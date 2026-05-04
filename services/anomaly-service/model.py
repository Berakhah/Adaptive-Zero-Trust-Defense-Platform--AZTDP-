import os
import threading
import time
from pathlib import Path
from typing import Optional, Tuple

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

from . import config


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
        if not self.is_loaded:
            raise RuntimeError("model not fitted")
        Path(config.MODEL_DIR).mkdir(parents=True, exist_ok=True)
        path = Path(config.MODEL_DIR) / f"isolation_forest_{self._version}.pkl"
        joblib.dump(
            {
                "estimator": self._estimator,
                "version": self._version,
                "score_min": self._score_min,
                "score_max": self._score_max,
            },
            path,
        )
        return path

    def load(self, version: str) -> bool:
        path = Path(config.MODEL_DIR) / f"isolation_forest_{version}.pkl"
        if not path.exists():
            return False
        bundle = joblib.load(path)
        with self._lock:
            self._estimator = bundle["estimator"]
            self._version = bundle["version"]
            self._score_min = float(bundle["score_min"])
            self._score_max = float(bundle["score_max"])
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
                        model.load(target)
            except Exception:
                pass
            time.sleep(interval)

    thread = threading.Thread(target=_loop, name="anomaly-model-reload", daemon=True)
    thread.start()
    return thread
