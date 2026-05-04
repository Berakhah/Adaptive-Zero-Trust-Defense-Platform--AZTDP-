"""Step-up challenge issuance and TOTP verification.

When the OPA policy returns a *stepup* decision the middleware issues a
challenge (challenge_id + allowed methods + TTL). This module:

1.  Stores pending challenges in a TTL-expiring in-memory dict (per-worker).
2.  Provides a verification endpoint that validates a TOTP code and returns a
    short-lived ``step_up_token`` JWT.
3.  The token is a self-contained HS256 JWT containing the original challenge_id,
    the user sub, and an expiry. Downstream middleware or OPA can check for it
    to bypass the step-up gate on subsequent requests.

Production considerations
~~~~~~~~~~~~~~~~~~~~~~~~~
*  Replace the in-memory store with Redis (same Redis instance as revocations)
   to share challenge state across gunicorn workers.
*  Pull the TOTP secret from Keycloak's credential store per-user instead of
   a single shared secret.
*  WebAuthn verification requires a server-side library (e.g. py_webauthn);
   this module covers TOTP only as the first practical implementation.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import os
import struct
import time
from typing import Any, Dict, Optional

_CHALLENGE_TTL = 300  # seconds
_STEP_UP_TOKEN_TTL = 600  # 10 minutes
_TOTP_STEP = 30
_TOTP_DIGITS = 6

# In production: pull from Keycloak user credential or Vault.
_TOTP_SECRET = os.getenv("AZTDP_TOTP_SECRET", "AZTDP_DEV_TOTP_SECRET_BASE32")
_SIGNING_KEY = os.getenv("AZTDP_STEPUP_SIGNING_KEY", "aztdp-stepup-signing-key-change-me")


# ── In-memory challenge store (single-worker; replace with Redis for multi) ──

_challenges: Dict[str, Dict[str, Any]] = {}


def create_challenge(challenge_id: str, user_id: str) -> Dict[str, Any]:
    """Store a pending step-up challenge keyed by challenge_id."""
    entry = {
        "challenge_id": challenge_id,
        "user_id": user_id,
        "created_at": time.time(),
        "verified": False,
    }
    _challenges[challenge_id] = entry
    _gc()
    return entry


def verify_challenge(challenge_id: str, totp_code: str, user_id: str) -> Optional[str]:
    """Validate a TOTP code against the stored challenge.

    Returns a signed step_up_token JWT string on success, or None on failure.
    """
    entry = _challenges.get(challenge_id)
    if not entry:
        return None
    if entry["user_id"] != user_id:
        return None
    if time.time() - entry["created_at"] > _CHALLENGE_TTL:
        _challenges.pop(challenge_id, None)
        return None
    if entry["verified"]:
        return None  # one-shot

    if not _verify_totp(totp_code, _TOTP_SECRET):
        return None

    entry["verified"] = True
    _challenges.pop(challenge_id, None)

    return _mint_step_up_token(user_id, challenge_id)


# ── TOTP implementation (RFC 6238 / RFC 4226) ────────────────────────────────

def _verify_totp(code: str, secret: str, window: int = 1) -> bool:
    """Verify a TOTP code within ±window time steps."""
    if not code or not code.isdigit() or len(code) != _TOTP_DIGITS:
        return False
    now = int(time.time())
    for offset in range(-window, window + 1):
        counter = (now // _TOTP_STEP) + offset
        expected = _hotp(secret, counter)
        if hmac.compare_digest(code, expected):
            return True
    return False


def _hotp(secret: str, counter: int) -> str:
    """Compute an HOTP code per RFC 4226."""
    import base64
    try:
        key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    except Exception:
        key = secret.encode("utf-8")
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10 ** _TOTP_DIGITS)).zfill(_TOTP_DIGITS)


# ── Step-up token (compact HS256 JWT) ────────────────────────────────────────

def _mint_step_up_token(user_id: str, challenge_id: str) -> str:
    """Issue a minimal HS256 JWT for step-up proof.

    We avoid a full PyJWT dependency by constructing the token manually.
    This is a self-contained claim that the enforcement middleware can verify.
    """
    import base64
    import json as _json

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "challenge_id": challenge_id,
        "purpose": "step_up",
        "iat": int(time.time()),
        "exp": int(time.time()) + _STEP_UP_TOKEN_TTL,
    }

    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    segments = _b64(_json.dumps(header).encode()) + "." + _b64(_json.dumps(payload).encode())
    sig = hmac.new(_SIGNING_KEY.encode("utf-8"), segments.encode("ascii"), hashlib.sha256).digest()
    return segments + "." + _b64(sig)


def verify_step_up_token(token: str, user_id: str) -> bool:
    """Verify a previously issued step-up token."""
    import base64
    import json as _json

    try:
        parts = token.split(".")
        if len(parts) != 3:
            return False

        def _unb64(s: str) -> bytes:
            s += "=" * (-len(s) % 4)
            return base64.urlsafe_b64decode(s)

        segments = parts[0] + "." + parts[1]
        expected_sig = hmac.new(
            _SIGNING_KEY.encode("utf-8"), segments.encode("ascii"), hashlib.sha256
        ).digest()
        actual_sig = _unb64(parts[2])
        if not hmac.compare_digest(expected_sig, actual_sig):
            return False

        payload = _json.loads(_unb64(parts[1]))
        if payload.get("purpose") != "step_up":
            return False
        if payload.get("sub") != user_id:
            return False
        if payload.get("exp", 0) < time.time():
            return False
        return True
    except Exception:
        return False


# ── Housekeeping ─────────────────────────────────────────────────────────────

def _gc() -> None:
    """Remove expired challenges to prevent unbounded growth."""
    now = time.time()
    expired = [k for k, v in _challenges.items() if now - v["created_at"] > _CHALLENGE_TTL]
    for k in expired:
        _challenges.pop(k, None)
