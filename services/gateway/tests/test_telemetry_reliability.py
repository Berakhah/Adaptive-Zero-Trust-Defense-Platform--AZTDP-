import requests

from gateway import metrics, telemetry


class _Resp:  # minimal stand-in; telemetry only needs the call to not raise
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
    telemetry._post("policy_decision", {"request_id": "r"})
    assert calls["n"] == 3


def test_drop_is_counted_and_logged(monkeypatch, caplog):
    monkeypatch.setattr(telemetry.requests, "post", _down)
    monkeypatch.setattr(telemetry.time, "sleep", lambda s: None)
    monkeypatch.setattr(telemetry.config, "TELEMETRY_URL", "http://t")
    before = metrics.TELEMETRY_DROPPED.labels(service="gateway", reason="exhausted")._value.get()
    telemetry._post("policy_decision", {"request_id": "r"})
    after = metrics.TELEMETRY_DROPPED.labels(service="gateway", reason="exhausted")._value.get()
    assert after == before + 1
    assert any(r.levelname == "WARNING" for r in caplog.records)


def test_backoff_schedule_and_retry_counter(monkeypatch):
    sleeps = []
    monkeypatch.setattr(telemetry.requests, "post", _down)
    monkeypatch.setattr(telemetry.time, "sleep", sleeps.append)
    monkeypatch.setattr(telemetry.config, "TELEMETRY_URL", "http://t")
    before = metrics.TELEMETRY_RETRIES.labels(service="gateway")._value.get()
    telemetry._post("policy_decision", {"request_id": "r"})
    assert sleeps == [0.05, 0.15, 0.45]
    assert metrics.TELEMETRY_RETRIES.labels(service="gateway")._value.get() == before + 3


def test_http_error_status_is_retried(monkeypatch):
    class _Bad:
        status_code = 500

    calls = {"n": 0}

    def post(*a, **k):
        calls["n"] += 1
        return _Bad()

    monkeypatch.setattr(telemetry.requests, "post", post)
    monkeypatch.setattr(telemetry.time, "sleep", lambda s: None)
    monkeypatch.setattr(telemetry.config, "TELEMETRY_URL", "http://t")
    telemetry._post("policy_decision", {"request_id": "r"})
    assert calls["n"] == 4
