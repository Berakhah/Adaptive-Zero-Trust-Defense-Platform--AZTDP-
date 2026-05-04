import time

from risk_engine.risk_model import score_risk


def _req(**overrides):
    base = {
        "request_id": "r1",
        "token_jti_hash": "hash",
        "ip": "1.1.1.1",
        "geo": "US-CA",
        "user_agent_hash": "ua-1",
        "endpoint": {"service": "django", "method": "GET", "path": "/v1/payments/1", "sensitivity": 2},
    }
    base.update(overrides)
    return base


def test_no_history_yields_base_only():
    risk, reasons, replay = score_risk(_req(), None)
    assert risk == 0.10
    assert reasons == []
    assert replay is False


def test_high_sensitivity_adds_weight():
    req = _req(endpoint={"service": "x", "method": "GET", "path": "/v1/admin", "sensitivity": 5})
    risk, reasons, _ = score_risk(req, None)
    assert risk == 0.10 + 0.15
    assert reasons[0]["code"] == "HIGH_SENSITIVITY"


def test_ip_drift_adds_weight():
    last = {"ip": "9.9.9.9", "geo": "US-CA", "ua": "ua-1", "ts": time.time() - 300}
    risk, reasons, replay = score_risk(_req(), last)
    assert risk == 0.10 + 0.35
    assert reasons[0]["code"] == "IP_GEO_DRIFT"
    assert replay is False


def test_ip_drift_within_replay_window_flags_replay():
    last = {"ip": "9.9.9.9", "geo": "US-CA", "ua": "ua-1", "ts": time.time() - 5}
    _, _, replay = score_risk(_req(), last)
    assert replay is True


def test_ua_drift_adds_weight():
    last = {"ip": "1.1.1.1", "geo": "US-CA", "ua": "ua-OLD", "ts": time.time() - 300}
    risk, reasons, _ = score_risk(_req(), last)
    assert risk == 0.10 + 0.20
    assert reasons[0]["code"] == "NEW_DEVICE"


def test_geo_drift_adds_weight():
    last = {"ip": "1.1.1.1", "geo": "US-NY", "ua": "ua-1", "ts": time.time() - 300}
    risk, reasons, _ = score_risk(_req(), last)
    assert risk == 0.10 + 0.20
    assert reasons[0]["code"] == "GEO_DRIFT"


def test_all_signals_capped_at_one():
    last = {"ip": "9.9.9.9", "geo": "CN-SHA", "ua": "ua-OLD", "ts": time.time() - 300}
    req = _req(endpoint={"service": "x", "method": "GET", "path": "/v1/admin", "sensitivity": 5})
    risk, _, _ = score_risk(req, last)
    assert risk == 1.0
