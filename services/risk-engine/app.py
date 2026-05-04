import time
from typing import Any, Dict

from fastapi import Depends, FastAPI, HTTPException, Response

from .json_logging import configure as _configure_logging
_configure_logging("risk-engine")
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

from . import config, metrics
from .anomaly_client import score as score_anomaly
from .internal_auth import require_internal_token
from .risk_model import score_risk
from .storage import ReplayStore
from .telemetry import emit_async

app = FastAPI(title="aztdp-risk-engine")
store = ReplayStore()


class Endpoint(BaseModel):
    service: str
    method: str
    path: str
    sensitivity: int


class RiskRequest(BaseModel):
    request_id: str
    session_id: str | None = None
    user_id: str | None = None
    token_jti_hash: str
    ip: str | None = None
    geo: str | None = None
    user_agent_hash: str | None = None
    endpoint: Endpoint
    timestamp: str


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def prom_metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/risk/evaluate", dependencies=[Depends(require_internal_token)])
def evaluate_risk(request: RiskRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    last_seen = store.get_last_seen(request.token_jti_hash)
    payload = request.model_dump()
    risk, reasons, replay_detected = score_risk(payload, last_seen)

    if replay_detected:
        metrics.REPLAY_DETECTED.inc()
        raise HTTPException(status_code=409, detail="replay_detected")

    anomaly_payload = score_anomaly(payload, last_seen)
    anomaly_score = 0.0
    anomaly_version = ""
    if anomaly_payload:
        anomaly_score = float(anomaly_payload.get("anomaly_score", 0.0))
        anomaly_version = str(anomaly_payload.get("model_version", ""))
        if anomaly_payload.get("is_anomalous"):
            reasons.append({"code": "ML_ANOMALY", "weight": anomaly_score})
        risk = min(1.0, risk + (anomaly_score * 0.2))

    store.set_last_seen(
        request.token_jti_hash,
        {"ip": request.ip, "geo": request.geo, "ua": request.user_agent_hash, "ts": time.time()},
    )

    trust = max(0.0, 1.0 - risk)
    metrics.RISK_SCORES.observe(risk)
    metrics.EVAL_LATENCY.observe(time.perf_counter() - started)

    response = {
        "risk_score": round(risk, 4),
        "trust_score": round(trust, 4),
        "anomaly_score": round(anomaly_score, 4),
        "anomaly_model_version": anomaly_version,
        "reasons": reasons,
        "ttl_seconds": config.TOKEN_TTL_SECONDS,
    }

    emit_async(
        {
            "request_id": request.request_id,
            "session_id": request.session_id,
            "user_id": request.user_id,
            "token_jti_hash": request.token_jti_hash,
            "ip": request.ip,
            "geo": request.geo,
            "payload": {
                "risk_score": response["risk_score"],
                "trust_score": response["trust_score"],
                "anomaly_score": response["anomaly_score"],
                "reasons": reasons,
                "endpoint_path": request.endpoint.path,
                "endpoint_method": request.endpoint.method,
                "sensitivity": request.endpoint.sensitivity,
            },
        }
    )

    return response
