import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

import requests

from . import config

logger = logging.getLogger("aztdp.gateway.telemetry")

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="aztdp-telemetry")
_internal_token = os.getenv("AZTDP_INTERNAL_TOKEN", "")


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
    try:
        requests.post(
            f"{config.TELEMETRY_URL.rstrip('/')}/v1/telemetry/event",
            json=body,
            headers=headers,
            timeout=(0.2, 0.5),
        )
    except Exception as exc:
        logger.debug("telemetry emit failed: %s", exc)
