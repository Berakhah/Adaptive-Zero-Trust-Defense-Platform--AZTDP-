import hashlib
import hmac
import io
import logging
import os
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional, Tuple

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

from . import config

logger = logging.getLogger("aztdp.anomaly.model")

_VERSION_RE = re.compile(r"v[0-9A-Za-z._-]+")  # used with fullmatch


def is_valid_version(version) -> bool:
    """True only for strings safe to embed in an artifact filename."""
    return isinstance(version, str) and _VERSION_RE.fullmatch(version) is not None


def _sign(data: bytes) -> str:
    return hmac.new(config.MODEL_HMAC_KEY.encode(), data, hashlib.sha256).hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    """Write to a temp file in the same dir, fsync, then rename into place."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

class AnomalyModel:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._estimator: Optional[IsolationForest] = None
        self._version: str = ""
        self._score_min: float = -0.5
        self._score_max: float = 0.5

    @property
    def version(self) -> str:
        return self._version

    @property
    def is_loaded(self) -> bool:
        return self._estimator is not None

    def fit(self, X: np.ndarray, version: str) -> None:
        clf = IsolationForest(
            n_estimators=config.N_ESTIMATORS,
            contamination=config.CONTAMINATION,
            random_state=config.RANDOM_STATE,
        )
        clf.fit(X)
        raw_scores = clf.score_samples(X)
        with self._lock:
            self._estimator = clf
            self._version = version
            self._score_min = float(np.min(raw_scores))
            self._score_max = float(np.max(raw_scores))

    def save(self) -> Path:
        """Persist the model and its HMAC signature.

        The model is renamed into place first and the signature LAST: a reader
        can never see a signed-looking model without its signature, and a
        signature that does not match the bytes is never trusted by load().
        """
        if not self.is_loaded:
            raise RuntimeError("model not fitted")
        if not is_valid_version(self._version):
            raise ValueError(f"invalid model version: {self._version!r}")
        if not config.MODEL_HMAC_KEY:
            raise RuntimeError("AZTDP_MODEL_HMAC_KEY is not set; refusing to save unsigned model")
        model_dir = Path(config.MODEL_DIR)
        model_dir.mkdir(parents=True, exist_ok=True)
        path = model_dir / f"isolation_forest_{self._version}.pkl"
        buf = io.BytesIO()
        joblib.dump(
            {
                "estimator": self._estimator,
                "version": self._version,
                "score_min": self._score_min,
                "score_max": self._score_max,
            },
            buf,
        )
        data = buf.getvalue()
        _atomic_write(path, data)
        _atomic_write(path.with_name(path.name + ".sig"), _sign(data).encode())
        return path

    def load(self, version: str) -> bool:
        """Load a signed model. Never unpickles bytes whose HMAC does not verify."""
        if not is_valid_version(version):
            logger.error("invalid model version rejected: %r", version)
            return False
        if not config.MODEL_HMAC_KEY:
            logger.error("model_signature_invalid version=%s reason=no_hmac_key", version)
            return False
        path = Path(config.MODEL_DIR) / f"isolation_forest_{version}.pkl"
        sig_path = path.with_name(path.name + ".sig")
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            return False
        try:
            signature = sig_path.read_text().strip()
        except FileNotFoundError:
            logger.error("model_signature_invalid version=%s reason=missing_signature", version)
            return False
        if not hmac.compare_digest(_sign(data), signature):
            logger.error("model_signature_invalid version=%s reason=mismatch", version)
            return False
        try:
            bundle = joblib.load(io.BytesIO(data))  # only after verification
            estimator = bundle["estimator"]
            loaded_version = bundle["version"]
            score_min = float(bundle["score_min"])
            score_max = float(bundle["score_max"])
        except Exception:
            logger.exception("model artifact unreadable version=%s", version)
            return False
        with self._lock:
            self._estimator = estimator
            self._version = loaded_version
            self._score_min = score_min
            self._score_max = score_max
        return True

    def score(self, X: np.ndarray) -> Tuple[float, float]:
        with self._lock:
            if self._estimator is None:
                return 0.0, 0.0
            raw = float(self._estimator.score_samples(X)[0])
            denom = self._score_max - self._score_min
            if denom <= 0:
                normalized = 0.0
            else:
                normalized = (self._score_max - raw) / denom
            normalized = max(0.0, min(1.0, normalized))
            depths = [tree.decision_path(X).nnz for tree in self._estimator.estimators_]
            mean_depth = float(np.mean(depths))
            spread = float(np.std(depths))
            confidence = 1.0 / (1.0 + spread / max(mean_depth, 1.0))
            return normalized, max(0.0, min(1.0, confidence))


def start_hot_reload(model: AnomalyModel, redis_client, interval: int = None) -> threading.Thread:
    interval = interval or config.RELOAD_INTERVAL_SECONDS

    def _loop():
        while True:
            try:
                if redis_client is not None:
                    target = redis_client.get(config.MODEL_VERSION_KEY)
                    if target and target != model.version:
                        if not is_valid_version(target):
                            logger.error("invalid model version in redis ignored: %r", target)
                        elif not model.load(target):
                            logger.error("model hot reload failed version=%s", target)
            except Exception:
                logger.exception("model hot reload error")
            time.sleep(interval)

    thread = threading.Thread(target=_loop, name="anomaly-model-reload", daemon=True)
    thread.start()
    return thread
