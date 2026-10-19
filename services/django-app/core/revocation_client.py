from typing import Any, Dict
import requests


class RevocationClientError(Exception):
    """Revocation failed. `code` is revocation_not_persisted (gateway 503) or
    revocation_unavailable (network/other HTTP error)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class TokenRevocationClient:
    def __init__(
        self,
        revoke_url: str,
        timeout_connect: float,
        timeout_read: float,
        internal_token: str = "",
    ) -> None:
        self.revoke_url = revoke_url
        self.timeout = (timeout_connect, timeout_read)
        self.session = requests.Session()
        if internal_token:
            self.session.headers["X-Internal-Token"] = internal_token

    def revoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            response = self.session.post(self.revoke_url, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise RevocationClientError("revocation_unavailable") from exc
        if response.status_code == 503:
            raise RevocationClientError("revocation_not_persisted")
        try:
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RevocationClientError("revocation_unavailable") from exc
