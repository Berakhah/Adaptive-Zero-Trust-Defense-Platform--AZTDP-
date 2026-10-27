from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from risk_engine import anomaly_client, config


def _payload(**overrides):
    body = {
        "request_id": "r",
        "user_id": "u",
        "session_id": "s",
        "token_jti_hash": "h",
        "ip": "1.1.1.1",
        "geo": "US-CA",
        "user_agent_hash": "ua-1",
        "endpoint": {"service": "x", "method": "GET", "path": "/p", "sensitivity": 3},
        "timestamp": datetime(2026, 5, 3, 14, 0, tzinfo=timezone.utc).isoformat(),
    }
    body.update(overrides)
    return body


def test_returns_none_when_no_anomaly_url(monkeypatch):
    monkeypatch.setattr(config, "ANOMALY_URL", "")
    assert anomaly_client.score(_payload(), None) is None


def test_returns_none_on_request_error(monkeypatch):
    monkeypatch.setattr(config, "ANOMALY_URL", "http://anomaly:8080")
    with patch.object(anomaly_client.requests, "post", side_effect=Exception("boom")):
        assert anomaly_client.score(_payload(), None) is None


def test_returns_payload_on_success(monkeypatch):
    monkeypatch.setattr(config, "ANOMALY_URL", "http://anomaly:8080")
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"anomaly_score": 0.5, "is_anomalous": False, "model_version": "v1.0", "confidence": 0.9}
    with patch.object(anomaly_client.requests, "post", return_value=resp):
        out = anomaly_client.score(_payload(), None)
    assert out is not None
    assert out["anomaly_score"] == 0.5


def _calls(outcome):
    return anomaly_client.ANOMALY_CALLS.labels(outcome=outcome)._value.get()


def _failing_outcome(monkeypatch, outcome, **post_kwargs):
    monkeypatch.setattr(config, "ANOMALY_URL", "http://anomaly:8080")
    before = _calls(outcome)
    with patch.object(anomaly_client.requests, "post", **post_kwargs):
        assert anomaly_client.score(_payload(), None) is None
    assert _calls(outcome) == before + 1


def test_counts_disabled(monkeypatch):
    monkeypatch.setattr(config, "ANOMALY_URL", "")
    before = _calls("disabled")
    anomaly_client.score(_payload(), None)
    assert _calls("disabled") == before + 1


def test_counts_ok(monkeypatch):
    monkeypatch.setattr(config, "ANOMALY_URL", "http://anomaly:8080")
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"anomaly_score": 0.1}
    before = _calls("ok")
    with patch.object(anomaly_client.requests, "post", return_value=resp):
        anomaly_client.score(_payload(), None)
    assert _calls("ok") == before + 1


def test_counts_timeout(monkeypatch):
    _failing_outcome(monkeypatch, "timeout", side_effect=anomaly_client.requests.exceptions.Timeout())


def test_counts_connection_error(monkeypatch):
    _failing_outcome(monkeypatch, "connection_error", side_effect=anomaly_client.requests.exceptions.ConnectionError())


def test_counts_http_error(monkeypatch):
    _failing_outcome(monkeypatch, "http_error", return_value=MagicMock(status_code=503))


def test_counts_invalid_response(monkeypatch):
    resp = MagicMock(status_code=200)
    resp.json.side_effect = ValueError("not json")
    _failing_outcome(monkeypatch, "invalid_response", return_value=resp)


def test_counts_unexpected_error(monkeypatch):
    _failing_outcome(monkeypatch, "error", side_effect=Exception("boom"))


def test_drift_flags_computed_from_last_seen(monkeypatch):
    monkeypatch.setattr(config, "ANOMALY_URL", "http://anomaly:8080")
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["body"] = json
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"anomaly_score": 0.0, "is_anomalous": False, "model_version": "v1", "confidence": 1.0}
        return resp

    last_seen = {"ip": "9.9.9.9", "geo": "GB-LDN", "ua": "ua-OLD"}
    with patch.object(anomaly_client.requests, "post", side_effect=fake_post):
        anomaly_client.score(_payload(), last_seen)

    body = captured["body"]
    assert body["ip_changed"] is True
    assert body["geo_changed"] is True
    assert body["ua_changed"] is True
    assert body["hour_of_day"] == 14
    assert body["endpoint_sensitivity"] == 3
