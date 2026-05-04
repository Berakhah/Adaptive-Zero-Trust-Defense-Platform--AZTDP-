"""Pytest assertions for attack scenario HTTP outcomes.

Run against a live stack:
    AZTDP_BASE_URL=http://localhost:8010 \
    AZTDP_USERNAME=user1 AZTDP_PASSWORD=password \
    pytest services/attack-sim/test_attack_outcomes.py
"""
import os

import pytest

from utils import base_url, default_headers, get_access_token, request_json, sleep_between


pytestmark = pytest.mark.skipif(
    not os.getenv("AZTDP_RUN_LIVE_TESTS"),
    reason="set AZTDP_RUN_LIVE_TESTS=1 to run live attack tests",
)


def _url(path: str) -> str:
    return f"{base_url().rstrip('/')}{path}"


def test_low_risk_request_returns_200():
    token = get_access_token()
    headers = default_headers(token, "203.0.113.10", "aztdp-test", "US-CA")
    response = request_json("GET", _url("/v1/payments/1"), headers)
    assert response.status_code == 200


def test_token_replay_returns_403():
    token = get_access_token()
    h1 = default_headers(token, "203.0.113.10", "aztdp-test-a", "US-CA")
    h2 = default_headers(token, "198.51.100.22", "aztdp-test-b", "US-NY")
    request_json("GET", _url("/v1/payments/1"), h1)
    sleep_between()
    response = request_json("GET", _url("/v1/payments/1"), h2)
    assert response.status_code == 403


def test_privilege_escalation_returns_403():
    admin_user = os.getenv("AZTDP_USERNAME", "user1")
    if admin_user.startswith("admin"):
        pytest.skip("test requires non-admin credentials")
    token = get_access_token()
    headers = default_headers(token, "203.0.113.10", "aztdp-test", "US-CA")
    response = request_json("POST", _url("/v1/admin/revoke"), headers)
    assert response.status_code in (401, 403)
