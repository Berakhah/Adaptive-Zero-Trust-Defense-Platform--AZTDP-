from unittest.mock import MagicMock, patch

import pytest
from core.middleware import RiskAuthzMiddleware
from core.risk_client import RiskClientError
from django.http import HttpResponse
from django.test import RequestFactory


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


@pytest.mark.parametrize("path", ["/health/", "/metrics", "/v1/auth/step-up/verify"])
def test_allowlist_matches_exact_paths(rf, path):
    mw = _build_middleware()
    assert mw(rf.get(path)).status_code == 200


@pytest.mark.parametrize(
    "path",
    ["/healthz", "/health/x", "/healthcheck-admin", "/metrics/extra", "/metricsfoo", "/health/../v1/admin/flags"],
)
def test_allowlist_does_not_match_path_prefixes(rf, path):
    """A path that merely starts with an allowlisted one must still require a token."""
    mw = _build_middleware()
    assert mw(rf.get(path)).status_code == 401


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


# --- Task 9: durable revocation -------------------------------------------

def _revoke_decision(mw, exp=1_760_000_000):
    mw.verifier.verify = MagicMock(
        return_value={
            "sub": "user-1",
            "jti": "jti-abc",
            "session_state": "sess",
            "roles": ["user"],
            "exp": exp,
        }
    )
    mw.risk_client.evaluate = MagicMock(
        return_value={"risk_score": 0.99, "trust_score": 0.01, "anomaly_score": 0.0}
    )
    mw.policy_client.decide = MagicMock(
        return_value={"decision": {"decision": "revoke", "reason": {"rule": "very_high_risk"}}}
    )


def test_revoke_sends_token_exp_as_expires_at(rf):
    mw = _build_middleware()
    _revoke_decision(mw, exp=1_760_000_123)
    mw.revocation_client.revoke = MagicMock(return_value={"status": "revoked"})
    response = mw(_request(rf))
    assert response.status_code == 403
    payload = mw.revocation_client.revoke.call_args.args[0]
    assert payload["expires_at"] == 1_760_000_123
    assert payload["source"] == "policy"


def test_revoke_not_persisted_still_denies_and_logs_error(rf, caplog):
    from core.revocation_client import RevocationClientError

    mw = _build_middleware()
    _revoke_decision(mw)
    mw.revocation_client.revoke = MagicMock(
        side_effect=RevocationClientError("revocation_not_persisted")
    )
    with caplog.at_level("ERROR", logger="aztdp.middleware"):
        response = mw(_request(rf))
    assert response.status_code == 403
    assert b"token_revoked" in response.content
    assert any(
        r.levelname == "ERROR" and "revocation_not_persisted" in r.getMessage()
        for r in caplog.records
    )


def test_revocation_client_maps_503_to_not_persisted():
    from core.revocation_client import RevocationClientError, TokenRevocationClient

    client = TokenRevocationClient("http://gw/v1/tokens/revoke", 0.1, 0.1, internal_token="t")
    resp = MagicMock(status_code=503)
    client.session.post = MagicMock(return_value=resp)
    with pytest.raises(RevocationClientError) as excinfo:
        client.revoke({"token_jti_hash": "h", "reason": "policy", "source": "policy"})
    assert excinfo.value.code == "revocation_not_persisted"


def test_revocation_client_maps_network_error_to_unavailable():
    import requests
    from core.revocation_client import RevocationClientError, TokenRevocationClient

    client = TokenRevocationClient("http://gw/v1/tokens/revoke", 0.1, 0.1)
    client.session.post = MagicMock(side_effect=requests.ConnectionError("down"))
    with pytest.raises(RevocationClientError) as excinfo:
        client.revoke({"token_jti_hash": "h", "reason": "policy", "source": "policy"})
    assert excinfo.value.code == "revocation_unavailable"


@pytest.mark.parametrize("path", ["/ui", "/ui/", "/ui/app.js", "/ui/static/css/site.css"])
def test_debug_ui_subtree_is_allowlisted(rf, settings, path):
    settings.AZTDP_ALLOWLIST_PATHS = ["/health", "/ui"]
    settings.AZTDP_ALLOWLIST_SUBTREES = ["/ui"]
    assert _build_middleware()(rf.get(path)).status_code == 200


@pytest.mark.parametrize("path", ["/uix", "/ui-admin/x", "/ui/../v1/admin/flags", "/ui/./x"])
def test_debug_ui_subtree_respects_segment_boundary(rf, settings, path):
    settings.AZTDP_ALLOWLIST_PATHS = ["/health", "/ui"]
    settings.AZTDP_ALLOWLIST_SUBTREES = ["/ui"]
    assert _build_middleware()(rf.get(path)).status_code == 401


def test_ui_subtree_not_allowlisted_without_setting(rf, settings):
    settings.AZTDP_ALLOWLIST_PATHS = ["/health"]
    settings.AZTDP_ALLOWLIST_SUBTREES = []
    assert _build_middleware()(rf.get("/ui/app.js")).status_code == 401
