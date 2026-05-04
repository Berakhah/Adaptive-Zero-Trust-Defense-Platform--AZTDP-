from unittest.mock import patch

from fastapi.testclient import TestClient

from gateway import app as app_module


client = TestClient(app_module.app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_revoked_token_short_circuits_to_revoke():
    app_module.revocations.revoke("abc")
    body = {
        "input": {
            "request_id": "r1",
            "context": {"token_jti_hash": "abc"},
        }
    }
    r = client.post("/v1/policy/decision", json=body)
    assert r.status_code == 200
    decision = r.json()["decision"]
    assert decision["decision"] == "revoke"


def test_decision_passes_through_opa_allow():
    body = {
        "input": {
            "request_id": "r2",
            "context": {"token_jti_hash": "fresh"},
        }
    }
    fake = {"result": {"decision": "allow", "reason": {"rule": "default_allow"}}}
    with patch.object(app_module, "evaluate", return_value=fake):
        r = client.post("/v1/policy/decision", json=body)
    assert r.status_code == 200
    assert r.json()["decision"]["decision"] == "allow"


def test_revoke_endpoint():
    r = client.post(
        "/v1/tokens/revoke",
        json={"token_jti_hash": "xyz", "reason": "test", "source": "unit"},
    )
    assert r.status_code == 200
    r = client.get("/v1/tokens/revoked/xyz")
    assert r.json()["revoked"] is True
