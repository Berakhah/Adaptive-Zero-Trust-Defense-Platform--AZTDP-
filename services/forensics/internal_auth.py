"""Service-to-service authentication via shared X-Internal-Token header.

Internal endpoints (policy decision, token revoke, telemetry ingest, anomaly
score) are reachable only from sibling services on the docker bridge network.
The shared secret is delivered via Docker secret / env (AZTDP_INTERNAL_TOKEN).
If unset, a clear startup-time RuntimeError is raised — there is no silent
"open" mode, since that was exactly the lateral-movement gap this closes.
"""
import hmac
import os
from typing import Optional

from fastapi import Header, HTTPException

INTERNAL_TOKEN_ENV = "AZTDP_INTERNAL_TOKEN"
INTERNAL_TOKEN_HEADER = "X-Internal-Token"


def _expected_token() -> str:
    token = os.getenv(INTERNAL_TOKEN_ENV, "")
    if not token:
        raise RuntimeError(
            f"{INTERNAL_TOKEN_ENV} not set; refusing to start with open internal endpoints"
        )
    return token


def require_internal_token(
    x_internal_token: Optional[str] = Header(default=None, alias=INTERNAL_TOKEN_HEADER),
) -> None:
    expected = _expected_token()
    if not x_internal_token or not hmac.compare_digest(x_internal_token, expected):
        raise HTTPException(status_code=401, detail="internal_auth_required")
