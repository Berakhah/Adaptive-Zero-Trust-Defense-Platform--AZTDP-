"""attack-sim API: internal token required on /v1/sim/*, no wildcard CORS."""
import os
import sys
from pathlib import Path

os.environ["AZTDP_INTERNAL_TOKEN"] = "sim-test-token"
os.environ["AZTDP_SIM_ORIGINS"] = "https://soc.example"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402

client = TestClient(api.app)


def test_health_is_open():
    assert client.get("/health").status_code == 200


def test_sim_requires_token():
    assert client.get("/v1/sim/status").status_code == 401
    assert client.post("/v1/sim/token_replay").status_code == 401
    assert client.post("/v1/sim/all/run").status_code == 401
    assert client.post("/v1/sim/token_replay", headers={"X-Internal-Token": "wrong"}).status_code == 401


def test_sim_accepts_token():
    r = client.get("/v1/sim/status", headers={"X-Internal-Token": "sim-test-token"})
    assert r.status_code == 200


def test_cors_not_wildcard():
    r = client.options(
        "/v1/sim/status",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert r.headers.get("access-control-allow-origin") != "*"
    assert "access-control-allow-origin" not in r.headers
    ok = client.options(
        "/v1/sim/status",
        headers={"Origin": "https://soc.example", "Access-Control-Request-Method": "GET"},
    )
    assert ok.headers.get("access-control-allow-origin") == "https://soc.example"
