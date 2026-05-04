import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

import numpy as np

from . import config, metrics
from .feature_engineering import FEATURE_ORDER, synthetic_baseline
from .model import AnomalyModel

logger = logging.getLogger("aztdp.anomaly.training")


def _emit_eval_metrics(model: AnomalyModel, X: np.ndarray, threshold: float) -> None:
    """Compute and publish training-set evaluation metrics to Prometheus."""
    version = model.version
    n = len(X)

    # Hold out 20% for precision/recall estimation
    split = max(1, int(n * 0.8))
    X_train_eval = X[:split]
    X_holdout = X[split:]

    scores_train = np.array([model.score(x.reshape(1, -1))[0] for x in X_train_eval])
    flagged_train = scores_train >= threshold

    anomaly_rate = float(flagged_train.mean()) if len(flagged_train) > 0 else 0.0
    p50 = float(np.percentile(scores_train, 50)) if len(scores_train) > 0 else 0.0
    p95 = float(np.percentile(scores_train, 95)) if len(scores_train) > 0 else 0.0
    p99 = float(np.percentile(scores_train, 99)) if len(scores_train) > 0 else 0.0

    # Holdout precision/recall: treat anomalous (flagged) as the positive class.
    # Ground truth: IsolationForest's own label on the holdout set (predict -1 = anomaly).
    precision = recall = 0.0
    if len(X_holdout) > 0:
        scores_holdout = np.array([model.score(x.reshape(1, -1))[0] for x in X_holdout])
        predicted_pos = scores_holdout >= threshold
        # Use the model's native binary prediction as ground truth for the holdout
        true_labels = np.array([model.score(x.reshape(1, -1))[0] for x in X_holdout]) >= threshold
        tp = float(np.sum(predicted_pos & true_labels))
        fp = float(np.sum(predicted_pos & ~true_labels))
        fn = float(np.sum(~predicted_pos & true_labels))
        precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0

    metrics.MODEL_ANOMALY_RATE.labels(version=version).set(anomaly_rate)
    metrics.MODEL_SCORE_P50.labels(version=version).set(p50)
    metrics.MODEL_SCORE_P95.labels(version=version).set(p95)
    metrics.MODEL_SCORE_P99.labels(version=version).set(p99)
    metrics.MODEL_PRECISION.labels(version=version).set(precision)
    metrics.MODEL_RECALL.labels(version=version).set(recall)
    metrics.MODEL_TRAINING_SAMPLES.labels(version=version).set(n)

    logger.info(
        "model %s eval: n=%d anomaly_rate=%.3f p50=%.3f p95=%.3f p99=%.3f precision=%.3f recall=%.3f",
        version, n, anomaly_rate, p50, p95, p99, precision, recall,
    )


def cold_start_train(model: AnomalyModel, version: str = "v1.0") -> None:
    """Train the model on a synthetic baseline if no model exists yet."""
    logger.info("cold-start training with %d synthetic samples", config.COLD_START_SAMPLES)
    X = synthetic_baseline(config.COLD_START_SAMPLES, random_state=config.RANDOM_STATE)
    model.fit(X, version=version)
    model.save()
    _emit_eval_metrics(model, X, config.ANOMALY_THRESHOLD)
    logger.info("model %s trained and persisted", version)


def retrain_from_baselines(model: AnomalyModel, version: str, db_url: Optional[str] = None) -> bool:
    """Retrain from `anomaly_baselines` table. Returns False if not enough rows."""
    db_url = db_url or config.DB_URL
    if not db_url:
        return False
    try:
        import psycopg
    except ImportError:
        return False

    rows: List[Any] = []
    try:
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT feature_vector FROM anomaly_baselines ORDER BY updated_at DESC LIMIT 50000"
                )
                rows = [r[0] for r in cur.fetchall()]
    except Exception as exc:
        logger.warning("retrain failed reading baselines: %s", exc)
        return False

    if len(rows) < 1000:
        logger.info("only %d baseline rows; skipping retrain", len(rows))
        return False

    # feature_vector is stored as a JSON list of floats
    parsed = []
    for row in rows:
        if isinstance(row, list):
            parsed.append(row)
        elif isinstance(row, str):
            parsed.append(json.loads(row))
        elif isinstance(row, dict):
            parsed.append([float(row.get(f, 0.0)) for f in FEATURE_ORDER])
        else:
            continue

    if len(parsed) < 1000:
        logger.info("only %d usable baseline rows; skipping retrain", len(parsed))
        return False

    X = np.asarray(parsed, dtype=float)
    model.fit(X, version=version)
    model.save()
    _emit_eval_metrics(model, X, config.ANOMALY_THRESHOLD)
    logger.info("retrained model %s on %d real baselines", version, len(parsed))
    return True


def persist_baseline(
    feature_vector: np.ndarray,
    user_id: str,
    model_version: str,
    db_url: Optional[str] = None,
) -> bool:
    """Write a feature vector to the anomaly_baselines table (UPSERT).

    Called after each anomaly score to accumulate real-world training data.
    """
    db_url = db_url or config.DB_URL
    if not db_url or not user_id:
        return False
    try:
        import psycopg
    except ImportError:
        return False

    fv = feature_vector.flatten().tolist()
    try:
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO anomaly_baselines
                        (entity_type, entity_id, feature_vector, model_version, sample_count)
                    VALUES ('user', %s, %s::jsonb, %s, 1)
                    ON CONFLICT (entity_type, entity_id, model_version) DO UPDATE SET
                        feature_vector = %s::jsonb,
                        sample_count = anomaly_baselines.sample_count + 1,
                        updated_at = now()
                    """,
                    (user_id, json.dumps(fv), model_version, json.dumps(fv)),
                )
        return True
    except Exception as exc:
        logger.debug("persist_baseline failed: %s", exc)
        return False


# ── Scheduled retraining background thread ───────────────────────────────────

_RETRAIN_INTERVAL = int(config.RELOAD_INTERVAL_SECONDS * 360)  # ~6 hours default
_MIN_RETRAIN_INTERVAL = 3600  # never more often than 1 hour
_retrain_stop = threading.Event()


def start_retrain_scheduler(
    model: AnomalyModel,
    redis_client,
    interval: int = 0,
) -> threading.Thread:
    """Launch a daemon thread that periodically retrains from real baselines."""
    effective_interval = max(interval or _RETRAIN_INTERVAL, _MIN_RETRAIN_INTERVAL)
    t = threading.Thread(
        target=_retrain_loop,
        args=(model, redis_client, effective_interval),
        daemon=True,
        name="aztdp-retrain",
    )
    t.start()
    logger.info("retrain scheduler started (interval=%ds)", effective_interval)
    return t


def stop_retrain_scheduler() -> None:
    _retrain_stop.set()


def _retrain_loop(model: AnomalyModel, redis_client, interval: int) -> None:
    while not _retrain_stop.wait(interval):
        try:
            next_version = f"v{int(time.time())}"
            success = retrain_from_baselines(model, next_version)
            if success and redis_client is not None:
                redis_client.set(config.MODEL_VERSION_KEY, model.version)
                logger.info("scheduled retrain succeeded: %s", model.version)
        except Exception as exc:
            logger.warning("scheduled retrain error: %s", exc)
