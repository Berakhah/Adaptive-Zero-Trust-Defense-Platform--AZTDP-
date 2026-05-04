import json
import logging
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from . import config, metrics
from .db import close_pool, get_pool
from .internal_auth import require_internal_token

from .json_logging import configure as _configure_logging
_configure_logging("telemetry-ingest")
logger = logging.getLogger("aztdp.telemetry")

app = FastAPI(title="aztdp-telemetry-ingest")


VALID_EVENT_TYPES = {"risk_eval", "policy_decision", "token_revocation", "anomaly_score"}


class TelemetryEvent(BaseModel):
    event_type: str = Field(..., description="One of: risk_eval, policy_decision, token_revocation, anomaly_score")
    service: str
    request_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    token_jti_hash: Optional[str] = None
    ip: Optional[str] = None
    geo: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    occurred_at: Optional[str] = None


@app.on_event("startup")
def _on_startup() -> None:
    try:
        get_pool().open()
        logger.info("telemetry pool opened")
    except Exception as exc:
        logger.warning("pool open failed: %s", exc)


@app.on_event("shutdown")
def _on_shutdown() -> None:
    close_pool()


@app.get("/health")
def health() -> Dict[str, str]:
    try:
        pool = get_pool()
        with pool.connection() as conn:
            conn.execute("SELECT 1")
    except Exception:
        raise HTTPException(status_code=503, detail="db_unavailable")
    return {"status": "ok"}


@app.get("/metrics")
def prom_metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/telemetry/event", dependencies=[Depends(require_internal_token)])
def ingest(event: TelemetryEvent) -> Dict[str, Any]:
    if event.event_type not in VALID_EVENT_TYPES:
        raise HTTPException(status_code=400, detail="invalid_event_type")

    event_id = str(uuid.uuid4())
    start = time.perf_counter()
    try:
        with get_pool().connection() as conn:
            with conn.cursor() as cur:
                _insert_audit(cur, event_id, event)
                _denormalize(cur, event)
                _update_session(cur, event)
        metrics.EVENTS_INGESTED.labels(event_type=event.event_type).inc()
    except Exception as exc:
        metrics.INGEST_ERRORS.labels(event_type=event.event_type).inc()
        logger.error("ingest failed: %s", exc)
        raise HTTPException(status_code=500, detail="ingest_failed")
    finally:
        metrics.INGEST_LATENCY.observe(time.perf_counter() - start)

    return {"event_id": event_id, "status": "ingested"}


def _insert_audit(cur, event_id: str, event: TelemetryEvent) -> None:
    cur.execute(
        """
        INSERT INTO audit_events
            (event_id, event_type, service, request_id, session_id, user_id,
             token_jti_hash, ip, geo, payload, occurred_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                COALESCE(%s::timestamptz, now()))
        """,
        (
            event_id,
            event.event_type,
            event.service,
            event.request_id,
            event.session_id,
            event.user_id,
            event.token_jti_hash,
            event.ip,
            event.geo,
            json.dumps(event.payload),
            event.occurred_at,
        ),
    )


def _denormalize(cur, event: TelemetryEvent) -> None:
    p = event.payload
    if event.event_type == "risk_eval":
        cur.execute(
            """
            INSERT INTO risk_evaluations
                (request_id, session_id, user_id, token_jti_hash,
                 risk_score, trust_score, anomaly_score, reasons,
                 service, endpoint_path, endpoint_method, sensitivity)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
            """,
            (
                event.request_id or "",
                event.session_id,
                event.user_id,
                event.token_jti_hash,
                float(p.get("risk_score", 0.0)),
                float(p.get("trust_score", 0.0)),
                float(p.get("anomaly_score", 0.0)),
                json.dumps(p.get("reasons", [])),
                event.service,
                p.get("endpoint_path"),
                p.get("endpoint_method"),
                p.get("sensitivity"),
            ),
        )
    elif event.event_type == "policy_decision":
        cur.execute(
            """
            INSERT INTO policy_decisions
                (request_id, session_id, user_id, token_jti_hash,
                 decision, rule, policy, risk_score, anomaly_score,
                 service, endpoint_path)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event.request_id or "",
                event.session_id,
                event.user_id,
                event.token_jti_hash,
                p.get("decision", "deny"),
                (p.get("reason") or {}).get("rule") if isinstance(p.get("reason"), dict) else None,
                p.get("policy", "aztdp.authz"),
                p.get("risk_score"),
                p.get("anomaly_score"),
                event.service,
                p.get("endpoint_path"),
            ),
        )
    elif event.event_type == "token_revocation":
        cur.execute(
            """
            INSERT INTO token_revocations
                (token_jti_hash, reason, source, expires_at, user_id, session_id)
            VALUES (%s, %s, %s, %s::timestamptz, %s, %s)
            ON CONFLICT (token_jti_hash) DO NOTHING
            """,
            (
                event.token_jti_hash or "",
                p.get("reason", "policy"),
                p.get("source", "policy"),
                p.get("expires_at"),
                event.user_id,
                event.session_id,
            ),
        )


def _update_session(cur, event: TelemetryEvent) -> None:
    if not event.session_id or not event.user_id:
        return

    p = event.payload
    risk = float(p.get("risk_score", 0.0))
    anomaly = float(p.get("anomaly_score", 0.0))
    decision = p.get("decision") if event.event_type == "policy_decision" else None
    is_suspicious = decision is not None and decision != "allow"

    cur.execute(
        """
        INSERT INTO sessions
            (session_id, user_id, ip_first, geo_first, ip_last, geo_last,
             risk_max, risk_avg, anomaly_max, request_count,
             decision_counts, is_suspicious, last_seen_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1,
                %s::jsonb, %s, now())
        ON CONFLICT (session_id) DO UPDATE SET
            ip_last       = EXCLUDED.ip_last,
            geo_last      = EXCLUDED.geo_last,
            risk_max      = GREATEST(sessions.risk_max, EXCLUDED.risk_max),
            anomaly_max   = GREATEST(sessions.anomaly_max, EXCLUDED.anomaly_max),
            request_count = sessions.request_count + 1,
            risk_avg      = (sessions.risk_avg * sessions.request_count + EXCLUDED.risk_max)
                              / (sessions.request_count + 1),
            decision_counts = CASE
                WHEN %s IS NULL THEN sessions.decision_counts
                ELSE jsonb_set(
                    sessions.decision_counts,
                    ARRAY[%s::text],
                    to_jsonb(COALESCE((sessions.decision_counts->>%s)::int, 0) + 1)
                )
            END,
            is_suspicious = sessions.is_suspicious OR EXCLUDED.is_suspicious,
            last_seen_at  = now()
        """,
        (
            event.session_id,
            event.user_id,
            event.ip,
            event.geo,
            event.ip,
            event.geo,
            risk,
            risk,
            anomaly,
            json.dumps({"allow": 0, "deny": 0, "stepup": 0, "revoke": 0}),
            is_suspicious,
            decision,
            decision or "allow",
            decision or "allow",
        ),
    )
