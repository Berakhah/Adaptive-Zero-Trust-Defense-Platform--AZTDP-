from fastapi.testclient import TestClient

from forensics import app as app_module

client = TestClient(app_module.app)


def test_events_requires_internal_token():
    assert client.get("/v1/forensics/events").status_code == 401


def test_replay_requires_internal_token():
    assert client.get("/v1/forensics/replay/s1").status_code == 401


def test_incident_requires_internal_token():
    assert client.get("/v1/forensics/incidents/r1").status_code == 401


def test_wrong_token_rejected():
    r = client.get("/v1/forensics/events", headers={"X-Internal-Token": "nope"})
    assert r.status_code == 401


def test_metrics_stays_open():
    assert client.get("/metrics").status_code == 200
