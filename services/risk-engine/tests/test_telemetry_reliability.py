import requests

from risk_engine import metrics, telemetry


class _Resp:
    status_code = 200


def _down(*a, **k):
    raise requests.ConnectionError("down")


def test_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.ConnectionError("down")
        return _Resp()

    monkeypatch.setattr(telemetry.requests, "post", flaky)
    monkeypatch.setattr(telemetry.time, "sleep", lambda s: None)
    monkeypatch.setattr(telemetry.config, "TELEMETRY_URL", "http://t")
    telemetry._post({"request_id": "r"})
    assert calls["n"] == 3


def test_drop_is_counted_and_logged(monkeypatch, caplog):
    monkeypatch.setattr(telemetry.requests, "post", _down)
    monkeypatch.setattr(telemetry.time, "sleep", lambda s: None)
    monkeypatch.setattr(telemetry.config, "TELEMETRY_URL", "http://t")
    before = metrics.TELEMETRY_DROPPED.labels(service="risk-engine", reason="exhausted")._value.get()
    telemetry._post({"request_id": "r"})
    after = metrics.TELEMETRY_DROPPED.labels(service="risk-engine", reason="exhausted")._value.get()
    assert after == before + 1
    assert any(r.levelname == "WARNING" for r in caplog.records)
