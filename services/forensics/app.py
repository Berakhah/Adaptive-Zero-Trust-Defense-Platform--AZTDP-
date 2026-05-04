import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from . import config, metrics
from .db import close_pool, get_pool

from .json_logging import configure as _configure_logging
_configure_logging("forensics")
logger = logging.getLogger("aztdp.forensics")

app = FastAPI(title="aztdp-forensics")


@app.on_event("startup")
def _on_startup() -> None:
    try:
        get_pool().open()
    except Exception as exc:
        logger.warning("forensics pool open failed: %s", exc)


@app.on_event("shutdown")
def _on_shutdown() -> None:
    close_pool()


@app.get("/health")
def health() -> Dict[str, str]:
    try:
        with get_pool().connection() as conn:
            conn.execute("SELECT 1")
    except Exception:
        raise HTTPException(status_code=503, detail="db_unavailable")
    return {"status": "ok"}


@app.get("/metrics")
def prom_metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/v1/forensics/events")
def list_events(
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    request_id: Optional[str] = None,
    event_type: Optional[str] = None,
    ip: Optional[str] = None,
    since: Optional[str] = Query(None, description="ISO8601"),
    until: Optional[str] = Query(None, description="ISO8601"),
    limit: int = Query(config.DEFAULT_PAGE_SIZE, ge=1, le=config.MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    metrics.QUERY_COUNT.labels(endpoint="events").inc()
    start = time.perf_counter()
    try:
        clauses: List[str] = []
        params: List[Any] = []
        if user_id:
            clauses.append("user_id = %s")
            params.append(user_id)
        if session_id:
            clauses.append("session_id = %s")
            params.append(session_id)
        if request_id:
            clauses.append("request_id = %s")
            params.append(request_id)
        if event_type:
            clauses.append("event_type = %s")
            params.append(event_type)
        if ip:
            clauses.append("ip = %s")
            params.append(ip)
        if since:
            clauses.append("occurred_at >= %s::timestamptz")
            params.append(since)
        if until:
            clauses.append("occurred_at <= %s::timestamptz")
            params.append(until)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"""
            SELECT event_id, event_type, service, request_id, session_id,
                   user_id, token_jti_hash, ip, geo, payload, occurred_at
            FROM audit_events
            {where}
            ORDER BY occurred_at DESC
            LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])
        with get_pool().connection() as conn:
            rows = list(conn.execute(sql, params).fetchall())
        return {"events": rows, "count": len(rows), "limit": limit, "offset": offset}
    finally:
        metrics.QUERY_LATENCY.labels(endpoint="events").observe(time.perf_counter() - start)


@app.get("/v1/forensics/replay/{session_id}")
def replay_session(session_id: str) -> Dict[str, Any]:
    metrics.QUERY_COUNT.labels(endpoint="replay").inc()
    start = time.perf_counter()
    try:
        sql = """
            SELECT event_id, event_type, service, request_id, ip, geo,
                   payload, occurred_at,
                   EXTRACT(EPOCH FROM (occurred_at - LAG(occurred_at) OVER w)) * 1000.0 AS delta_ms
            FROM audit_events
            WHERE session_id = %s
            WINDOW w AS (ORDER BY occurred_at)
            ORDER BY occurred_at
        """
        with get_pool().connection() as conn:
            timeline = list(conn.execute(sql, [session_id]).fetchall())
            session_meta = conn.execute(
                "SELECT * FROM sessions WHERE session_id = %s", [session_id]
            ).fetchone()
        if not timeline and not session_meta:
            raise HTTPException(status_code=404, detail="session_not_found")
        return {"session": session_meta, "timeline": timeline, "event_count": len(timeline)}
    finally:
        metrics.QUERY_LATENCY.labels(endpoint="replay").observe(time.perf_counter() - start)


@app.get("/v1/forensics/incidents/{request_id}")
def incident_detail(request_id: str) -> Dict[str, Any]:
    metrics.QUERY_COUNT.labels(endpoint="incidents").inc()
    start = time.perf_counter()
    try:
        with get_pool().connection() as conn:
            decision = conn.execute(
                """
                SELECT * FROM policy_decisions
                WHERE request_id = %s
                ORDER BY decided_at DESC
                LIMIT 1
                """,
                [request_id],
            ).fetchone()
            if not decision:
                raise HTTPException(status_code=404, detail="incident_not_found")
            context = list(
                conn.execute(
                    """
                    SELECT event_id, event_type, service, request_id, payload, occurred_at
                    FROM audit_events
                    WHERE occurred_at BETWEEN
                        (SELECT decided_at FROM policy_decisions WHERE request_id = %s ORDER BY decided_at DESC LIMIT 1)
                        - (%s || ' seconds')::interval
                      AND
                        (SELECT decided_at FROM policy_decisions WHERE request_id = %s ORDER BY decided_at DESC LIMIT 1)
                        + (%s || ' seconds')::interval
                    ORDER BY occurred_at
                    """,
                    [request_id, config.INCIDENT_WINDOW_SECONDS, request_id, config.INCIDENT_WINDOW_SECONDS],
                ).fetchall()
            )
            risk = conn.execute(
                "SELECT * FROM risk_evaluations WHERE request_id = %s", [request_id]
            ).fetchone()
        return {"decision": decision, "risk": risk, "context_window": context}
    finally:
        metrics.QUERY_LATENCY.labels(endpoint="incidents").observe(time.perf_counter() - start)
