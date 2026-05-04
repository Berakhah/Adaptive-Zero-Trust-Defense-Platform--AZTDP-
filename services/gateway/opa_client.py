from typing import Any, Dict
import requests

from . import config


class OpaClientError(Exception):
    pass


def evaluate(input_payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{config.OPA_URL}{config.OPA_DECISION_PATH}"
    try:
        response = requests.post(url, json=input_payload, timeout=config.REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise OpaClientError("opa_unavailable") from exc
