"""Service-to-service authentication via shared X-Internal-Token header.

See services/gateway/internal_auth.py for the canonical doc — this file is a
verbatim copy because each service is its own Docker build context with no
shared library tree.
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
