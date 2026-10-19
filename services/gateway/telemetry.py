import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

import requests

from . import config, metrics

logger = logging.getLogger("aztdp.gateway.telemetry")

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="aztdp-telemetry")
_internal_token = os.getenv("AZTDP_INTERNAL_TOKEN", "")

_BACKOFF_SECONDS = (0.05, 0.15, 0.45)  # 3 retries after the first attempt


def emit_async(event_type: str, payload: Dict[str, Any]) -> None:
    """Bounded fire-and-forget telemetry emit. Drained on shutdown via shutdown_executor()."""
    if not config.TELEMETRY_URL:
        return
    try:
        _executor.submit(_post, event_type, payload)
    except RuntimeError:
        # Executor already shut down — service is exiting; drop quietly.
        pass


def shutdown_executor(timeout: float = 2.0) -> None:
    _executor.shutdown(wait=True, cancel_futures=False)


def _post(event_type: str, payload: Dict[str, Any]) -> None:
    body = {"event_type": event_type, "service": "gateway", **payload}
    headers = {"X-Internal-Token": _internal_token} if _internal_token else {}
    url = f"{config.TELEMETRY_URL.rstrip('/')}/v1/telemetry/event"
    last_error = "unknown"
    for attempt in range(len(_BACKOFF_SECONDS) + 1):
        if attempt:
            metrics.TELEMETRY_RETRIES.labels(service="gateway").inc()
            time.sleep(_BACKOFF_SECONDS[attempt - 1])
        try:
            resp = requests.post(url, json=body, headers=headers, timeout=(0.2, 0.5))
            status = getattr(resp, "status_code", 200)
            if status < 400:
                return
            last_error = f"http {status}"
        except Exception as exc:
            last_error = str(exc)
    metrics.TELEMETRY_DROPPED.labels(service="gateway", reason="exhausted").inc()
    logger.warning(
        "audit telemetry dropped after %d attempts: event_type=%s request_id=%s error=%s",
        len(_BACKOFF_SECONDS) + 1, event_type, payload.get("request_id"), last_error,
    )
