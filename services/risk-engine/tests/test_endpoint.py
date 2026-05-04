from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from risk_engine import app as app_module


client = TestClient(app_module.app)


def _payload(**overrides):
    body = {
        "request_id": "r1",
        "token_jti_hash": "h1",
        "ip": "1.1.1.1",
        "geo": "US-CA",
        "user_agent_hash": "ua-1",
        "endpoint": {"service": "django", "method": "GET", "path": "/v1/payments/1", "sensitivity": 2},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    body.update(overrides)
    return body


def test_health():
    assert client.get("/health").status_code == 200


def test_evaluate_returns_score_and_anomaly_field():
    with patch("risk_engine.app.score_anomaly", return_value=None):
        r = client.post("/v1/risk/evaluate", json=_payload(token_jti_hash="t-fresh"))
    assert r.status_code == 200
    body = r.json()
    assert "risk_score" in body
    assert "trust_score" in body
    assert body["anomaly_score"] == 0.0


def test_replay_returns_409():
    # First call sets last_seen, second with different IP within window triggers replay.
    token = "t-replay"
    p1 = _payload(token_jti_hash=token, ip="1.1.1.1")
    p2 = _payload(token_jti_hash=token, ip="2.2.2.2")
    with patch("risk_engine.app.score_anomaly", return_value=None):
        client.post("/v1/risk/evaluate", json=p1)
        r = client.post("/v1/risk/evaluate", json=p2)
    assert r.status_code == 409
