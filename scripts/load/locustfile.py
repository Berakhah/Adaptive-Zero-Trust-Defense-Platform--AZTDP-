"""AZTDP load test.

Usage:
    locust -f scripts/load/locustfile.py --host http://localhost:8010 \
           --users 100 --spawn-rate 10 --run-time 5m \
           --headless --html report.html

SLOs validated post-run by `scripts/load/check_slos.py`:
    - p95 < 200ms
    - replay detection rate > 99%
    - throughput > 200 RPS @ 100 concurrent
    - false positive rate < 0.1%
"""
import os
import random
import time
import uuid

import requests
from locust import HttpUser, between, events, task


KEYCLOAK_URL = os.getenv(
    "AZTDP_KEYCLOAK_TOKEN_URL",
    "http://localhost:8080/realms/aztdp/protocol/openid-connect/token",
)
CLIENT_ID = os.getenv("AZTDP_CLIENT_ID", "aztdp-client")
CLIENT_SECRET = os.getenv("AZTDP_CLIENT_SECRET", "aztdp-secret")
USERNAME = os.getenv("AZTDP_USERNAME", "user1")
PASSWORD = os.getenv("AZTDP_PASSWORD", "password")


def _fetch_token() -> str:
    resp = requests.post(
        KEYCLOAK_URL,
        data={
            "grant_type": "password",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "username": USERNAME,
            "password": PASSWORD,
        },
        timeout=5,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


class NormalUser(HttpUser):
    """Simulates legitimate traffic with stable IP/UA/geo."""
    weight = 80
    wait_time = between(0.5, 2.0)

    def on_start(self):
        self.token = _fetch_token()
        self.client_ip = f"203.0.113.{random.randint(1, 254)}"
        self.user_agent = f"aztdp-loadtest-{random.randint(1, 1000)}"
        self.geo = "US-CA"

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "X-Request-Id": str(uuid.uuid4()),
            "X-Client-Ip": self.client_ip,
            "User-Agent": self.user_agent,
            "X-Geo": self.geo,
        }

    @task(8)
    def get_payment(self):
        pid = random.randint(1, 1000)
        self.client.get(f"/v1/payments/{pid}", headers=self._headers(), name="/v1/payments/[id]")

    @task(2)
    def health(self):
        self.client.get("/health", name="/health")


class AttackUser(HttpUser):
    """Simulates attack patterns expected to be denied/stepped-up."""
    weight = 20
    wait_time = between(0.1, 0.5)

    def on_start(self):
        self.token = _fetch_token()

    def _headers(self, ip, ua, geo):
        return {
            "Authorization": f"Bearer {self.token}",
            "X-Request-Id": str(uuid.uuid4()),
            "X-Client-Ip": ip,
            "User-Agent": ua,
            "X-Geo": geo,
        }

    @task(3)
    def replay_attempt(self):
        ip1 = f"203.0.113.{random.randint(1, 100)}"
        ip2 = f"198.51.100.{random.randint(100, 200)}"
        self.client.get(
            "/v1/payments/1",
            headers=self._headers(ip1, "attacker-a", "US-CA"),
            name="/replay-step1",
        )
        time.sleep(0.05)
        self.client.get(
            "/v1/payments/1",
            headers=self._headers(ip2, "attacker-b", "US-NY"),
            name="/replay-step2",
        )

    @task(2)
    def geo_drift(self):
        geos = [("US-CA", "203.0.113.10"), ("CN-SHA", "198.51.100.55"), ("RU-MOW", "192.0.2.99")]
        for geo, ip in geos:
            self.client.get(
                "/v1/payments/1",
                headers=self._headers(ip, "drift-ua", geo),
                name="/geo-drift",
            )
            time.sleep(0.1)

    @task(1)
    def admin_no_role(self):
        self.client.post(
            "/v1/admin/revoke",
            headers=self._headers("203.0.113.10", "attacker-priv", "US-CA"),
            name="/admin-priv-esc",
        )


@events.test_stop.add_listener
def _print_slo_report(environment, **kwargs):
    stats = environment.stats.total
    p95 = stats.get_response_time_percentile(0.95)
    rps = stats.total_rps
    print("\n=== AZTDP LOAD TEST SLO REPORT ===")
    print(f"  total_requests : {stats.num_requests}")
    print(f"  total_failures : {stats.num_failures}")
    print(f"  rps            : {rps:.1f}")
    print(f"  p50_ms         : {stats.get_response_time_percentile(0.50):.1f}")
    print(f"  p95_ms         : {p95:.1f}  (SLO < 200)")
    print(f"  p99_ms         : {stats.get_response_time_percentile(0.99):.1f}")
    print("===================================\n")
