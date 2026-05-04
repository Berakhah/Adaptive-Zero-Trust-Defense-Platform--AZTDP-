import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

import requests

from . import config

logger = logging.getLogger("aztdp.risk.telemetry")

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="aztdp-telemetry")
_internal_token = os.getenv("AZTDP_INTERNAL_TOKEN", "")


def emit_async(payload: Dict[str, Any]) -> None:
    if not config.TELEMETRY_URL:
        return
    try:
        _executor.submit(_post, payload)
    except RuntimeError:
        pass


def shutdown_executor(timeout: float = 2.0) -> None:
    _executor.shutdown(wait=True, cancel_futures=False)


def _post(payload: Dict[str, Any]) -> None:
    body = {"event_type": "risk_eval", "service": "risk-engine", **payload}
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
