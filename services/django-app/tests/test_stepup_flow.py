"""P5.4 — Step-up MFA unit tests.

Tests the full challenge → TOTP verify → step-up token flow without a live
network stack. Uses the HOTP/TOTP implementation in core.stepup directly.
"""
import time
import os
import pytest

os.environ.setdefault("AZTDP_TOTP_SECRET", "JBSWY3DPEHPK3PXP")  # well-known test secret
os.environ.setdefault("AZTDP_STEPUP_SIGNING_KEY", "test-signing-key")

from core.stepup import (
    _challenges,
    _hotp,
    _TOTP_STEP,
    _TOTP_DIGITS,
    create_challenge,
    verify_challenge,
    verify_step_up_token,
)


def _current_totp(secret: str = "JBSWY3DPEHPK3PXP") -> str:
    """Compute the current valid TOTP code for the test secret."""
    counter = int(time.time()) // _TOTP_STEP
    return _hotp(secret, counter)


class TestStepUpChallengeLifecycle:
    def setup_method(self):
        _challenges.clear()

    def test_create_challenge_stores_entry(self):
        entry = create_challenge("chal-1", "user-abc")
        assert entry["challenge_id"] == "chal-1"
        assert entry["user_id"] == "user-abc"
        assert not entry["verified"]
        assert "chal-1" in _challenges

    def test_verify_challenge_returns_token_on_valid_totp(self):
        create_challenge("chal-ok", "user-abc")
        code = _current_totp()
        token = verify_challenge("chal-ok", code, "user-abc")
        assert token is not None, "Valid TOTP should produce a step-up token"
        assert len(token.split(".")) == 3, "Token must be a 3-segment JWT"

    def test_verify_challenge_fails_for_wrong_user(self):
        create_challenge("chal-x", "user-abc")
        code = _current_totp()
        result = verify_challenge("chal-x", code, "user-OTHER")
        assert result is None

    def test_verify_challenge_fails_for_unknown_challenge(self):
        result = verify_challenge("no-such-challenge", "000000", "user-abc")
        assert result is None

    def test_verify_challenge_is_one_shot(self):
        """A challenge can only be consumed once."""
        create_challenge("chal-once", "user-abc")
        code = _current_totp()
        first = verify_challenge("chal-once", code, "user-abc")
        second = verify_challenge("chal-once", code, "user-abc")
        assert first is not None
        assert second is None, "Challenge must be single-use"

    def test_verify_challenge_rejects_wrong_code(self):
        create_challenge("chal-bad", "user-abc")
        result = verify_challenge("chal-bad", "000000", "user-abc")
        assert result is None

    def test_expired_challenge_rejected(self, monkeypatch):
        """Challenges older than TTL must be rejected."""
        create_challenge("chal-old", "user-abc")
        # Fast-forward time beyond TTL
        old_time = _challenges["chal-old"]["created_at"]
        _challenges["chal-old"]["created_at"] = old_time - 400  # > 300s TTL
        code = _current_totp()
        result = verify_challenge("chal-old", code, "user-abc")
        assert result is None


class TestStepUpToken:
    def setup_method(self):
        _challenges.clear()

    def test_issued_token_verifies_for_correct_user(self):
        create_challenge("chal-tok", "user-z")
        code = _current_totp()
        token = verify_challenge("chal-tok", code, "user-z")
        assert token is not None
        assert verify_step_up_token(token, "user-z") is True

    def test_token_rejected_for_wrong_user(self):
        create_challenge("chal-tok2", "user-z")
        code = _current_totp()
        token = verify_challenge("chal-tok2", code, "user-z")
        assert token is not None
        assert verify_step_up_token(token, "user-WRONG") is False

    def test_tampered_token_rejected(self):
        create_challenge("chal-tok3", "user-z")
        code = _current_totp()
        token = verify_challenge("chal-tok3", code, "user-z")
        # Flip last char of signature
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        assert verify_step_up_token(tampered, "user-z") is False

    def test_expired_token_rejected(self, monkeypatch):
        """Tokens whose exp claim is in the past are rejected."""
        from core import stepup as su

        create_challenge("chal-exp", "user-z")
        code = _current_totp()
        token = verify_challenge("chal-exp", code, "user-z")
        assert token is not None

        # Monkeypatch time so token appears expired
        original_time = time.time
        monkeypatch.setattr(time, "time", lambda: original_time() + 700)  # > 600s TTL
        assert verify_step_up_token(token, "user-z") is False

    def test_garbage_token_rejected(self):
        assert verify_step_up_token("not.a.jwt", "user-z") is False
        assert verify_step_up_token("", "user-z") is False
        assert verify_step_up_token("a.b", "user-z") is False
