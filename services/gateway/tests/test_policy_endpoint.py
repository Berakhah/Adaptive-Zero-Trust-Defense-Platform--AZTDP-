from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from gateway import app as app_module

client = TestClient(app_module.app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_revoked_token_short_circuits_to_revoke(auth_headers):
    app_module.revocations.revoke("abc")
    body = {
        "input": {
            "request_id": "r1",
            "context": {"token_jti_hash": "abc"},
        }
    }
    r = client.post("/v1/policy/decision", json=body, headers=auth_headers)
    assert r.status_code == 200
    decision = r.json()["decision"]
    assert decision["decision"] == "revoke"


def test_decision_passes_through_opa_allow(auth_headers):
    body = {
        "input": {
            "request_id": "r2",
            "context": {"token_jti_hash": "fresh"},
        }
    }
    fake = {"result": {"decision": "allow", "reason": {"rule": "default_allow"}}}
    with patch.object(app_module, "evaluate", return_value=fake):
        r = client.post("/v1/policy/decision", json=body, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["decision"]["decision"] == "allow"


def test_revoke_endpoint(auth_headers):
    r = client.post(
        "/v1/tokens/revoke",
        json={"token_jti_hash": "xyz", "reason": "test", "source": "manual"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    r = client.get("/v1/tokens/revoked/xyz", headers=auth_headers)
    assert r.json()["revoked"] is True


def test_protected_route_rejects_missing_token():
    r = client.post("/v1/policy/decision", json={"input": {}})
    assert r.status_code == 401




@pytest.mark.parametrize("bad", [-1, 99_999_999_999_999, 4_102_444_801])
def test_revoke_request_rejects_out_of_range_expires_at(bad):
    from gateway.app import RevokeRequest

    with pytest.raises(ValidationError):
        RevokeRequest(token_jti_hash="h", reason="r", source="admin", expires_at=bad)


def test_revoke_request_accepts_normal_and_missing_expires_at():
    from gateway.app import RevokeRequest

    assert RevokeRequest(token_jti_hash="h", reason="r", source="admin", expires_at=1_900_000_000)
    assert RevokeRequest(token_jti_hash="h", reason="r", source="admin").expires_at is None
