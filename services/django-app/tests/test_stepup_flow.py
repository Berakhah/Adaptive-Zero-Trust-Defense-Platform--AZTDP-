import time

from core.stepup import (
    create_challenge,
    current_totp_for_tests,
    verify_challenge,
    verify_step_up_token,
)

JTI = "jti-hash-1"


def _current_totp(user: str = "user-abc") -> str:
    return current_totp_for_tests(user)


def _entry(store, cid):
    return store.hgetall(f"stepup:chal:{cid}")


class TestStepUpChallengeLifecycle:
    def test_create_challenge_stores_entry(self, _fake_stepup_store):
        create_challenge("chal-1", "user-abc", JTI)
        entry = _entry(_fake_stepup_store, "chal-1")
        assert entry["user_id"] == "user-abc"
        assert entry["jti_hash"] == JTI
        assert entry["attempts"] == "0"
        assert 0 < _fake_stepup_store.ttl("stepup:chal:chal-1") <= 300

    def test_verify_challenge_returns_token_on_valid_totp(self):
        create_challenge("chal-ok", "user-abc")
        token = verify_challenge("chal-ok", _current_totp(), "user-abc")
        assert token is not None, "Valid TOTP should produce a step-up token"
        assert len(token.split(".")) == 3, "Token must be a 3-segment JWT"

    def test_verify_challenge_fails_for_wrong_user(self):
        create_challenge("chal-x", "user-abc")
        result = verify_challenge("chal-x", _current_totp(), "user-OTHER")
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

    def test_expired_challenge_rejected(self, _fake_stepup_store):
        """Challenges past their Redis TTL must be rejected."""
        create_challenge("chal-old", "user-abc")
        _fake_stepup_store.delete("stepup:chal:chal-old")  # TTL elapsed
        result = verify_challenge("chal-old", _current_totp(), "user-abc")
        assert result is None


class TestStepUpToken:
    def test_issued_token_verifies_for_correct_user(self):
        create_challenge("chal-tok", "user-z", JTI)
        code = _current_totp("user-z")
        token = verify_challenge("chal-tok", code, "user-z")
        assert token is not None
        assert verify_step_up_token(token, "user-z", JTI) is True

    def test_token_rejected_for_wrong_user(self):
        create_challenge("chal-tok2", "user-z", JTI)
        code = _current_totp("user-z")
        token = verify_challenge("chal-tok2", code, "user-z")
        assert token is not None
        assert verify_step_up_token(token, "user-WRONG", JTI) is False

    def test_tampered_token_rejected(self):
        create_challenge("chal-tok3", "user-z", JTI)
        code = _current_totp("user-z")
        token = verify_challenge("chal-tok3", code, "user-z")
        # Flip last char of signature
        sig_start = token.rindex(".") + 1
        mid = sig_start + 5  # last b64 char carries padding bits; flip a full one
        tampered = token[:mid] + ("A" if token[mid] != "A" else "B") + token[mid + 1:]
        assert verify_step_up_token(tampered, "user-z", JTI) is False

    def test_expired_token_rejected(self, monkeypatch):
        """Tokens whose exp claim is in the past are rejected."""
        create_challenge("chal-exp", "user-z", JTI)
        code = _current_totp("user-z")
        token = verify_challenge("chal-exp", code, "user-z")
        assert token is not None

        # Monkeypatch time so token appears expired
        original_time = time.time
        monkeypatch.setattr(time, "time", lambda: original_time() + 400)  # > 300s TTL
        assert verify_step_up_token(token, "user-z", JTI) is False

    def test_garbage_token_rejected(self):
        assert verify_step_up_token("not.a.jwt", "user-z", JTI) is False
        assert verify_step_up_token("", "user-z", JTI) is False
        assert verify_step_up_token("a.b", "user-z", JTI) is False
