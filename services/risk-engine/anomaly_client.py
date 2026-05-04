import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

import requests

from . import config

logger = logging.getLogger("aztdp.risk.anomaly_client")

ANOMALY_TIMEOUT = 0.15  # 150ms
_internal_token = os.getenv("AZTDP_INTERNAL_TOKEN", "")


def score(payload: Dict[str, Any], last_seen: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Call the anomaly service. Returns None on any error (fail-open)."""
    if not config.ANOMALY_URL:
        return None

    body = _build_request(payload, last_seen)
    headers = {"X-Internal-Token": _internal_token} if _internal_token else {}
    try:
        resp = requests.post(
            f"{config.ANOMALY_URL.rstrip('/')}/v1/anomaly/score",
            json=body,
            headers=headers,
            timeout=ANOMALY_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None


def _build_request(payload: Dict[str, Any], last_seen: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    ts = _parse_timestamp(payload.get("timestamp"))
    ip_changed = bool(last_seen and last_seen.get("ip") and last_seen.get("ip") != payload.get("ip"))
    geo_changed = bool(last_seen and last_seen.get("geo") and last_seen.get("geo") != payload.get("geo"))
    ua_changed = bool(
        last_seen and last_seen.get("ua") and last_seen.get("ua") != payload.get("user_agent_hash")
    )
    return {
        "request_id": payload.get("request_id"),
        "user_id": payload.get("user_id"),
        "session_id": payload.get("session_id"),
        "token_jti_hash": payload.get("token_jti_hash"),
        "ip": payload.get("ip"),
        "geo": payload.get("geo"),
        "user_agent_hash": payload.get("user_agent_hash"),
        "hour_of_day": ts.hour,
        "day_of_week": ts.weekday(),
        "endpoint_sensitivity": int(payload.get("endpoint", {}).get("sensitivity", 1)),
        "ip_changed": ip_changed,
        "geo_changed": geo_changed,
        "ua_changed": ua_changed,
    }


def _parse_timestamp(value: Optional[str]) -> datetime:
    if not value:
        return datetime.utcnow()
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.utcnow()
