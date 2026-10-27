import re


def test_requires_internal_token(client):
    assert client.post("/v1/telemetry/event", json={"event_type": "risk_eval", "service": "t"}).status_code == 401


def test_invalid_event_type_400(client, auth_headers):
    r = client.post("/v1/telemetry/event", json={"event_type": "nope", "service": "t"}, headers=auth_headers)
    assert r.status_code == 400


def test_policy_decision_is_denormalized(client, auth_headers, stub_pool):
    body = {"event_type": "policy_decision", "service": "gateway", "request_id": "r1",
            "payload": {"decision": "deny", "reason": {"rule": "admin_required"}}}
    assert client.post("/v1/telemetry/event", json=body, headers=auth_headers).status_code == 200
    assert any("INSERT INTO policy_decisions" in sql for sql, _ in stub_pool.executed)


def test_db_error_returns_500(client, auth_headers, stub_pool):
    stub_pool.fail_next = True
    body = {"event_type": "risk_eval", "service": "t", "request_id": "r"}
    assert client.post("/v1/telemetry/event", json=body, headers=auth_headers).status_code == 500


def test_session_update_params_are_type_inferable(client, auth_headers, stub_pool):
    """Regression: Postgres cannot infer the type of a bare `%s IS NULL` parameter
    ("could not determine data type of parameter"), which made every event with a
    session_id and user_id fail with 500 so `sessions` was never filled."""
    body = {"event_type": "policy_decision", "service": "gateway", "request_id": "r1",
            "session_id": "s1", "user_id": "u1",
            "payload": {"decision": "deny"}}
    assert client.post("/v1/telemetry/event", json=body, headers=auth_headers).status_code == 200
    sql = next(s for s, _ in stub_pool.executed if "INSERT INTO sessions" in s)
    assert not re.search(r"%s\s+IS\s+NULL", sql, re.IGNORECASE)
    assert "(sessions.decision_counts->>%s)" not in sql
