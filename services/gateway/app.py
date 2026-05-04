from typing import Any, Dict

from fastapi import Depends, FastAPI, HTTPException, Response

from .json_logging import configure as _configure_logging
_configure_logging("gateway")
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

from . import config, metrics
from .internal_auth import require_internal_token
from .opa_client import OpaClientError, evaluate
from .revocation_store import RevocationStore
from .telemetry import emit_async, shutdown_executor

app = FastAPI(title="aztdp-policy-gateway")
revocations = RevocationStore()


@app.on_event("startup")
def _on_startup() -> None:
    revocations.cold_start_recovery()


@app.on_event("shutdown")
def _drain_telemetry() -> None:
    shutdown_executor()


class DecisionRequest(BaseModel):
    input: Dict[str, Any]


class RevokeRequest(BaseModel):
    token_jti_hash: str
    reason: str
    source: str


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def prom_metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/policy/decision", dependencies=[Depends(require_internal_token)])
def policy_decision(request: DecisionRequest) -> Dict[str, Any]:
    request_id = str(request.input.get("request_id", ""))
    context = request.input.get("context", {}) or {}
    token_hash = str(context.get("token_jti_hash", ""))

    if revocations.is_revoked(token_hash):
        decision = {"decision": "revoke", "reason": {"rule": "token_revoked"}}
        _emit(request_id, decision, request.input, token_hash)
        return {"decision": decision}

    try:
        opa_response = evaluate({"input": request.input})
    except OpaClientError:
        if config.FAIL_OPEN:
            decision = {"decision": "allow", "reason": {"rule": "fail_open"}}
            _emit(request_id, decision, request.input, token_hash)
            return {"decision": decision}
        raise HTTPException(status_code=503, detail="policy_unavailable")

    result = opa_response.get("result", opa_response)
    if isinstance(result, dict) and "decision" in result:
        decision = result
    else:
        decision = {"decision": "deny", "reason": {"rule": "invalid_response"}}

    _emit(request_id, decision, request.input, token_hash)
    return {"decision": decision}


@app.get("/v1/policy/version", dependencies=[Depends(require_internal_token)])
def policy_version() -> Dict[str, str]:
    return {"version": "dev", "bundle_hash": ""}


@app.post("/v1/tokens/revoke", dependencies=[Depends(require_internal_token)])
def revoke_token(request: RevokeRequest) -> Dict[str, Any]:
    if request.token_jti_hash:
        revocations.revoke(request.token_jti_hash)
        metrics.REVOCATIONS.inc()
        emit_async(
            "token_revocation",
            {
                "token_jti_hash": request.token_jti_hash,
                "payload": {"reason": request.reason, "source": request.source},
            },
        )
    return {"status": "revoked"}


@app.get("/v1/tokens/revoked/{token_jti_hash}", dependencies=[Depends(require_internal_token)])
def token_revoked(token_jti_hash: str) -> Dict[str, Any]:
    return {"revoked": revocations.is_revoked(token_jti_hash)}


def _emit(request_id: str, decision: Dict[str, Any], opa_input: Dict[str, Any], token_hash: str) -> None:
    metrics.POLICY_DECISIONS.labels(decision=decision.get("decision", "deny")).inc()
    subject = opa_input.get("subject", {}) or {}
    resource = opa_input.get("resource", {}) or {}
    context = opa_input.get("context", {}) or {}
    emit_async(
        "policy_decision",
        {
            "request_id": request_id,
            "user_id": subject.get("user_id"),
            "session_id": subject.get("session_id"),
            "token_jti_hash": token_hash,
            "ip": context.get("ip"),
            "geo": context.get("geo"),
            "payload": {
                "decision": decision.get("decision"),
                "reason": decision.get("reason", {}),
                "policy": "aztdp.authz",
                "risk_score": context.get("risk_score"),
                "anomaly_score": context.get("anomaly_score"),
                "endpoint_path": resource.get("path"),
            },
        },
    )
