import fakeredis
import pytest
from core import stepup


@pytest.fixture(autouse=True)
def _store(monkeypatch):
    shared = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(stepup, "get_store", lambda: shared)


def test_challenge_visible_to_another_worker():
    stepup.create_challenge("c1", "u1")           # "worker A"
    assert stepup.challenge_exists("c1", "u1")     # "worker B" shares the store


def test_challenge_visible_via_independent_connection(monkeypatch):
    server = fakeredis.FakeServer()
    a = fakeredis.FakeRedis(server=server, decode_responses=True)
    b = fakeredis.FakeRedis(server=server, decode_responses=True)
    monkeypatch.setattr(stepup, "get_store", lambda: a)
    stepup.create_challenge("cw", "u1")
    monkeypatch.setattr(stepup, "get_store", lambda: b)
    assert stepup.challenge_exists("cw", "u1")
    assert stepup.verify_challenge("cw", stepup.current_totp_for_tests("u1"), "u1")
    monkeypatch.setattr(stepup, "get_store", lambda: a)
    assert not stepup.challenge_exists("cw", "u1")  # consumed cross-worker


def test_attempt_limit_destroys_challenge():
    stepup.create_challenge("c2", "u1")
    for _ in range(stepup.MAX_ATTEMPTS):
        assert stepup.verify_challenge("c2", "000000", "u1") is None
    good = stepup.current_totp_for_tests("u1")
    assert stepup.verify_challenge("c2", good, "u1") is None   # too late


def test_token_bound_to_access_token():
    tok = stepup.mint_for_tests("u1", "c3", jti_hash="AAA")
    assert stepup.verify_step_up_token(tok, "u1", "AAA") is True
    assert stepup.verify_step_up_token(tok, "u1", "BBB") is False


def test_missing_secrets_fail_closed(monkeypatch):
    monkeypatch.delenv("AZTDP_STEPUP_SIGNING_KEY", raising=False)
    with pytest.raises(stepup.StepUpConfigError):
        stepup.load_config(debug=False)


def test_missing_master_secret_fail_closed(monkeypatch):
    monkeypatch.setenv("AZTDP_STEPUP_SIGNING_KEY", "k")
    monkeypatch.delenv("AZTDP_TOTP_MASTER_SECRET", raising=False)
    with pytest.raises(stepup.StepUpConfigError):
        stepup.load_config(debug=False)


def test_per_user_secrets_differ():
    assert stepup._user_secret("u1") != stepup._user_secret("u2")


def test_challenge_jti_hash_flows_into_token():
    stepup.create_challenge("c4", "u1", jti_hash="JJJ")
    tok = stepup.verify_challenge("c4", stepup.current_totp_for_tests("u1"), "u1")
    assert stepup.verify_step_up_token(tok, "u1", "JJJ") is True
    assert stepup.verify_step_up_token(tok, "u1", "") is False


# ── view: user_id from stored challenge, per-IP throttle ─────────────────────

def _post(rf, body, ip="203.0.113.9"):
    import json

    from core.views import step_up_verify
    req = rf.post("/v1/auth/step-up/verify", data=json.dumps(body),
                  content_type="application/json", REMOTE_ADDR=ip)
    return step_up_verify(req)


def test_view_rejects_body_user_mismatch(rf):
    stepup.create_challenge("v1", "u1")
    code = stepup.current_totp_for_tests("u1")
    assert _post(rf, {"challenge_id": "v1", "code": code, "user_id": "u2"}).status_code == 401
    assert stepup.challenge_exists("v1", "u1")  # not consumed


def test_view_works_without_body_user_id(rf):
    stepup.create_challenge("v2", "u1")
    code = stepup.current_totp_for_tests("u1")
    r = _post(rf, {"challenge_id": "v2", "code": code})
    assert r.status_code == 200


def test_view_per_ip_throttle(rf):
    for _ in range(20):
        assert _post(rf, {"challenge_id": "nope", "code": "000000"}).status_code == 401
    assert _post(rf, {"challenge_id": "nope", "code": "000000"}).status_code == 429
    assert _post(rf, {"challenge_id": "nope", "code": "000000"}, ip="198.51.100.1").status_code == 401


# ── fix round 1: per-user lockout, atomic counters, spoof-proof IP key ───────

def test_per_user_lockout_across_challenges():
    for i in range(stepup.MAX_USER_FAILURES):
        cid = f"lk{i}"
        stepup.create_challenge(cid, "victim")
        assert stepup.verify_challenge(cid, "000000", "victim") is None
    stepup.create_challenge("lk-final", "victim")
    good = stepup.current_totp_for_tests("victim")
    assert stepup.verify_challenge("lk-final", good, "victim") is None  # locked out


def test_lockout_does_not_affect_other_user():
    for i in range(stepup.MAX_USER_FAILURES):
        stepup.create_challenge(f"o{i}", "victim")
        stepup.verify_challenge(f"o{i}", "000000", "victim")
    stepup.create_challenge("other-c", "bystander")
    assert stepup.verify_challenge("other-c", stepup.current_totp_for_tests("bystander"), "bystander")


def test_unknown_challenge_does_not_count_against_user():
    stepup.verify_challenge("missing", "000000", "victim")
    assert stepup.get_store().get("stepup:user:victim") is None


def test_counter_without_ttl_gets_ttl():
    stepup.get_store().set("stepup:user:u9", 3)  # orphan key, no TTL
    assert stepup.get_store().ttl("stepup:user:u9") == -1
    stepup.bump_counter(stepup.get_store(), "stepup:user:u9", 900)
    assert 0 < stepup.get_store().ttl("stepup:user:u9") <= 900


def test_ip_key_without_ttl_does_not_lock_forever(rf):
    stepup.get_store().set("stepup:ip:203.0.113.9", 500)  # stale, no TTL
    _post(rf, {"challenge_id": "nope", "code": "000000"})
    assert 0 < stepup.get_store().ttl("stepup:ip:203.0.113.9") <= 60


def test_spoofed_headers_ignored_when_not_from_trusted_proxy(rf):
    import json

    from core.views import step_up_verify
    for i in range(3):
        req = rf.post("/v1/auth/step-up/verify",
                      data=json.dumps({"challenge_id": "nope", "code": "000000"}),
                      content_type="application/json", REMOTE_ADDR="203.0.113.50",
                      HTTP_X_CLIENT_IP=f"10.9.9.{i}", HTTP_X_FORWARDED_FOR=f"10.8.8.{i}")
        step_up_verify(req)
    assert stepup.get_store().get("stepup:ip:203.0.113.50") == "3"
    assert not list(stepup.get_store().scan_iter("stepup:ip:10.*"))


# ── TOTP replay (RFC 6238 5.2) ───────────────────────────────────────────────

def test_totp_code_cannot_be_replayed_on_another_challenge():
    stepup.create_challenge("r1", "u1")
    stepup.create_challenge("r2", "u1")
    code = stepup.current_totp_for_tests("u1")
    assert stepup.verify_challenge("r1", code, "u1")
    assert stepup.verify_challenge("r2", code, "u1") is None


def test_totp_replay_counts_toward_user_lockout():
    code = stepup.current_totp_for_tests("u1")
    stepup.create_challenge("r3", "u1")
    assert stepup.verify_challenge("r3", code, "u1")
    for i in range(stepup.MAX_USER_FAILURES):
        stepup.create_challenge(f"rp{i}", "u1")
        assert stepup.verify_challenge(f"rp{i}", code, "u1") is None
    stepup.create_challenge("rp-final", "u1")
    assert stepup.verify_challenge("rp-final", stepup.current_totp_for_tests("u1"), "u1") is None


def test_totp_replay_is_per_user():
    stepup.create_challenge("r4", "u1")
    stepup.create_challenge("r5", "u2")
    assert stepup.verify_challenge("r4", stepup.current_totp_for_tests("u1"), "u1")
    assert stepup.verify_challenge("r5", stepup.current_totp_for_tests("u2"), "u2")
