import logging
import time
from typing import Any, Dict, Optional

import redis
from fastapi import Depends, FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from . import config, metrics
from .feature_engineering import build_feature_vector, record_request
from .internal_auth import require_internal_token
from .model import AnomalyModel, start_hot_reload
from .training import cold_start_train, persist_baseline, retrain_from_baselines, start_retrain_scheduler

from .json_logging import configure as _configure_logging
_configure_logging("anomaly-service")
logger = logging.getLogger("aztdp.anomaly")

app = FastAPI(title="aztdp-anomaly-service")
model = AnomalyModel()
redis_client: Optional[redis.Redis] = None


class AnomalyRequest(BaseModel):
    request_id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    token_jti_hash: str
    ip: Optional[str] = None
    geo: Optional[str] = None
    user_agent_hash: Optional[str] = None
    hour_of_day: int = Field(ge=0, le=23)
    day_of_week: int = Field(ge=0, le=6)
    endpoint_sensitivity: int = Field(ge=1, le=5)
    ip_changed: bool = False
    geo_changed: bool = False
    ua_changed: bool = False
    request_rate_1m: Optional[float] = None
    time_since_last_request: Optional[float] = None


@app.on_event("startup")
def _on_startup() -> None:
    global redis_client
    if config.REDIS_URL:
        try:
            redis_client = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
            redis_client.ping()
        except Exception as exc:
            logger.warning("redis unavailable: %s", exc)
            redis_client = None

    target_version = "v1.0"
    if redis_client is not None:
        try:
            stored = redis_client.get(config.MODEL_VERSION_KEY)
            if stored:
                target_version = stored
        except Exception:
            pass

    if not model.load(target_version):
        cold_start_train(model, version=target_version)
        if redis_client is not None:
            try:
                redis_client.set(config.MODEL_VERSION_KEY, model.version)
            except Exception:
                pass

    metrics.MODEL_VERSION.labels(version=model.version).set(1)
    start_hot_reload(model, redis_client)
    start_retrain_scheduler(model, redis_client)
    logger.info("anomaly service ready, model=%s", model.version)


@app.get("/health")
def health() -> Dict[str, Any]:
    if not model.is_loaded:
        raise HTTPException(status_code=503, detail={"status": "loading"})
    return {"status": "ok", "model_version": model.version}


@app.get("/metrics")
def prometheus_metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/anomaly/score", dependencies=[Depends(require_internal_token)])
def score_anomaly(request: AnomalyRequest) -> Dict[str, Any]:
    if not model.is_loaded:
        return {
            "anomaly_score": 0.0,
            "is_anomalous": False,
            "model_version": "",
            "confidence": 0.0,
        }

    payload = request.model_dump()
    X = build_feature_vector(payload, redis_client=redis_client)

    start = time.perf_counter()
    score, confidence = model.score(X)
    metrics.INFERENCE_LATENCY.observe(time.perf_counter() - start)
    metrics.ANOMALY_SCORES.observe(score)

    is_anomalous = score >= config.ANOMALY_THRESHOLD
    if is_anomalous:
        metrics.ANOMALY_FLAGGED.inc()

    if request.user_id and redis_client is not None:
        record_request(redis_client, request.user_id)

    # Persist feature vector to anomaly_baselines for future retraining (P3.1)
    if request.user_id:
        persist_baseline(X, request.user_id, model.version)

    return {
        "anomaly_score": round(score, 4),
        "is_anomalous": is_anomalous,
        "model_version": model.version,
        "confidence": round(confidence, 4),
    }


@app.post("/v1/anomaly/retrain", dependencies=[Depends(require_internal_token)])
def manual_retrain() -> Dict[str, Any]:
    """Trigger an immediate model retrain from anomaly_baselines.

    Protected by internal auth. Returns the new model version on success.
    """
    import time as _time
    next_version = f"v{int(_time.time())}"
    success = retrain_from_baselines(model, next_version)
    if not success:
        return {"status": "skipped", "reason": "not enough baselines (min 1000 rows)"}

    if redis_client is not None:
        try:
            redis_client.set(config.MODEL_VERSION_KEY, model.version)
        except Exception:
            pass

    metrics.MODEL_VERSION.labels(version=model.version).set(1)
    return {"status": "retrained", "model_version": model.version}
