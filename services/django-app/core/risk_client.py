from typing import Any, Dict
import requests


class RiskClientError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class RiskClient:
    def __init__(
        self,
        base_url: str,
        timeout_connect: float,
        timeout_read: float,
        internal_token: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = (timeout_connect, timeout_read)
        self.session = requests.Session()
        if internal_token:
            self.session.headers["X-Internal-Token"] = internal_token

    def evaluate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/v1/risk/evaluate"
        try:
            response = self.session.post(url, json=payload, timeout=self.timeout)
            if response.status_code == 409:
                raise RiskClientError("replay_detected")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise RiskClientError("risk_unavailable") from exc
