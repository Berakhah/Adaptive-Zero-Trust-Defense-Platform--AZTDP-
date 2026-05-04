from unittest.mock import MagicMock, patch

import pytest

from django.http import HttpResponse
from django.test import RequestFactory

from core.middleware import RiskAuthzMiddleware
from core.risk_client import RiskClient, RiskClientError
from core.policy_client import PolicyClient


def _ok_view(request):
    return HttpResponse("ok")


def _build_middleware():
    with patch("core.middleware.JwtVerifier") as Verifier:
        Verifier.return_value.verify.return_value = {
            "sub": "user-1",
            "jti": "jti-abc",
            "session_state": "sess",
            "roles": ["user"],
        }
        mw = RiskAuthzMiddleware(_ok_view)
    return mw


def _request(rf, path="/v1/payments/1"):
    return rf.get(
        path,
        HTTP_AUTHORIZATION="Bearer token-abc",
        HTTP_USER_AGENT="ua",
        HTTP_X_CLIENT_IP="1.1.1.1",
        HTTP_X_GEO="US-CA",
    )


@pytest.fixture
def rf():
    return RequestFactory()


def test_allowlist_passes_through(rf):
    mw = _build_middleware()
    response = mw(rf.get("/health"))
    assert response.status_code == 200


def test_missing_token_returns_401(rf):
    mw = _build_middleware()
    response = mw(rf.get("/v1/payments/1"))
    assert response.status_code == 401


def test_replay_returns_403_even_with_fail_open(rf):
    """Critical: replay (HTTP 409 from risk engine) must be hard-deny regardless of fail_open."""
    mw = _build_middleware()
    mw.fail_open = True
    mw.risk_client.evaluate = MagicMock(
        side_effect=RiskClientError("replay_detected")
    )
    response = mw(_request(rf))
    assert response.status_code == 403


def test_allow_path_invokes_handler(rf):
    mw = _build_middleware()
    mw.risk_client.evaluate = MagicMock(
        return_value={"risk_score": 0.1, "trust_score": 0.9, "anomaly_score": 0.0}
    )
    mw.policy_client.decide = MagicMock(
        return_value={"decision": {"decision": "allow", "reason": {}}}
    )
    response = mw(_request(rf))
    assert response.status_code == 200


def test_deny_path_returns_403(rf):
    mw = _build_middleware()
    mw.risk_client.evaluate = MagicMock(
        return_value={"risk_score": 0.95, "trust_score": 0.05, "anomaly_score": 0.0}
    )
    mw.policy_client.decide = MagicMock(
        return_value={"decision": {"decision": "deny", "reason": {"rule": "high_risk"}}}
    )
    response = mw(_request(rf))
    assert response.status_code == 403


def test_stepup_returns_401_with_challenge(rf):
    mw = _build_middleware()
    mw.risk_client.evaluate = MagicMock(
        return_value={"risk_score": 0.7, "trust_score": 0.3, "anomaly_score": 0.0}
    )
    mw.policy_client.decide = MagicMock(
        return_value={"decision": {"decision": "stepup", "reason": {"rule": "stepup_required"}}}
    )
    response = mw(_request(rf))
    assert response.status_code == 401
    body = response.content.decode()
    assert "STEP_UP_REQUIRED" in body
