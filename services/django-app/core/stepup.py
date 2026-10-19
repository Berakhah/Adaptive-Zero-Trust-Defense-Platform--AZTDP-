"""Step-up challenge issuance and TOTP verification.

Challenges live in Redis (shared across gunicorn workers, TTL-expiring), are
limited to MAX_ATTEMPTS wrong codes, and are one-shot. TOTP secrets are derived
per user from AZTDP_TOTP_MASTER_SECRET. The resulting step-up token is an HS256
JWT bound to the user *and* the access token (jti hash) it was issued for.

Open question Q1: enrollment (showing the derived secret to the user's
authenticator) is not implemented; WebAuthn is not covered.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json as _json
import os
import struct
import time
from typing import Optional, Tuple

MAX_ATTEMPTS = 5
_CHALLENGE_TTL = 300  # seconds
_STEP_UP_TOKEN_TTL = 300
_TOTP_STEP = 30
_TOTP_DIGITS = 6
_KEY_PREFIX = "stepup:chal:"


class StepUpConfigError(RuntimeError):
    pass


def load_config(debug: bool) -> Tuple[str, str]:
    signing = os.getenv("AZTDP_STEPUP_SIGNING_KEY", "")
    master = os.getenv("AZTDP_TOTP_MASTER_SECRET", "")
    if not debug and (not signing or not master):
        raise StepUpConfigError(
            "AZTDP_STEPUP_SIGNING_KEY and AZTDP_TOTP_MASTER_SECRET are required"
        )
    return signing or "dev-only-signing-key", master or "dev-only-master-secret"


def _debug() -> bool:
    from django.conf import settings

    return bool(getattr(settings, "DEBUG", False))


_SIGNING_KEY, _MASTER = load_config(_debug())

_store = None


def get_store():
    """Return the shared Redis client (tests monkeypatch this)."""
    global _store
    if _store is None:
        import redis
        from django.conf import settings

        url = settings.AZTDP.get("REDIS_URL", "")
        if not url:
            raise StepUpConfigError("AZTDP_REDIS_URL is required for step-up")
        _store = redis.Redis.from_url(url, decode_responses=True, socket_timeout=1.0)
    return _store


def _user_secret(user_id: str) -> bytes:
    # Per-user secret derived from the master secret; enrollment is Open Question Q1.
    return hmac.new(_MASTER.encode(), user_id.encode(), hashlib.sha256).digest()


def create_challenge(challenge_id: str, user_id: str, jti_hash: str = "") -> None:
    r = get_store()
    key = _KEY_PREFIX + challenge_id
    pipe = r.pipeline()
    pipe.hset(key, mapping={"user_id": user_id, "attempts": 0, "jti_hash": jti_hash})
    pipe.expire(key, _CHALLENGE_TTL)
    pipe.execute()


def get_challenge_user(challenge_id: str) -> str:
    """Return the user_id the challenge was issued to ('' if none)."""
    return get_store().hget(_KEY_PREFIX + challenge_id, "user_id") or ""


def challenge_exists(challenge_id: str, user_id: str) -> bool:
    return bool(user_id) and get_challenge_user(challenge_id) == user_id


def verify_challenge(challenge_id: str, totp_code: str, user_id: str) -> Optional[str]:
    """Validate a TOTP code; returns a step-up token or None.

    Every call against an existing challenge counts as an attempt; the challenge
    is destroyed after MAX_ATTEMPTS.
    """
    r = get_store()
    key = _KEY_PREFIX + challenge_id
    entry = r.hgetall(key)
    if not entry or entry.get("user_id") != user_id:
        return None
    if r.hincrby(key, "attempts", 1) > MAX_ATTEMPTS:
        r.delete(key)
        return None
    if not _verify_totp(totp_code, _user_secret(user_id)):
        return None
    if r.delete(key) != 1:  # one-shot, even under concurrent correct submissions
        return None
    return _mint_step_up_token(user_id, challenge_id, entry.get("jti_hash", ""))


# ── TOTP implementation (RFC 6238 / RFC 4226) ────────────────────────────────

def _verify_totp(code: str, secret: bytes, window: int = 1) -> bool:
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


def _hotp(secret: bytes, counter: int) -> str:
    """Compute an HOTP code per RFC 4226."""
    key = secret
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10 ** _TOTP_DIGITS)).zfill(_TOTP_DIGITS)


# ── Step-up token (compact HS256 JWT) ────────────────────────────────────────

def _mint_step_up_token(user_id: str, challenge_id: str, jti_hash: str = "") -> str:
    """Issue a minimal HS256 JWT for step-up proof.

    We avoid a full PyJWT dependency by constructing the token manually.
    This is a self-contained claim that the enforcement middleware can verify.
    """
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "challenge_id": challenge_id,
        "jti_hash": jti_hash,
        "purpose": "step_up",
        "iat": int(time.time()),
        "exp": int(time.time()) + _STEP_UP_TOKEN_TTL,
    }

    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    segments = _b64(_json.dumps(header).encode()) + "." + _b64(_json.dumps(payload).encode())
    sig = hmac.new(_SIGNING_KEY.encode("utf-8"), segments.encode("ascii"), hashlib.sha256).digest()
    return segments + "." + _b64(sig)


def verify_step_up_token(token: str, user_id: str, access_jti_hash: str) -> bool:
    """Verify a previously issued step-up token."""
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
        if not access_jti_hash or not hmac.compare_digest(
            str(payload.get("jti_hash", "")), access_jti_hash
        ):
            return False
        if payload.get("exp", 0) < time.time():
            return False
        return True
    except Exception:
        return False


# ── Test helpers ─────────────────────────────────────────────────────────────

def current_totp_for_tests(user_id: str) -> str:
    return _hotp(_user_secret(user_id), int(time.time()) // _TOTP_STEP)


def mint_for_tests(user_id: str, challenge_id: str, jti_hash: str) -> str:
    return _mint_step_up_token(user_id, challenge_id, jti_hash)
