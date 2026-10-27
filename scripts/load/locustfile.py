"""AZTDP load test (current stack: Keycloak JWT -> Django middleware -> risk-engine + gateway/OPA).

Run inside the compose network (see scripts/load/README.md), e.g.:

    locust -f /mnt/locustfile.py --headless -u 200 -r 20 -t 5m --host https://nginx

Configuration (environment):
    AZTDP_KEYCLOAK_TOKEN_URL  default http://keycloak:8080/realms/aztdp/protocol/openid-connect/token
    AZTDP_CLIENT_ID           default aztdp-client
    AZTDP_CLIENT_SECRET       REQUIRED (no default: fail closed). Dev: KEYCLOAK_CLIENT_SECRET from .env.dev
    AZTDP_USERNAME/PASSWORD   default risk_user / password (dev realm seed user)
    AZTDP_ATTACK_USERNAME/PASSWORD  default user1 / password
    AZTDP_HOST_HEADER         Host header to send (must be in Django ALLOWED_HOSTS), default localhost
    AZTDP_INSECURE_TLS        "1" (default) skips verification of the self-signed ingress cert
    AZTDP_TOKENS_PER_USER     size of the token pool per account, default 40
    AZTDP_LOGIN_SPACING       seconds between logins of one account, default 1.1
    AZTDP_ENFORCE_SLO         "1": exit non-zero when the PROVISIONAL SLOs are missed

Notes on what is and is not exercised:
    * nginx overwrites X-Client-Ip / X-Geo / X-Forwarded-For with the socket peer, and
      Django honours those headers only from the pinned proxy address, so IP/geo-drift
      attacks cannot be generated from a load client and are not simulated here.
      The attack mix therefore covers user-agent drift on one token (risk increase, any
      non-5xx verdict is fine) and privilege escalation (non-admin on a sensitivity-5
      route, must be denied). The risk engine's replay rule needs a changing client IP, so
      replay detection cannot be exercised from here (it is covered by unit tests).
    * Keycloak's brute-force protection (kept ON, as in production) locks an account that
      logs in twice within 1 s, so tokens are pre-fetched into a pool per account with
      >= AZTDP_LOGIN_SPACING between logins (accounts run in parallel) and handed out
      round-robin. A pool entry is one "device": it carries its own stable user agent.
    * Access tokens live 5 minutes, so the pre-fetch time plus the run must stay under
      that: with the defaults (40 tokens, ~45 s) use `-t 3m` or shorter. A 401 from an
      expired token is counted as a failure.
"""
import os
import random
import time
import uuid

import gevent
import requests
import urllib3
from locust import HttpUser, between, events, task

KEYCLOAK_URL = os.getenv(
    "AZTDP_KEYCLOAK_TOKEN_URL",
    "http://keycloak:8080/realms/aztdp/protocol/openid-connect/token",
)
CLIENT_ID = os.getenv("AZTDP_CLIENT_ID", "aztdp-client")
CLIENT_SECRET = os.getenv("AZTDP_CLIENT_SECRET", "")
USERNAME = os.getenv("AZTDP_USERNAME", "risk_user")
PASSWORD = os.getenv("AZTDP_PASSWORD", "password")
ATTACK_USERNAME = os.getenv("AZTDP_ATTACK_USERNAME", "user1")
ATTACK_PASSWORD = os.getenv("AZTDP_ATTACK_PASSWORD", "password")
HOST_HEADER = os.getenv("AZTDP_HOST_HEADER", "localhost")
INSECURE_TLS = os.getenv("AZTDP_INSECURE_TLS", "1") == "1"
TOKENS_PER_USER = int(os.getenv("AZTDP_TOKENS_PER_USER", "40"))
LOGIN_SPACING = float(os.getenv("AZTDP_LOGIN_SPACING", "1.1"))

# PROVISIONAL (owner has not confirmed): docs/PERFORMANCE_BASELINE.md
SLO_P99_MS = 250.0
SLO_ERROR_RATE = 0.001

if INSECURE_TLS:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _fetch_token(username: str, password: str) -> str:
    if not CLIENT_SECRET:
        raise RuntimeError("AZTDP_CLIENT_SECRET is required (dev: KEYCLOAK_CLIENT_SECRET from .env.dev)")
    resp = requests.post(
        KEYCLOAK_URL,
        data={
            "grant_type": "password",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "username": username,
            "password": password,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


_POOLS = {}  # username -> list of (token, user_agent)
_NEXT = {}


def _fill_pool(username, password):
    pool = []
    for i in range(TOKENS_PER_USER):
        started = time.monotonic()
        pool.append((_fetch_token(username, password), f"aztdp-loadtest-{username}-{i}"))
        wait = LOGIN_SPACING - (time.monotonic() - started)
        if wait > 0:
            gevent.sleep(wait)
    _POOLS[username] = pool


@events.init.add_listener
def _prefetch_tokens(environment, **kwargs):
    accounts = {(USERNAME, PASSWORD), (ATTACK_USERNAME, ATTACK_PASSWORD)}
    started = time.monotonic()
    gevent.joinall([gevent.spawn(_fill_pool, u, p) for u, p in accounts], raise_error=True)
    print(f"pre-fetched {TOKENS_PER_USER} tokens for {len(accounts)} accounts in {time.monotonic() - started:.0f}s")


def _next_token(username):
    pool = _POOLS[username]
    i = _NEXT.get(username, 0)
    _NEXT[username] = i + 1
    return pool[i % len(pool)]


class _AztdpUser(HttpUser):
    abstract = True

    def on_start(self):
        self.client.verify = not INSECURE_TLS
        self.token, self.device_ua = _next_token(self._credentials()[0])

    def _credentials(self):
        return USERNAME, PASSWORD

    def _headers(self, user_agent=None):
        return {
            "Authorization": f"Bearer {self.token}",
            "X-Request-Id": str(uuid.uuid4()),
            "User-Agent": user_agent or self.device_ua,
            "Host": HOST_HEADER,
        }


class NormalUser(_AztdpUser):
    """Legitimate traffic: stable user agent, authenticated reads."""

    weight = 90
    wait_time = between(0.5, 2.0)

    @task(9)
    def get_payment(self):
        pid = random.randint(1, 1000)
        # Expected: allowed (200). Anything else (deny, 5xx, timeout) is a failure.
        self.client.get(
            f"/v1/payments/{pid}",
            headers=self._headers(),
            name="/v1/payments/[id]",
        )

    @task(1)
    def health(self):
        self.client.get("/health", headers={"Host": HOST_HEADER}, name="/health")


class AttackUser(_AztdpUser):
    """Abuse patterns. A denial (401/403) is the *expected* outcome; success means a gap."""

    weight = 10
    wait_time = between(0.1, 0.5)

    def _credentials(self):
        return ATTACK_USERNAME, ATTACK_PASSWORD

    def _expect_denied(self, method, path, name, user_agent):
        with self.client.request(
            method, path, headers=self._headers(user_agent), name=name, catch_response=True
        ) as resp:
            if resp.status_code in (401, 403):
                resp.success()
            elif resp.status_code >= 500 or resp.status_code == 0:
                resp.failure(f"server error {resp.status_code}")
            else:
                resp.failure(f"abuse request was allowed ({resp.status_code})")

    @task(3)
    def user_agent_drift(self):
        # Same token, changing user agent: raises the risk score (allow, step-up or deny
        # are all valid verdicts); only server errors / timeouts count as failures.
        with self.client.get(
            "/v1/payments/1",
            headers=self._headers(f"drift-{random.randint(1, 100)}"),
            name="/ua-drift",
            catch_response=True,
        ) as resp:
            if resp.status_code >= 500 or resp.status_code == 0:
                resp.failure(f"server error {resp.status_code}")
            else:
                resp.success()

    @task(1)
    def admin_no_role(self):
        self._expect_denied("POST", "/v1/admin/flags", "/admin-priv-esc", "attacker-priv")


@events.test_stop.add_listener
def _print_slo_report(environment, **kwargs):
    stats = environment.stats.total
    n = max(stats.num_requests, 1)
    err = stats.num_failures / n
    p99 = stats.get_response_time_percentile(0.99)
    print("\n=== AZTDP LOAD TEST REPORT (SLOs are PROVISIONAL) ===")
    print(f"  total_requests : {stats.num_requests}")
    print(f"  total_failures : {stats.num_failures}  (error rate {err * 100:.3f}%, SLO < {SLO_ERROR_RATE * 100:.1f}%)")
    print(f"  rps            : {stats.total_rps:.1f}")
    print(f"  p50_ms         : {stats.get_response_time_percentile(0.50):.1f}")
    print(f"  p95_ms         : {stats.get_response_time_percentile(0.95):.1f}")
    print(f"  p99_ms         : {p99:.1f}  (SLO < {SLO_P99_MS:.0f})")
    print("=====================================================\n")
    if os.getenv("AZTDP_ENFORCE_SLO") == "1" and (p99 >= SLO_P99_MS or err >= SLO_ERROR_RATE):
        environment.process_exit_code = 1
