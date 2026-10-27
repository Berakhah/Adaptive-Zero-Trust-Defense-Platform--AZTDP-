# AZTDP Production-Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take AZTDP from "feature-complete demo that claims production readiness" to a deployable, verifiably-green, SOC 2-defensible Docker Compose platform.

**Architecture:** No new subsystems. The plan (a) makes the existing test/CI signal truthful, (b) closes the security gaps that remain in the "done" P0–P5 work, (c) makes the audit/revocation data path durable, (d) hardens containers, network exposure and secrets, and (e) adds the operational pieces (alerting, backups, release pipeline) that a real deployment needs.

**Tech Stack:** Python 3.12 (FastAPI, Django 5), Java 25 / Spring Boot 4, OPA/Rego, Redis 7, PostgreSQL 16, Keycloak 25, Prometheus/Grafana, nginx, GitHub Actions, Vite/React (two UIs).

**Spec:** `docs/PRODUCTION_READINESS.md` (existing tracker; this plan supersedes its "all done" status) + the Findings Register below (analysis of commit `7f50424`, 2026-10-19).

## Global Constraints

- Deployment target is **Docker Compose only** (owner decision 2026-05-03). K8s/Helm are out of scope and are quarantined, not maintained (Task 17).
- Compliance scope is **SOC 2 Type II**; no PCI/GDPR (owner decision 2026-05-03).
- Python `>=3.11` (CI uses 3.12); Java 25 / Spring Boot 4.0.6 (verified 2026-05-03).
- All internal endpoints authenticate with the `X-Internal-Token` header (constant-time compare, startup failure if unset). **Never** `Authorization: Bearer` for internal calls.
- Fail-closed by default: `AZTDP_FAIL_OPEN=false` everywhere; any new code path must deny on dependency failure.
- No secret may have a usable default value in code, compose or the Keycloak realm in the production profile.
- Every behavior change is test-first (red → green) and committed separately with a conventional-commit message.
- Python tests are run **per service directory** (the `tests` package name collides across services — see Finding F-01).

---

## Findings Register (what the analysis found)

Severity: **B** = blocks production, **H** = high, **M** = medium, **L** = low. "Task" = where it is fixed.

### Verified by running code
| ID | Sev | Finding | Evidence | Task |
|---|---|---|---|---|
| F-01 | B | Test suite is **red**: gateway 4 failures, risk-engine 3 failures (401 — tests never send `X-Internal-Token` after P1.3). Root `pytest` aborts at collection (`No module named 'tests.test_anomaly_client'`, duplicate `tests` packages). `docs/PRODUCTION_READINESS.md` nonetheless marks P1.3/P5 done. | `pytest` run 2026-10-19 | 1 |
| F-02 | B | `.env.example` was **deleted** in the latest commit (`7f50424`) but README/docs/CI depend on it; CI `integration-test` runs `docker compose up` with no `.env` → every `${VAR}` empty → stack cannot start. | `git show --stat 7f50424` | 2, 16 |
| F-03 | H | Repo hygiene: `services/spring-app/target/*` committed; `.claude/worktrees/nostalgic-sinoussi-4a2dcd` committed as a broken gitlink (`git status` fatal); empty `libs/*` dirs; 5 overlapping root guides; two competing dashboards (`services/dashboard`, `sentinel-command-main`). | `git ls-files` | 2, 15, 18 |

### Verified by code reading
| ID | Sev | Finding | Evidence | Task |
|---|---|---|---|---|
| F-04 | B | **Dashboard nginx sends `Authorization: Bearer $TOKEN`**, but services read `X-Internal-Token` → every proxied gateway/risk/anomaly/telemetry call from the SOC UI returns 401. Separately, the dashboard (port 8099, no auth) is a public relay to internal endpoints; if the header were fixed it would hand any visitor the internal token's power (revoke tokens, retrain model). | `services/dashboard/nginx.conf.template:72-102` vs `internal_auth.py` | 3 |
| F-05 | B | **Forensics service has no authentication** and returns audit data (user ids, IPs, geo, payloads); published on host port 8004 and proxied "(no auth required)". | `services/forensics/app.py`, `nginx.conf.template:37` | 3 |
| F-06 | B | **Step-up is broken and brute-forceable**: challenges live in a per-process dict while gunicorn runs 4 workers (verify lands on a different worker 75% of the time → "invalid challenge"); `/v1/auth/step-up/verify` is allow-listed (no bearer), takes `user_id` from the caller, has no attempt limit (6-digit TOTP, ±1 window) and one **shared** TOTP secret with a hard-coded default (`AZTDP_DEV_TOTP_SECRET_BASE32`) and signing key default (`aztdp-stepup-signing-key-change-me`). Step-up token is not bound to the access token and is replayable for 10 min on any path. | `core/stepup.py`, `core/views.py:52-86`, `settings.py:80`, compose `--workers 4` | 5 |
| F-07 | B | **Revocations are not durable**: Redis runs `save ""`, `appendonly no`, `maxmemory-policy allkeys-lru` (revocation keys can be *evicted* under memory pressure); DB persistence of revocations happens only via fire-and-forget telemetry that logs failures at `debug` and drops them. Revocation TTL is a fixed setting, not the token's `exp`. After a Redis restart or telemetry blip, a revoked token becomes valid again. | `infra/redis/redis.conf`, `gateway/telemetry.py:_post`, `gateway/revocation_store.py` | 9 |
| F-08 | H | **Audit completeness is not guaranteed** (SOC 2 control claim): telemetry emit is lossy (0.2 s connect / 0.5 s read, no retry, no dead-letter, no metric). `audit_events` is granted `UPDATE` to the service role, so the audit table is mutable. | `gateway/telemetry.py`, `infra/postgres/03_grants.sql` | 8, 10 |
| F-09 | B | **Network exposure**: compose publishes Postgres 5432, Redis 6379 (no password), OPA 8181 (policy-write API unauthenticated), Keycloak 8080/9000, every internal service, Prometheus. Anyone on the host network can rewrite policy (`PUT /v1/policies`) or flush revocations. | `docker-compose.yml` `ports:` | 4 |
| F-10 | B | **Dev settings in the only compose file**: `AZTDP_DEBUG="true"` (disables SSL redirect/HSTS/secure cookies), Keycloak `start-dev`, realm `sslRequired: none`, client secret `aztdp-secret`, `directAccessGrants` on, `webOrigins: ["*"]`, seeded users with static passwords, attack-sim credentials hard-coded in compose, Django `SECRET_KEY` falls back to `"change-me"`. | `docker-compose.yml`, `infra/keycloak/aztdp-realm.json`, `settings.py:6` | 6 |
| F-11 | H | **Attack-sim is deployed with the platform**, exposes `POST /v1/sim/*` with `CORS *` and no auth, spawns subprocesses. Must not exist in a production profile. | `services/attack-sim/api.py`, compose | 6 |
| F-12 | H | Containers run as **root**, no `HEALTHCHECK` in images, no `.dockerignore`, Django image `EXPOSE`s/`CMD`s 8080 while compose overrides to 8000 → **Prometheus scrapes `django-app:8080` and gets nothing**; Spring image builds with `-Dmaven.test.skip`; unpinned base-image digests. | Dockerfiles, `prometheus.yml:36` | 7, 14 |
| F-13 | H | **Anomaly model is loaded with `joblib.load` (pickle) from a shared writable volume** — anyone able to write that volume gets code execution in the scoring service. Hot-reload loads whatever version string Redis holds (Redis is unauthenticated, F-09). | `anomaly-service/model.py:60-70,90-106` | 11 |
| F-14 | H | DB layout drift: compose mounts only `scripts/db/schema.sql` (non-partitioned `audit_events`); `V2__audit_partitioning.sql` (needs a *partitioned* `audit_events`) is never applied by anything. Retention runbook describes a table that doesn't exist in a fresh deployment. All services share one DB role. | `docker-compose.yml:25-27`, `scripts/db/` | 8 |
| F-15 | M | No alerting path: Prometheus rules exist but there is no Alertmanager; no `up == 0` rules; no backup/restore procedure or test; Redis persistence off. | `infra/prometheus`, compose | 12, 13 |
| F-16 | M | CI gaps: OPA tests (`authz_test.rego`) never run; no frontend CI (either UI); no SAST/dependency/secret/image scanning; no coverage gate (pyproject `fail_under=40` never executed); lint selects only `E,F,W,I`; images are never pushed/signed; integration job depends on `.env`. | `.github/workflows/ci.yml` | 16 |
| F-17 | M | **sentinel-command UI silently falls back to mock data on any API error** (`api.ts wrap()`), and `health/sessions/heatmap/series/topRules` are always mocks; response shapes (`{events:[…]}`) don't match what the code expects (arrays). A production SOC screen that fabricates data is a safety problem. Default `VITE_USE_MOCK` is `true`. | `sentinel-command-main/src/lib/api.ts` | 18 |
| F-18 | M | `pyproject.toml` is invalid/ignored in places: `build-backend = "setuptools.backends.legacy:build"` doesn't exist; `[tool.pytest.env]` needs `pytest-env`; `pytest.ini` shadows `[tool.pytest.ini_options]`; `testpaths` lists `telemetry-ingest/tests` and `forensics/tests`, which don't exist (those two services have **zero tests**). | repo root | 1, 10 |
| F-19 | M | Dependency hygiene: duplicate `python-json-logger` line in django requirements; `psycopg` 3.1.19 vs 3.2.1 across services; no hashes/lock; Keycloak `25.0`, Grafana, etc. pinned by tag not digest. | `services/*/requirements.txt` | 7, 16 |
| F-20 | L | Documentation drift: `docs/PRODUCTION_READINESS.md` "Open Questions: none"; `.github/copilot-instructions.md` is boilerplate; `memories/repo/upgrade-java-*.md` stray; K8s/Helm manifests use `:latest` and contradict the Compose-only decision. | docs | 15, 17 |

### Known limitations accepted (documented, not fixed here)
- Risk-engine `get_last_seen`/`set_last_seen` is not atomic (two concurrent requests on one token can both pass replay checks). Documented in Task 15; revisit if load testing shows it matters.
- IP change within `REPLAY_WINDOW_SECONDS` is treated as replay (409). A legitimate mobile client switching networks is denied; this is a product decision and is documented.
- Per-user TOTP enrollment / WebAuthn is **not** built here. Task 5 makes the existing TOTP safe to run; Open Question Q1 asks whether to delegate step-up to Keycloak instead.

### Open questions for the owner (do not block Tasks 1–4)
- **Q1:** Step-up long-term: keep self-hosted TOTP (needs enrollment UI + per-user secrets) or delegate to Keycloak step-up (`acr_values`)? Task 5 assumes "harden what exists".
- **Q2:** Which dashboard is the product — `services/dashboard` (vanilla React, wired to real APIs but 401s) or `sentinel-command-main` (new design, mostly mocked)? Task 18 assumes sentinel becomes primary and `services/dashboard` is removed once parity is verified.
- **Q3:** Is there a target host/registry for releases (GHCR assumed in Task 16)?

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `scripts/run_tests.sh` | create | Runs pytest once per service dir with the right env; used by CI and humans |
| `services/*/tests/conftest.py` | create/modify | Sets `AZTDP_INTERNAL_TOKEN`, provides `auth_headers` |
| `.env.example` | restore + extend | Documented template for every `${VAR}` |
| `docker-compose.yml` | modify | Production-safe base: no published ports except ingress, no dev secrets |
| `docker-compose.dev.yml` | create | Dev overrides: localhost-bound ports, DEBUG, attack-sim profile |
| `infra/redis/redis.conf` | modify | `requirepass`, AOF, `noeviction` |
| `infra/keycloak/aztdp-realm.dev.json` / `aztdp-realm.json` | split | Dev realm (seeded users) vs prod realm (no users, no secrets) |
| `services/django-app/core/stepup.py` | rewrite | Redis-backed challenges, attempt limiter, bound tokens |
| `services/forensics/internal_auth.py` | create | Same dependency as other services |
| `libs/` | delete | Empty placeholder dirs |
| `infra/postgres/04_roles.sql`, `scripts/db/migrate.sh` | create | Per-service roles, append-only audit, single migration path |
| `services/gateway/telemetry.py`, `revocation_store.py` | modify | Durable revocation, telemetry retry + drop metric |
| `services/anomaly-service/model.py` | modify | Signed model artifacts |
| `infra/alertmanager/alertmanager.yml` | create | Alert routing |
| `.github/workflows/ci.yml`, `release.yml`, `dependabot.yml` | rewrite/create | Full pipeline |
| `docs/runbooks/BACKUP_RESTORE.md`, `docs/GO_LIVE_CHECKLIST.md` | create | Operations |

---

## Phase A — Make the signal truthful

### Task 1: Green, isolated, per-service test runs

**Files:**
- Create: `services/gateway/tests/conftest.py`, `services/risk-engine/tests/conftest.py`, `scripts/run_tests.sh`
- Modify: `services/gateway/tests/test_policy_endpoint.py`, `services/risk-engine/tests/test_endpoint.py`, `services/risk-engine/tests/test_anomaly_client.py`, `services/gateway/tests/test_telemetry_drain.py`, `pyproject.toml`, `pytest.ini`

**Interfaces:**
- Produces: fixture `auth_headers: dict[str,str]` (contains `X-Internal-Token`) in gateway and risk-engine test packages; `scripts/run_tests.sh [service...]` exit code non-zero if any service fails.

- [ ] **Step 1: Reproduce the failures**

Run: `cd services/gateway && AZTDP_INTERNAL_TOKEN=t python -m pytest -q --rootdir=. 2>&1 | tail -8`
Expected: 4 FAILED (`test_revoked_token_short_circuits_to_revoke`, `test_decision_passes_through_opa_allow`, `test_revoke_endpoint` → 401; `test_emit_async_no_op_without_telemetry_url`).
Run the same in `services/risk-engine`. Expected: 3 FAILED (two 401s, `test_drift_flags_computed_from_last_seen`).

- [ ] **Step 2: Add the shared conftest (gateway)**

```python
# services/gateway/tests/conftest.py
import pytest

TEST_TOKEN = "test-internal-token"


@pytest.fixture(autouse=True)
def _internal_token(monkeypatch):
    monkeypatch.setenv("AZTDP_INTERNAL_TOKEN", TEST_TOKEN)


@pytest.fixture
def auth_headers():
    return {"X-Internal-Token": TEST_TOKEN}
```

Create the identical file at `services/risk-engine/tests/conftest.py`.

- [ ] **Step 3: Make the endpoint tests send the header**

In `services/gateway/tests/test_policy_endpoint.py` change each protected call, e.g.:

```python
def test_revoked_token_short_circuits_to_revoke(auth_headers):
    app_module.revocations.revoke("abc")
    body = {"input": {"request_id": "r1", "context": {"token_jti_hash": "abc"}}}
    r = client.post("/v1/policy/decision", json=body, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["decision"]["decision"] == "revoke"
```

Apply `headers=auth_headers` to every `client.post/get` on a protected route in `test_policy_endpoint.py` and `risk-engine/tests/test_endpoint.py`. Add a negative test to each file:

```python
def test_protected_route_rejects_missing_token():
    r = client.post("/v1/policy/decision", json={"input": {}})
    assert r.status_code == 401
```
(risk-engine: `/v1/risk/evaluate` with a minimal valid body.)

- [ ] **Step 4: Diagnose the two non-401 failures**

Run: `python -m pytest -q --rootdir=. services/risk-engine/tests/test_anomaly_client.py::test_drift_flags_computed_from_last_seen -x` (and the gateway telemetry test) and read the assertion. These were *not* root-caused during analysis; fix the test or the code depending on which is wrong (`docs/architecture/ARCHITECTURE.md` is the tie-breaker). Record the root cause in the commit message.

- [ ] **Step 5: Add the per-service runner**

```bash
#!/usr/bin/env bash
# scripts/run_tests.sh — run pytest once per service (the `tests` package name
# collides across services, so a single root invocation cannot collect them).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICES=("$@")
[ ${#SERVICES[@]} -eq 0 ] && SERVICES=(gateway risk-engine anomaly-service telemetry-ingest forensics django-app)
rc=0
for s in "${SERVICES[@]}"; do
  dir="$ROOT/services/$s"
  [ -d "$dir/tests" ] || { echo "!! $s has no tests/"; rc=1; continue; }
  echo "=== $s"
  (cd "$dir" && AZTDP_INTERNAL_TOKEN=test AZTDP_SECRET_KEY=test \
     python -m pytest -q --rootdir=. -p no:cacheprovider) || rc=1
done
exit $rc
```

- [ ] **Step 6: Fix `pyproject.toml` / `pytest.ini`**

Set `build-backend = "setuptools.build_meta"`, delete the `[tool.pytest.ini_options]` and `[tool.pytest.env]` blocks (keep `pytest.ini` as the single source; add `pytest-env` only if a service needs it), and remove `testpaths` entries for dirs that don't exist yet (they return in Task 10). Keep `[tool.coverage.*]`.

- [ ] **Step 7: Verify**

Run: `bash scripts/run_tests.sh gateway risk-engine anomaly-service django-app`
Expected: all four services PASS; exit code 0. (telemetry-ingest/forensics report `!! has no tests/` until Task 10 — that is intended and non-zero.)

- [ ] **Step 8: Commit**

```bash
git add services/*/tests scripts/run_tests.sh pyproject.toml pytest.ini
git commit -m "test: restore green suite, send internal token, run pytest per service"
```

### Task 2: Repository hygiene and restored `.env.example`

**Files:**
- Create: `.env.example`
- Modify: `.gitignore`
- Delete (from index): `services/spring-app/target/**`, `.claude/worktrees/nostalgic-sinoussi-4a2dcd`, `memories/`, `libs/`

- [ ] **Step 1: Restore the template from history**

Run: `git show 7f50424^:.env.example > .env.example`
Then add every variable used by the stack and introduced by later tasks (blank values, with a generation hint per line):

```dotenv
POSTGRES_PASSWORD=
POSTGRES_PASSWORD_URLENCODED=
KEYCLOAK_ADMIN=admin
KEYCLOAK_ADMIN_PASSWORD=
AZTDP_SECRET_KEY=            # python -c "import secrets; print(secrets.token_urlsafe(50))"
AZTDP_ALLOWED_HOSTS=
AZTDP_INTERNAL_TOKEN=        # python -c "import secrets; print(secrets.token_hex(32))"
GRAFANA_ADMIN_PASSWORD=
REDIS_PASSWORD=              # Task 4
REDIS_PASSWORD_URLENCODED=   # Task 4
AZTDP_STEPUP_SIGNING_KEY=    # Task 5
AZTDP_TOTP_MASTER_SECRET=    # Task 5
AZTDP_MODEL_HMAC_KEY=        # Task 11
KEYCLOAK_CLIENT_SECRET=      # Task 6
DASHBOARD_HTPASSWD=          # Task 3
ALERT_WEBHOOK_URL=           # Task 12
```

- [ ] **Step 2: Stop tracking generated/stray files**

```bash
git rm -r --cached services/spring-app/target
git rm --cached .claude/worktrees/nostalgic-sinoussi-4a2dcd
git rm -r --cached memories
git rm -r libs
```
Append to `.gitignore`: `target/`, `*.jar.original`, `.pytest_cache/`, `.claude/worktrees/`, `dist/`, `*.pkl`, `.env.*` with exception `!.env.example`.

- [ ] **Step 3: Verify**

Run: `git status --short | head` (no fatal error) and `git ls-files | grep -E "target/|worktrees|^libs/"` (no output).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: restore .env.example, untrack build output and stray worktree link"
```

---

## Phase B — Close the security blockers

### Task 3: Authenticate forensics; lock down and fix the dashboard proxy

**Files:**
- Create: `services/forensics/internal_auth.py` (copy of `services/gateway/internal_auth.py`), `services/forensics/tests/__init__.py`, `services/forensics/tests/conftest.py`, `services/forensics/tests/test_auth.py`
- Modify: `services/forensics/app.py`, `docker-compose.yml` (forensics env), `services/dashboard/nginx.conf.template`

**Interfaces:**
- Consumes: `require_internal_token` dependency pattern from `services/gateway/internal_auth.py`.
- Produces: forensics `/v1/forensics/*` routes require `X-Internal-Token`; dashboard nginx adds that header (never `Authorization`) and exposes only an allow-list.

- [ ] **Step 1: Write the failing test**

```python
# services/forensics/tests/test_auth.py
from fastapi.testclient import TestClient
from forensics import app as app_module

client = TestClient(app_module.app)


def test_events_requires_internal_token():
    assert client.get("/v1/forensics/events").status_code == 401


def test_replay_requires_internal_token():
    assert client.get("/v1/forensics/replay/s1").status_code == 401


def test_incident_requires_internal_token():
    assert client.get("/v1/forensics/incidents/r1").status_code == 401


def test_metrics_stays_open():
    assert client.get("/metrics").status_code == 200
```
`conftest.py`: same autouse `AZTDP_INTERNAL_TOKEN` fixture as Task 1.

- [ ] **Step 2: Run to confirm failure**

Run: `bash scripts/run_tests.sh forensics` → Expected: 3 FAILED (200/500 instead of 401).

- [ ] **Step 3: Implement**

Copy `internal_auth.py`, then in `app.py`:

```python
from fastapi import Depends
from .internal_auth import require_internal_token

_auth = [Depends(require_internal_token)]

@app.get("/v1/forensics/events", dependencies=_auth)
...
@app.get("/v1/forensics/replay/{session_id}", dependencies=_auth)
...
@app.get("/v1/forensics/incidents/{request_id}", dependencies=_auth)
```
Add `AZTDP_INTERNAL_TOKEN: ${AZTDP_INTERNAL_TOKEN}` to the forensics service in `docker-compose.yml`.

- [ ] **Step 4: Run to confirm pass**

Run: `bash scripts/run_tests.sh forensics` → Expected: PASS.

- [ ] **Step 5: Fix and shrink the dashboard proxy**

Rewrite `services/dashboard/nginx.conf.template` so that:
- Every internal upstream uses `proxy_set_header X-Internal-Token "${AZTDP_INTERNAL_TOKEN}";` (no `Authorization`).
- Only **read** routes remain: `GET` on `/api/forensics/`, `/api/prometheus/api/v1/query*`, `/api/*/health`. Enforce with `limit_except GET { deny all; }` on each location.
- **Remove** `/api/gateway/`, `/api/anomaly/`, `/api/telemetry/`, `/api/opa/`, `/api/grafana/`, `/api/keycloak/`, `/api/django/`, `/api/spring/` (write paths such as token revoke, `/v1/anomaly/retrain` and OPA policy PUT must not be reachable from a browser).
- Add `auth_basic "AZTDP SOC"; auth_basic_user_file /etc/nginx/htpasswd;` at `server` level as an interim gate; the htpasswd file is mounted from a secret (`DASHBOARD_HTPASSWD` in `.env.example`). Real SSO (oauth2-proxy → Keycloak) is the follow-up listed in Task 18.
- Bind the dashboard behind the TLS ingress (Task 4) — it must not serve plain HTTP on a public port.

- [ ] **Step 6: Verify the proxy**

Run: `docker compose up -d --build dashboard forensics && curl -s -o /dev/null -w "%{http_code}\n" localhost:8099/api/forensics/v1/forensics/events`
Expected: `401` (basic-auth). With `-u soc:<pw>` → `200`. `curl -X POST -u … localhost:8099/api/gateway/v1/tokens/revoke` → `404`.

- [ ] **Step 7: Commit**

```bash
git add services/forensics services/dashboard docker-compose.yml
git commit -m "fix(security): require internal token on forensics, fix and shrink dashboard proxy"
```

### Task 4: Network exposure, Redis auth, OPA isolation

**Files:**
- Modify: `docker-compose.yml`, `infra/redis/redis.conf`, `infra/nginx/nginx.conf`
- Create: `docker-compose.dev.yml`, `scripts/check_exposure.sh`

**Interfaces:**
- Produces: base `docker-compose.yml` publishes **only** nginx (80/443/8443/3443) and, optionally, the dashboard behind nginx. `docker-compose.dev.yml` re-publishes service ports bound to `127.0.0.1`.

- [ ] **Step 1: Write the exposure check (failing first)**

```bash
#!/usr/bin/env bash
# scripts/check_exposure.sh — fail if the base compose file publishes anything except ingress.
set -euo pipefail
bad=$(docker compose -f docker-compose.yml config --format json | python -c "
import json,sys,re
cfg=json.load(sys.stdin); bad=[]
for name,svc in cfg['services'].items():
    for p in svc.get('ports',[]) or []:
        pub=str(p.get('published',''))
        if not re.match(r'^(80|443|8443|3443)$',pub): bad.append(f'{name}:{pub}')
print('\n'.join(bad))")
[ -z "$bad" ] || { echo "Unexpected published ports:"; echo "$bad"; exit 1; }
echo "exposure OK"
```
Run: `bash scripts/check_exposure.sh` → Expected: FAIL listing postgres:5432, redis:6379, opa:8181, keycloak, gateway:8000, …

- [ ] **Step 2: Remove `ports:` from every service except nginx**; replace with `expose:` where inter-service documentation is useful. Move the removed mappings into `docker-compose.dev.yml` with `127.0.0.1:` prefixes, e.g. `- "127.0.0.1:5432:5432"`.

- [ ] **Step 3: Redis authentication and durability** (`infra/redis/redis.conf`)

```conf
bind 0.0.0.0
protected-mode yes
appendonly yes
appendfsync everysec
save 300 10
maxmemory 256mb
maxmemory-policy noeviction
```
Redis does not expand env vars in the file: run it with `command: ["sh","-c","redis-server /usr/local/etc/redis/redis.conf --requirepass \"$$REDIS_PASSWORD\""]` and add a `redis_data:/data` volume. Update every `AZTDP_REDIS_URL` to `redis://:${REDIS_PASSWORD_URLENCODED}@redis:6379/0` and the Redis healthcheck to `redis-cli -a "$$REDIS_PASSWORD" ping`.

- [ ] **Step 4: Verify**

Run: `bash scripts/check_exposure.sh` → `exposure OK`. Then `docker compose up -d && docker compose exec gateway curl -sf http://opa:8181/health` (internal still works) and, from the host, `curl -m 2 localhost:8181` → connection refused.

- [ ] **Step 5: Commit**

```bash
git add docker-compose*.yml infra/redis scripts/check_exposure.sh
git commit -m "fix(security): publish only ingress, require redis auth, enable AOF/noeviction"
```

### Task 5: Make step-up safe (Redis-backed, rate-limited, no default secrets)

**Files:**
- Modify: `services/django-app/core/stepup.py`, `services/django-app/core/views.py`, `services/django-app/core/middleware.py`, `services/django-app/aztdp_django/settings.py`, `services/django-app/requirements.txt` (add `redis==5.0.4`)
- Test: `services/django-app/tests/test_stepup_flow.py` (extend), `services/django-app/tests/test_stepup_hardening.py` (create)

**Interfaces:**
- Produces (unchanged names, new behavior):
  - `create_challenge(challenge_id: str, user_id: str, jti_hash: str = "") -> None`
  - `challenge_exists(challenge_id: str, user_id: str) -> bool`
  - `verify_challenge(challenge_id: str, totp_code: str, user_id: str) -> Optional[str]` — returns `None` on bad code **and** increments a per-challenge attempt counter; after `MAX_ATTEMPTS = 5` the challenge is destroyed.
  - `verify_step_up_token(token: str, user_id: str, access_jti_hash: str) -> bool` — token now carries `jti_hash` and must match.
  - `class StepUpConfigError(RuntimeError)` raised by `load_config(debug: bool)` when `AZTDP_STEPUP_SIGNING_KEY` or `AZTDP_TOTP_MASTER_SECRET` is unset and `debug` is false.
  - Test helpers `current_totp_for_tests(user_id) -> str`, `mint_for_tests(user_id, challenge_id, jti_hash) -> str`.
- Store protocol: `get_store() -> redis.Redis` (injectable in tests with `fakeredis`).

- [ ] **Step 1: Write failing tests**

```python
# services/django-app/tests/test_stepup_hardening.py
import fakeredis
import pytest
from core import stepup


@pytest.fixture(autouse=True)
def _store(monkeypatch):
    shared = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(stepup, "get_store", lambda: shared)


def test_challenge_visible_to_another_worker():
    stepup.create_challenge("c1", "u1")           # "worker A"
    assert stepup.challenge_exists("c1", "u1")     # "worker B" shares the store


def test_attempt_limit_destroys_challenge():
    stepup.create_challenge("c2", "u1")
    for _ in range(stepup.MAX_ATTEMPTS):
        assert stepup.verify_challenge("c2", "000000", "u1") is None
    good = stepup.current_totp_for_tests("u1")
    assert stepup.verify_challenge("c2", good, "u1") is None   # too late


def test_token_bound_to_access_token():
    tok = stepup.mint_for_tests("u1", "c3", jti_hash="AAA")
    assert stepup.verify_step_up_token(tok, "u1", "AAA") is True
    assert stepup.verify_step_up_token(tok, "u1", "BBB") is False


def test_missing_secrets_fail_closed(monkeypatch):
    monkeypatch.delenv("AZTDP_STEPUP_SIGNING_KEY", raising=False)
    with pytest.raises(stepup.StepUpConfigError):
        stepup.load_config(debug=False)
```

- [ ] **Step 2: Run to confirm failure**

Run: `bash scripts/run_tests.sh django-app` → Expected: new tests FAIL (`AttributeError: ... challenge_exists`).

- [ ] **Step 3: Implement**

Key code (replace the module-level dict and constants in `stepup.py`):

```python
MAX_ATTEMPTS = 5
_CHALLENGE_TTL = 300

class StepUpConfigError(RuntimeError):
    pass

def load_config(debug: bool) -> tuple[str, str]:
    signing = os.getenv("AZTDP_STEPUP_SIGNING_KEY", "")
    master = os.getenv("AZTDP_TOTP_MASTER_SECRET", "")
    if not debug and (not signing or not master):
        raise StepUpConfigError("AZTDP_STEPUP_SIGNING_KEY and AZTDP_TOTP_MASTER_SECRET are required")
    return signing or "dev-only-signing-key", master or "dev-only-master-secret"

def _user_secret(user_id: str) -> bytes:
    # Per-user secret derived from the master secret; enrollment (showing it to the
    # user's authenticator) is Open Question Q1 — until then this removes the
    # single shared secret.
    return hmac.new(_MASTER.encode(), user_id.encode(), hashlib.sha256).digest()

def create_challenge(challenge_id, user_id, jti_hash=""):
    r = get_store()
    key = f"stepup:chal:{challenge_id}"
    r.hset(key, mapping={"user_id": user_id, "attempts": 0, "jti_hash": jti_hash})
    r.expire(key, _CHALLENGE_TTL)

def verify_challenge(challenge_id, totp_code, user_id):
    r = get_store(); key = f"stepup:chal:{challenge_id}"
    entry = r.hgetall(key)
    if not entry or entry["user_id"] != user_id:
        return None
    if r.hincrby(key, "attempts", 1) > MAX_ATTEMPTS:
        r.delete(key); return None
    if not _verify_totp(totp_code, _user_secret(user_id)):
        return None
    r.delete(key)                                   # one-shot
    return _mint_step_up_token(user_id, challenge_id, entry.get("jti_hash", ""))
```
`_verify_totp`/`_hotp` currently take the secret as a base32 `str`; change them to accept `bytes` (drop the base32 decode branch). In `middleware._stepup`, pass `token_jti_hash` into `create_challenge`; in the `stepup` branch pass it to `verify_step_up_token(step_up_header, subject_id, token_jti_hash)`. Include `jti_hash` in the token payload, require equality, and shorten `_STEP_UP_TOKEN_TTL` to 300 s. In `views.step_up_verify` **stop trusting `user_id` from the body**: read the challenge's stored `user_id` and reject if the body's differs. Add per-IP throttling (`INCR stepup:ip:{ip}` with 60 s TTL, max 20) using `resolve_client_ip`. Wire the Redis URL via `settings.AZTDP["REDIS_URL"]` (compose: `AZTDP_REDIS_URL`).

- [ ] **Step 4: Run to confirm pass**

Run: `bash scripts/run_tests.sh django-app` → all pass, including the original 12 `test_stepup_flow` tests (update them to the new signatures where they call `verify_step_up_token` / `create_challenge`).

- [ ] **Step 5: Live check with 4 workers**

Run: `docker compose up -d --build django-app`, trigger a stepup decision, call verify 20× — Expected: success rate 100% (was ~25%).

- [ ] **Step 6: Commit**

```bash
git add services/django-app
git commit -m "fix(security): redis-backed step-up with attempt limit, per-user secret, bound tokens"
```

### Task 6: Production profile for identity, Django and the demo tooling

**Files:**
- Modify: `docker-compose.yml`, `services/django-app/aztdp_django/settings.py`, `services/django-app/core/urls.py`, `infra/keycloak/aztdp-realm.json`, `services/attack-sim/api.py`
- Create: `docker-compose.dev.yml` additions, `infra/keycloak/aztdp-realm.dev.json`, `infra/keycloak/Dockerfile`, `services/django-app/tests/test_settings_prod.py`

**Interfaces:**
- Produces: `settings.py` raises `ImproperlyConfigured` when `DEBUG` is false and `AZTDP_SECRET_KEY` is unset, shorter than 32 chars, or equal to a known default.

- [ ] **Step 1: Failing test**

```python
# services/django-app/tests/test_settings_prod.py
import importlib, pytest
from django.core.exceptions import ImproperlyConfigured

def _reload(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import aztdp_django.settings as s
    return importlib.reload(s)

def test_prod_requires_real_secret(monkeypatch):
    with pytest.raises(ImproperlyConfigured):
        _reload(monkeypatch, AZTDP_DEBUG="false", AZTDP_SECRET_KEY="change-me")

def test_prod_requires_allowed_hosts(monkeypatch):
    with pytest.raises(ImproperlyConfigured):
        _reload(monkeypatch, AZTDP_DEBUG="false", AZTDP_SECRET_KEY="x"*50, AZTDP_ALLOWED_HOSTS="")
```
Run → Expected FAIL (no exception raised).

- [ ] **Step 2: Implement in `settings.py`**

```python
from django.core.exceptions import ImproperlyConfigured
SECRET_KEY = os.getenv("AZTDP_SECRET_KEY", "")
if not DEBUG:
    if len(SECRET_KEY) < 32 or SECRET_KEY in {"change-me", "ci-secret", "test-secret"}:
        raise ImproperlyConfigured("AZTDP_SECRET_KEY must be set to a random value >=32 chars")
    if not ALLOWED_HOSTS:
        raise ImproperlyConfigured("AZTDP_ALLOWED_HOSTS must be set when DEBUG is false")
else:
    SECRET_KEY = SECRET_KEY or "dev-insecure-key"
```
Also set `SESSION_COOKIE_HTTPONLY`, `CSRF_COOKIE_HTTPONLY`, `SECURE_REFERRER_POLICY`, and gate the demo `ui/` route in `core/urls.py` and the `"/ui"` allow-list entry on `settings.DEBUG` (the demo UI must not be served in production).

- [ ] **Step 3: Compose** — base file: `AZTDP_DEBUG: "false"`, remove the Django `ports`, add `AZTDP_REDIS_URL`, `AZTDP_STEPUP_SIGNING_KEY`, `AZTDP_TOTP_MASTER_SECRET`, `AZTDP_TRUSTED_PROXIES: <nginx network CIDR>` (otherwise client-IP/geo trust is disabled and every request appears to come from nginx — verify by reading `core/client_ip.py` behavior with the CIDR set). Keycloak: `command: ["start","--optimized"]` with `KC_HOSTNAME`, `KC_PROXY_HEADERS=xforwarded`, `KC_HTTP_ENABLED=false` behind TLS ingress; build step `kc.sh build` in `infra/keycloak/Dockerfile`. Move the dev items (`start-dev`, seeded realm, `DEBUG=true`) into `docker-compose.dev.yml`.

- [ ] **Step 4: Split the realm**

`aztdp-realm.dev.json` = current file (dev only, mounted by the dev override). New `aztdp-realm.json` (prod): `sslRequired: external`, **no `users`**, client `aztdp-client` `directAccessGrantsEnabled: false`, `publicClient: false`, secret rendered from `${KEYCLOAK_CLIENT_SECRET}` with `envsubst` in the Keycloak Dockerfile, explicit `redirectUris`/`webOrigins` (no `*`), `passwordPolicy: "length(14) and notUsername"`, OTP policy configured, `accessTokenLifespan: 300` kept.

- [ ] **Step 5: Attack-sim to a profile**

In the dev override, give `attack-sim` `profiles: ["sim"]`, move its credentials to the dev override, and in `api.py` replace `allow_origins=["*"]` with `allow_origins=os.getenv("AZTDP_SIM_ORIGINS","").split(",")` plus require `X-Internal-Token` on `POST /v1/sim/*` (copy `internal_auth.py` as in Task 3). Remove `attack-sim` from the base compose and from the dashboard's `depends_on`.

- [ ] **Step 6: Verify**

Run: `bash scripts/run_tests.sh django-app` (pass); `docker compose config | grep -E "DEBUG|start-dev|aztdp-secret|password"` → no hits in the base file; `docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile sim up -d` still brings up the dev stack.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "fix(security): production profile — fail-closed settings, split realms, sim behind dev profile"
```

### Task 7: Container hardening and Prometheus port mismatch

**Files:**
- Modify: every `services/*/Dockerfile`, `docker-compose.yml`, `infra/prometheus/prometheus.yml`, `services/django-app/requirements.txt`, `services/gateway/requirements.txt`
- Create: `services/*/.dockerignore`, `scripts/lint_dockerfiles.sh`

- [ ] **Step 1: Failing check** — `scripts/lint_dockerfiles.sh` runs `docker run --rm -i hadolint/hadolint < services/<svc>/Dockerfile` for each service and additionally greps each Dockerfile for `USER` and `HEALTHCHECK`. Run → Expected: FAIL (no USER/HEALTHCHECK anywhere).

- [ ] **Step 2: Apply this pattern to every Python service** (shown for gateway)

```dockerfile
FROM python:3.12-slim@sha256:<pin-current-digest>
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --no-create-home app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=app:app . ./gateway/
USER app
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD curl -sf http://localhost:8080/health || exit 1
CMD ["uvicorn", "gateway.app:app", "--host", "0.0.0.0", "--port", "8080"]
```
(`<pin-current-digest>`: obtain with `docker buildx imagetools inspect python:3.12-slim` at execution time and paste the real digest.) Anomaly-service additionally `RUN mkdir -p /app/models && chown app:app /app/models`. Django: make the Dockerfile's port **8000** and gunicorn bind `0.0.0.0:8000` so image, compose and Prometheus agree; move `migrate` out of the app container's start command into a one-shot `django-migrate` service (`restart: "no"`, `depends_on` postgres) — four workers racing `migrate` is unsafe. Spring: add a non-root `USER` and a `HEALTHCHECK` against `/actuator/health`; the image build keeps `-Dmaven.test.skip=true` because CI runs `mvn verify` (Task 16). Add `.dockerignore` (`__pycache__`, `tests/`, `.git`, `*.md`).

- [ ] **Step 3: Fix Prometheus** — `infra/prometheus/prometheus.yml` job `django-app` target → `django-app:8000`. Add `read_only: true` + `tmpfs: [/tmp]` to stateless services in compose where they start cleanly (verify per service; anomaly-service needs its model volume writable).

- [ ] **Step 4: Dependency cleanup (F-19)** — remove the duplicate `python-json-logger` line in `django-app/requirements.txt`; align `psycopg[binary]` to `3.2.1` in gateway; add `pip-compile --generate-hashes` outputs (`requirements.lock`) and install with `--require-hashes` in Dockerfiles.

- [ ] **Step 5: Verify**

Run: `bash scripts/lint_dockerfiles.sh` → PASS; `docker compose up -d --build && docker compose ps` → all `healthy`; `docker compose exec gateway id -u` → `10001`; Prometheus targets page (dev override) → `django-app` UP.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore(docker): non-root, healthchecks, digests, django port/migrate fix"
```

---

## Phase C — Data durability and audit integrity

### Task 8: One migration path, per-service DB roles, append-only audit

**Files:**
- Create: `infra/postgres/04_roles.sql`, `scripts/db/migrate.sh`, `scripts/db/tests/test_roles.sh`
- Modify: `docker-compose.yml`, `scripts/db/schema.sql`, `infra/postgres/03_grants.sql`, per-service `AZTDP_DB_URL`

**Interfaces:**
- Produces roles: `aztdp_owner` (migrations only), `aztdp_ingest` (INSERT on audit/derived tables, UPDATE on `sessions`; **no** UPDATE/DELETE on `audit_events`), `aztdp_forensics` (SELECT only), `aztdp_gateway` (SELECT/INSERT on `token_revocations` — required by Task 9), `aztdp_anomaly` (SELECT/INSERT/UPDATE on `anomaly_baselines`), `aztdp_django` (Django's own tables).

- [ ] **Step 1: Failing role test**

```bash
# scripts/db/tests/test_roles.sh  (run against a fresh compose postgres)
set -e
psql() { docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "$1" -d aztdp -c "$2"; }
psql aztdp_ingest "INSERT INTO audit_events(event_id,event_type,service) VALUES (gen_random_uuid(),'risk_eval','t')"
! psql aztdp_ingest "UPDATE audit_events SET service='x'"   && echo "update correctly denied"
! psql aztdp_ingest "DELETE FROM audit_events"              && echo "delete correctly denied"
! psql aztdp_forensics "INSERT INTO audit_events(event_id,event_type,service) VALUES (gen_random_uuid(),'x','x')" && echo "forensics read-only"
```
Run → Expected: FAIL (roles don't exist).

- [ ] **Step 2: Reconcile schema vs migrations** — decide the single source: make `V1__initial_schema.sql` + `V2__audit_partitioning.sql` authoritative (they are versioned and match the runbook); generate `schema.sql` from them or delete it. Write `scripts/db/migrate.sh` that applies `scripts/db/migrations/V*.sql` in order, recording each in the existing `schema_migrations` table, idempotently. Run it from a one-shot `db-migrate` compose service that runs after postgres is healthy and before any app starts (`depends_on: db-migrate: condition: service_completed_successfully`). Diff the V1 output against the current `schema.sql` (`pg_dump --schema-only`) and fix any drift in the migration, not the live schema. (This diff was not performed during analysis.)

- [ ] **Step 3: Roles** (`04_roles.sql`) — create the roles listed above with `LOGIN PASSWORD` from env via `psql -v`, `REVOKE ALL ON ALL TABLES … FROM PUBLIC`, then grant exactly the permissions in the Interfaces list; add `REVOKE UPDATE, DELETE, TRUNCATE ON audit_events FROM aztdp_ingest` and a trigger `audit_events_immutable` that raises on UPDATE/DELETE for any role except `aztdp_owner` (the retention procedure runs as owner).

- [ ] **Step 4: Update connection strings** — each service's `AZTDP_DB_URL` uses its own role/password (`.env.example` gets `PG_INGEST_PASSWORD`, `PG_FORENSICS_PASSWORD`, …). Keycloak keeps its own database (`KC_DB_URL` → separate `keycloak` DB) so a Keycloak compromise cannot touch audit data.

- [ ] **Step 5: Verify**

Run: `docker compose down -v && docker compose up -d && bash scripts/db/tests/test_roles.sh` → prints the three "correctly denied" lines, exit 0. Run `docker compose exec postgres psql -U aztdp_owner -d aztdp -c "\d+ audit_events" | grep -i partition` → shows `PARTITION BY RANGE (occurred_at)`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(db): single migration path, least-privilege roles, immutable audit_events"
```

### Task 9: Durable, correct token revocation

**Files:**
- Modify: `services/gateway/app.py`, `services/gateway/revocation_store.py`, `services/gateway/config.py`, `services/django-app/core/middleware.py`, `services/django-app/core/revocation_client.py`, `services/spring-app/src/main/java/com/aztdp/springapp/client/TokenRevocationClient.java`, `services/spring-app/src/main/java/com/aztdp/springapp/security/RiskEnforcementFilter.java`
- Test: `services/gateway/tests/test_revocation_durability.py`, `services/gateway/tests/conftest.py` (fixtures)

**Interfaces:**
- `RevokeRequest` gains `expires_at: Optional[int]` (epoch seconds, the access token's `exp`). Redis TTL = `max(1, expires_at - now)` when present, else `REVOCATION_TTL_SECONDS`.
- `RevocationStore.__init__(self, redis=None, db=None)`; `revoke(token_hash: str, expires_at: Optional[int] = None) -> None` writes **Postgres then Redis, synchronously**; raises `RevocationPersistError` if the DB write fails.
- `POST /v1/tokens/revoke` returns `503 revocation_not_persisted` if persistence failed (caller then denies — fail closed).
- `db` protocol: `insert_revocation(token_hash, expires_at)` and `active() -> list[tuple[str, Optional[int]]]`.

- [ ] **Step 1: Failing tests**

```python
# services/gateway/tests/test_revocation_durability.py
import pytest
from gateway.revocation_store import RevocationStore, RevocationPersistError

def test_revoke_persists_to_db_before_returning(fake_redis, fake_db):
    s = RevocationStore(redis=fake_redis, db=fake_db)
    s.revoke("h1", expires_at=None)
    assert [r[0] for r in fake_db.rows] == ["h1"]
    assert fake_redis.exists("revoked:token:h1")

def test_db_failure_fails_closed(fake_redis, failing_db):
    s = RevocationStore(redis=fake_redis, db=failing_db)
    with pytest.raises(RevocationPersistError):
        s.revoke("h1")

def test_ttl_follows_token_exp(fake_redis, fake_db, monkeypatch):
    monkeypatch.setattr("gateway.revocation_store.time.time", lambda: 1_000_000.0)
    s = RevocationStore(redis=fake_redis, db=fake_db)
    s.revoke("h1", expires_at=1_000_120)
    assert 100 <= fake_redis.ttl("revoked:token:h1") <= 120

def test_resync_restores_after_redis_flush(fake_redis, fake_db):
    fake_db.rows = [("h9", None)]
    s = RevocationStore(redis=fake_redis, db=fake_db)
    s.cold_start_recovery()
    assert s.is_revoked("h9")
```
Fixtures in `tests/conftest.py`: `fake_redis` = `fakeredis.FakeRedis(decode_responses=True)`; `fake_db` = small class with `rows: list`, `insert_revocation()` appending `(hash, exp)` and `active()` returning `rows`; `failing_db` = same but `insert_revocation()` raises `RuntimeError`. Add `fakeredis` to a new `services/gateway/requirements-dev.txt`.

- [ ] **Step 2: Run to confirm failure** — `bash scripts/run_tests.sh gateway` → FAIL (`ImportError: RevocationPersistError`).

- [ ] **Step 3: Implement** — inject `redis` and `db` into `RevocationStore.__init__` (defaults build from config so production wiring is unchanged); `revoke()` first `INSERT … ON CONFLICT DO NOTHING` into `token_revocations` using a short-lived psycopg connection pool, wrapping any exception in `RevocationPersistError`, then `SETEX`. In `app.revoke_token`, catch `RevocationPersistError` → `HTTPException(503, "revocation_not_persisted")`. Keep the telemetry audit event (it records who/why) but it is no longer the persistence path. Add `periodic_resync()` (every 60 s, daemon thread started in `_on_startup`) that re-seeds missing Redis keys from the DB, covering a Redis restart without a gateway restart. Pass `exp` from Django (`claims["exp"]` → `expires_at`) and Spring (`jwt.getExpiresAt()`); treat a 503 from the revoke endpoint as a failed revocation that still denies the current request.

- [ ] **Step 4: Run to confirm pass** — `bash scripts/run_tests.sh gateway django-app` → PASS; `mvn -B -f services/spring-app/pom.xml test` → PASS.

- [ ] **Step 5: Chaos check** — revoke a token, then `docker compose restart redis`, wait one resync period, call the protected endpoint with that token → Expected: `403 token_revoked`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "fix(gateway): synchronous durable revocation with token-exp TTL and periodic resync"
```

### Task 10: Audit telemetry reliability + the two untested services

**Files:**
- Modify: `services/gateway/telemetry.py`, `services/risk-engine/telemetry.py`, `services/gateway/metrics.py`, `services/risk-engine/metrics.py`, `infra/prometheus/rules/aztdp.rules.yml`, `services/forensics/app.py` (typed time parameters)
- Create: `services/gateway/tests/test_telemetry_reliability.py`, `services/telemetry-ingest/tests/{__init__,conftest,test_ingest}.py`, `services/forensics/tests/test_queries.py`

**Interfaces:**
- Produces metric `aztdp_telemetry_dropped_total{service,reason}` (counter) and `aztdp_telemetry_retry_total{service}`; Python names `metrics.TELEMETRY_DROPPED`, `metrics.TELEMETRY_RETRIES`.
- `emit_async(event_type, payload)` keeps its signature; internally retries 3× with backoff (50/150/450 ms) in the worker thread, then increments the drop counter and logs at **WARNING** with the event type and request id.

- [ ] **Step 1: Failing tests**

```python
# services/gateway/tests/test_telemetry_reliability.py
import requests
from gateway import metrics, telemetry

class _Resp:  # minimal stand-in; telemetry only needs the call to not raise
    status_code = 200

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
    monkeypatch.setattr(telemetry.requests, "post",
                        lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("down")))
    monkeypatch.setattr(telemetry.time, "sleep", lambda s: None)
    monkeypatch.setattr(telemetry.config, "TELEMETRY_URL", "http://t")
    before = metrics.TELEMETRY_DROPPED.labels(service="gateway", reason="exhausted")._value.get()
    telemetry._post("policy_decision", {"request_id": "r"})
    after = metrics.TELEMETRY_DROPPED.labels(service="gateway", reason="exhausted")._value.get()
    assert after == before + 1
    assert any(r.levelname == "WARNING" for r in caplog.records)
```
```python
# services/telemetry-ingest/tests/test_ingest.py  (FastAPI TestClient + stub pool in conftest)
def test_requires_internal_token(client):
    assert client.post("/v1/telemetry/event", json={"event_type": "risk_eval", "service": "t"}).status_code == 401

def test_invalid_event_type_400(client, auth_headers):
    r = client.post("/v1/telemetry/event", json={"event_type": "nope", "service": "t"}, headers=auth_headers)
    assert r.status_code == 400

def test_policy_decision_is_denormalized(client, auth_headers, stub_pool):
    body = {"event_type": "policy_decision", "service": "gateway", "request_id": "r1",
            "payload": {"decision": "deny", "reason": {"rule": "admin_required"}}}
    assert client.post("/v1/telemetry/event", json=body, headers=auth_headers).status_code == 200
    assert any("INSERT INTO policy_decisions" in sql for sql, _ in stub_pool.executed)

def test_db_error_returns_500(client, auth_headers, stub_pool):
    stub_pool.fail_next = True
    body = {"event_type": "risk_eval", "service": "t", "request_id": "r"}
    assert client.post("/v1/telemetry/event", json=body, headers=auth_headers).status_code == 500
```
`conftest.py` provides `client` (TestClient over `telemetry_ingest.app`), `auth_headers`, and `stub_pool`: a fake with `.connection()` context manager → `.cursor()` context manager → `.execute(sql, params)` appending to `.executed`, raising when `fail_next` is set; monkeypatch it over `telemetry_ingest.app.get_pool`.
```python
# services/forensics/tests/test_queries.py  (same stub-pool pattern)
def test_invalid_since_returns_422(client, auth_headers):
    assert client.get("/v1/forensics/events?since=not-a-date", headers=auth_headers).status_code == 422

def test_limit_above_max_returns_422(client, auth_headers):
    assert client.get("/v1/forensics/events?limit=100000", headers=auth_headers).status_code == 422
```

- [ ] **Step 2: Run to confirm failure** — `bash scripts/run_tests.sh gateway telemetry-ingest forensics` → FAIL.

- [ ] **Step 3: Implement** — retry loop + counters in both telemetry modules (the two copies are near-identical; keep them in sync — lifting into a shared package is YAGNI until a third consumer appears). In forensics change `since`/`until` to `Optional[datetime]` so FastAPI validates them (422 instead of a 500 from the SQL cast) and pass the datetime object as the SQL parameter.

- [ ] **Step 4: Alert rule** — add to `aztdp.rules.yml`:

```yaml
- alert: AuditTelemetryDropping
  expr: increase(aztdp_telemetry_dropped_total[5m]) > 0
  for: 1m
  labels: {severity: critical}
  annotations:
    summary: "Audit events are being dropped ({{ $labels.service }})"
```

- [ ] **Step 5: Verify** — `bash scripts/run_tests.sh` (all six services) → exit 0; restore the full `testpaths` list in `pytest.ini`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(telemetry): retry + drop metric + alert; add telemetry-ingest and forensics tests"
```

### Task 11: Signed anomaly-model artifacts

**Files:**
- Modify: `services/anomaly-service/model.py`, `services/anomaly-service/config.py`, `docker-compose.yml`
- Test: `services/anomaly-service/tests/test_model_integrity.py`

**Interfaces:**
- `AnomalyModel.save()` writes `isolation_forest_<v>.pkl` and `isolation_forest_<v>.pkl.sig` (hex HMAC-SHA256 of the file bytes with `config.MODEL_HMAC_KEY`, sourced from `AZTDP_MODEL_HMAC_KEY`).
- `AnomalyModel.load(version) -> bool` returns `False` and logs `ERROR model_signature_invalid` if the signature is missing or wrong; **never** calls `joblib.load` on an unverified file. Versions not matching `^v[0-9A-Za-z._-]+$` are rejected before any path is built.

- [ ] **Step 1: Failing tests**

```python
import numpy as np
import pytest
from anomaly_service import config
from anomaly_service.model import AnomalyModel


@pytest.fixture
def fitted_model(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(config, "MODEL_HMAC_KEY", "k" * 32, raising=False)
    m = AnomalyModel()
    m.fit(np.random.RandomState(0).rand(200, 8), "v1")
    return m


def test_tampered_model_is_rejected(fitted_model):
    p = fitted_model.save()
    p.write_bytes(p.read_bytes() + b"x")
    fresh = AnomalyModel()
    assert fresh.load("v1") is False and not fresh.is_loaded


def test_unsigned_model_is_rejected(fitted_model):
    p = fitted_model.save()
    p.with_name(p.name + ".sig").unlink()
    assert AnomalyModel().load("v1") is False


def test_valid_roundtrip(fitted_model):
    fitted_model.save()
    m = AnomalyModel()
    assert m.load("v1") and m.is_loaded


def test_path_traversal_version_rejected(fitted_model):
    assert AnomalyModel().load("../../etc/passwd") is False
```
(Check the feature-vector width in `feature_engineering.py` and use it in place of `8` if different.)

- [ ] **Step 2: Run to confirm failure** — `bash scripts/run_tests.sh anomaly-service` → FAIL.

- [ ] **Step 3: Implement**

```python
import hashlib, hmac, io, logging, re
logger = logging.getLogger("aztdp.anomaly.model")
_VERSION_RE = re.compile(r"^v[0-9A-Za-z._-]+$")

def _sign(data: bytes) -> str:
    return hmac.new(config.MODEL_HMAC_KEY.encode(), data, hashlib.sha256).hexdigest()

def save(self) -> Path:
    ...  # existing dump to a BytesIO first, then write bytes + signature
    buf = io.BytesIO(); joblib.dump({...}, buf)
    path.write_bytes(buf.getvalue())
    path.with_name(path.name + ".sig").write_text(_sign(buf.getvalue()))
    return path

def load(self, version: str) -> bool:
    if not _VERSION_RE.match(version or ""):
        return False
    path = Path(config.MODEL_DIR) / f"isolation_forest_{version}.pkl"
    sig = path.with_name(path.name + ".sig")
    if not path.exists() or not sig.exists():
        return False
    data = path.read_bytes()
    if not hmac.compare_digest(_sign(data), sig.read_text().strip()):
        logger.error("model_signature_invalid version=%s", version)
        return False
    bundle = joblib.load(io.BytesIO(data))      # only after verification
    ...
```
`config.MODEL_HMAC_KEY` is read from `AZTDP_MODEL_HMAC_KEY` and the service raises at startup if it is empty. Add the variable to compose for anomaly-service.

- [ ] **Step 4: Run to confirm pass** — `bash scripts/run_tests.sh anomaly-service` → PASS. Note in the commit that existing unsigned models in the `anomaly_models` volume are ignored and the first start after upgrade cold-trains.

- [ ] **Step 5: Commit**

```bash
git add services/anomaly-service docker-compose.yml .env.example
git commit -m "fix(security): HMAC-verify model artifacts before joblib.load; validate version string"
```

---

## Phase D — Operations

### Task 12: Alertmanager and availability alerts

**Files:**
- Create: `infra/alertmanager/alertmanager.yml`, `infra/prometheus/rules/aztdp.rules.test.yml`, `scripts/check_prometheus.sh`
- Modify: `docker-compose.yml`, `infra/prometheus/prometheus.yml`, `infra/prometheus/rules/aztdp.rules.yml`

- [ ] **Step 1: Failing check** — `scripts/check_prometheus.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
docker run --rm -v "$PWD/infra/prometheus:/p" --entrypoint promtool prom/prometheus:v2.53.0 check config /p/prometheus.yml
docker run --rm -v "$PWD/infra/prometheus:/p" --entrypoint promtool prom/prometheus:v2.53.0 check rules /p/rules/aztdp.rules.yml
docker run --rm -v "$PWD/infra/prometheus:/p" --entrypoint promtool prom/prometheus:v2.53.0 test rules /p/rules/aztdp.rules.test.yml
```
and `aztdp.rules.test.yml` asserting that `up{job="gateway"}` = 0 for 3 minutes fires `ServiceDown`:

```yaml
rule_files: [aztdp.rules.yml]
evaluation_interval: 30s
tests:
  - interval: 30s
    input_series:
      - series: 'up{job="gateway"}'
        values: '0x8'
    alert_rule_test:
      - eval_time: 4m
        alertname: ServiceDown
        exp_alerts:
          - exp_labels: {severity: critical, job: gateway}
            exp_annotations: {summary: "gateway is down"}
```
Run → FAIL (rule absent).

- [ ] **Step 2: Add rules**

```yaml
- alert: ServiceDown
  expr: up == 0
  for: 2m
  labels: {severity: critical}
  annotations: {summary: "{{ $labels.job }} is down"}
- alert: FailClosedDenialSpike     # a dependency outage shows up as risk_unavailable/policy_unavailable denials
  expr: sum(rate(aztdp_policy_decisions_total{decision="deny"}[5m])) > 20
  for: 5m
  labels: {severity: warning}
  annotations: {summary: "Sustained denial spike — check dependencies"}
```

- [ ] **Step 3: Alertmanager** — service `prom/alertmanager:v0.27.0`; config routes `severity=critical` to a webhook receiver whose URL comes from `ALERT_WEBHOOK_URL` (render with `envsubst` at container start); wire `alerting.alertmanagers` in `prometheus.yml`.

- [ ] **Step 4: Verify** — `bash scripts/check_prometheus.sh` → `SUCCESS` ×3; `docker compose stop gateway`, wait 3 min → alert visible at Alertmanager `/api/v2/alerts` and delivered to the webhook receiver.

- [ ] **Step 5: Commit** — `git commit -m "feat(ops): alertmanager, service-down and denial-spike alerts"`

### Task 13: Backups and tested restore

**Files:**
- Create: `scripts/backup/pg_restore_test.sh`, `docs/runbooks/BACKUP_RESTORE.md`
- Modify: `docker-compose.yml` (add `pg-backup` service: `prodrigestivill/postgres-backup-local:16`, daily schedule, 7 daily / 4 weekly retention, `pg_backups` volume)

- [ ] **Step 1: Write the restore test first** — `pg_restore_test.sh`: start a throw-away `postgres:16-alpine` container, restore the newest dump from the `pg_backups` volume, and assert `SELECT count(*) FROM token_revocations` and `SELECT count(*) FROM audit_events` match the source within the backup interval; exit non-zero otherwise.

- [ ] **Step 2: Run** — `bash scripts/backup/pg_restore_test.sh` → FAIL (no backup yet).

- [ ] **Step 3: Implement backup service** and the runbook: RPO 24 h / RTO 1 h targets, restore steps, and the **Redis note** — Redis is rebuildable from Postgres (Task 9), so it is not backed up. Document WAL archiving as the path to a smaller RPO.

- [ ] **Step 4: Verify** — trigger a backup (`docker compose exec pg-backup /backup.sh`), run `pg_restore_test.sh` → exit 0. Record the measured restore time in the runbook.

- [ ] **Step 5: Commit** — `git commit -m "feat(ops): postgres backups with automated restore verification"`

### Task 14: Resource limits, restart policy, and a load-test baseline

**Files:**
- Modify: `docker-compose.yml`, `scripts/load/locustfile.py`, `scripts/load/README.md`
- Create: `docs/PERFORMANCE_BASELINE.md`

- [ ] **Step 1:** Add `restart: unless-stopped`, `deploy.resources.limits` (cpu/memory) and `stop_grace_period: 15s` (the telemetry drain needs it) to every service; set uvicorn workers via `--workers ${UVICORN_WORKERS:-2}` for gateway/risk-engine/forensics/telemetry-ingest (anomaly-service stays single-worker because of the in-process model + scheduler — document why in the compose file).
- [ ] **Step 2:** Define SLOs in `docs/PERFORMANCE_BASELINE.md`: end-to-end p99 < 250 ms at the target request rate on the reference host; error rate < 0.1 %. Agree the numbers with the owner before gating on them.
- [ ] **Step 3:** Run `locust -f scripts/load/locustfile.py --headless -u 200 -r 20 -t 5m --host https://localhost` against the production profile; record p50/p95/p99, error rate, CPU/memory per service. If p99 exceeds the SLO, tune `AZTDP_TIMEOUT_*` (compose sets connect=1.0 s while the code default is 0.2 s — pick one and document it) and add `requests.Session` connection pooling in the Django clients.
- [ ] **Step 4:** Commit — `git commit -m "chore(ops): limits, restart policy, measured performance baseline"`

---

## Phase E — Delivery pipeline and product surface

### Task 15: Documentation truth pass

**Files:**
- Modify: `docs/PRODUCTION_READINESS.md`, `README.md`
- Delete/merge: `GETTING_STARTED.md`, `GUIDE_INDEX.md`, `WINDOWS_SETUP_GUIDE.md`, `WINDOWS_SUMMARY.md`, `PLATFORM_VERIFICATION_CHECKLIST.md`, `.github/copilot-instructions.md`
- Create: `docs/GO_LIVE_CHECKLIST.md`, `docs/KNOWN_LIMITATIONS.md`, `CHANGELOG.md`

- [ ] **Step 1:** Collapse the five root guides into `docs/runbooks/QUICK_START_GUIDE.md` (+ a Windows section); keep one README with a 30-line quickstart and links.
- [ ] **Step 2:** Rewrite `PRODUCTION_READINESS.md`: add this plan's Findings Register IDs, reopen items that were falsely "done" (P1.3 tests, P1.5, P4.1 `.env.example`, P4.4 partitioning), fill **Open Questions** with Q1–Q3 and link this plan, and update the SOC 2 evidence map with the new controls (immutable audit — Task 8; alerting — Task 12; backups — Task 13).
- [ ] **Step 3:** `KNOWN_LIMITATIONS.md` gets the accepted limitations list from this plan (non-atomic replay check, IP-change-as-replay, TOTP enrollment).
- [ ] **Step 4:** `GO_LIVE_CHECKLIST.md`: secret generation/rotation, TLS certs from a real CA (replace `gen-certs.sh` self-signed), DNS/hostnames, Keycloak realm import review, restore drill signed off, alert receiver tested, `scripts/check_exposure.sh` green, CI green on the release tag.
- [ ] **Step 5:** Verify every command in the README quickstart on a clean clone (`git clone` → `cp .env.example .env` → fill → `docker compose up`). Commit — `git commit -m "docs: truthful readiness status, go-live checklist, consolidated guides"`

### Task 16: CI/CD rewrite (tests, security gates, release)

**Files:**
- Rewrite: `.github/workflows/ci.yml`
- Create: `.github/workflows/release.yml`, `.github/dependabot.yml`, `scripts/ci_env.sh`

**Interfaces:**
- Consumes: `scripts/run_tests.sh` (Task 1), `scripts/check_exposure.sh` (Task 4), `scripts/check_prometheus.sh` (Task 12), `scripts/lint_dockerfiles.sh` (Task 7), `scripts/db/tests/test_roles.sh` (Task 8).

- [ ] **Step 1: Generate a CI `.env`** — `scripts/ci_env.sh` writes a `.env` with random values (`openssl rand -hex 32`) for every key in `.env.example` (URL-encoded variants derived with `python -c urllib.parse.quote`), so the integration job no longer depends on a committed/missing file (F-02).

- [ ] **Step 2: Replace `ci.yml`** with:

```yaml
name: CI
on:
  push: {branches: [main, develop]}
  pull_request: {branches: [main]}
permissions: {contents: read}
concurrency: {group: "ci-${{ github.ref }}", cancel-in-progress: true}

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: pip install ruff==0.5.0 bandit==1.7.9
      - run: ruff check services/ --select=E,F,W,I,B,S --ignore=E501,S101
      - run: bandit -r services -x '*/tests/*' -ll
      - run: bash scripts/lint_dockerfiles.sh

  python-tests:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix: {service: [gateway, risk-engine, anomaly-service, telemetry-ingest, forensics, django-app]}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12", cache: pip}
      - run: pip install -r services/${{ matrix.service }}/requirements.txt pytest==8.2.2 pytest-cov pytest-django==4.8.0 httpx fakeredis
      - run: |
          cd services/${{ matrix.service }}
          AZTDP_INTERNAL_TOKEN=ci AZTDP_SECRET_KEY=ci-not-used AZTDP_DEBUG=true \
          python -m pytest -q --rootdir=. --cov=. --cov-fail-under=70

  opa-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: open-policy-agent/setup-opa@v2
        with: {version: "0.65.0"}
      - run: opa test policies -v
      - run: opa check --strict policies

  java:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: {distribution: temurin, java-version: "25", cache: maven}
      - run: mvn -B -f services/spring-app/pom.xml verify

  frontend:
    runs-on: ubuntu-latest
    strategy:
      matrix: {app: [services/dashboard, sentinel-command-main]}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: {node-version: "20", cache: npm, cache-dependency-path: "${{ matrix.app }}/package-lock.json"}
      - run: cd ${{ matrix.app }} && npm ci && npm run build && (npm run lint --if-present) && (npm test --if-present)

  supply-chain:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: {fetch-depth: 0}
      - uses: gitleaks/gitleaks-action@v2
      - run: pip install pip-audit && for r in services/*/requirements.txt; do pip-audit -r "$r" --strict; done
      - run: cd sentinel-command-main && npm audit --omit=dev --audit-level=high
      - uses: aquasecurity/trivy-action@0.24.0
        with: {scan-type: fs, severity: "CRITICAL,HIGH", exit-code: "1", ignore-unfixed: true}

  config-checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: bash scripts/ci_env.sh && bash scripts/check_exposure.sh
      - run: bash scripts/check_prometheus.sh

  integration:
    needs: [lint, python-tests, opa-tests, java, frontend, config-checks]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: bash scripts/ci_env.sh
      - run: docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile sim up -d --build --wait --wait-timeout 300
      - run: bash scripts/db/tests/test_roles.sh
      - run: |
          pip install pytest==8.2.2 requests
          AZTDP_RUN_LIVE_TESTS=1 pytest services/attack-sim/test_attack_outcomes.py -ra
      - if: failure()
        run: docker compose logs --tail=200
      - if: always()
        run: docker compose down -v
```
(The attack-sim test's env values — base URL, Keycloak token URL, client id/secret, seeded user — move from the old workflow into `docker-compose.dev.yml` / a `scripts/ci_env.sh` dev block; keep them out of the workflow file.)

- [ ] **Step 3: `release.yml`** — on tag `v*`: build all images with Buildx, tag `ghcr.io/<owner>/aztdp-<svc>:<tag>` (assumes Q3), generate an SBOM (`anchore/sbom-action`), scan with Trivy (fail on CRITICAL), push, sign with `sigstore/cosign-installer` keyless, create a GitHub Release with the SBOM attached. `permissions: {contents: write, packages: write, id-token: write}` only on this workflow.

- [ ] **Step 4: `dependabot.yml`** — weekly updates for `pip` (each `services/*`), `npm` (both UIs), `maven`, `docker`, `github-actions`.

- [ ] **Step 5: Verify** — open a PR; every job must be green. Deliberately push a throwaway commit that (a) removes the internal-token header from a gateway test and (b) adds a fake AWS key, confirm `python-tests` and `supply-chain` fail, then revert.

- [ ] **Step 6: Commit** — `git commit -m "ci: per-service matrix, OPA/Java/frontend/security gates, signed release pipeline"`

**Sequencing note:** merge a *minimal* form of this workflow (lint + python-tests + opa-tests) right after Task 2 so a safety net exists during the security work, then extend it as later tasks land.

### Task 17: Quarantine Kubernetes/Helm

**Files:** Move `infra/k8s` and `infra/helm` → `infra/_unsupported/`; Create `infra/_unsupported/README.md`

- [ ] **Step 1:** `git mv infra/k8s infra/_unsupported/k8s && git mv infra/helm infra/_unsupported/helm`; the README states: "Not maintained. Owner decision 2026-05-03: Docker Compose only. Manifests use `:latest`, have no secrets management and no network policies; do not deploy."
- [ ] **Step 2:** `grep -rn "infra/k8s\|infra/helm" --include=*.md --include=*.yml .` and fix or remove each reference.
- [ ] **Step 3:** Commit — `git commit -m "chore: quarantine unsupported k8s/helm manifests"`

### Task 18: One SOC dashboard, wired to real data (depends on Q2)

**Files:**
- Modify: `sentinel-command-main/src/lib/api.ts`, `sentinel-command-main/src/lib/types.ts`, `sentinel-command-main/src/pages/*.tsx`, `sentinel-command-main/vite.config.ts`, `services/forensics/app.py`
- Create: `sentinel-command-main/Dockerfile`, `sentinel-command-main/nginx.conf.template`, `sentinel-command-main/src/test/api.contract.test.ts`, `sentinel-command-main/src/test/fixtures/*.json`, `services/forensics/tests/test_stats.py`
- Delete after parity: `services/dashboard/`

**Interfaces:**
- Consumes: forensics `GET /v1/forensics/events` → `{"events":[…], "count":n, "limit":n, "offset":n}`; `GET /v1/forensics/replay/{session_id}` → `{"session":…, "timeline":[…], "event_count":n}`; `GET /v1/forensics/incidents/{request_id}` → `{"decision":…, "risk":…, "context_window":[…]}` (see `services/forensics/app.py`).
- Produces: `api.events(limit)`, `api.replay(id)`, `api.incident(id)` return the types in `types.ts`, mapped from those shapes by explicit adapter functions `adaptEvents`, `adaptReplay`, `adaptIncident` exported from `api.ts`; new forensics routes `GET /v1/forensics/sessions?suspicious=bool&limit=n` and `GET /v1/forensics/stats/top-rules?since=ISO8601`.

- [ ] **Step 1: Failing contract tests** (vitest) feeding the exact forensics JSON above (captured from the running service into `src/test/fixtures/*.json`) through the adapters and asserting the resulting `AuditEvent[]`, `TimelineEvent[]`, `Incident`. Run `npm test` → FAIL (adapters don't exist; current code returns the raw object where an array is expected).

- [ ] **Step 2: Implement adapters; remove the silent mock fallback.** `wrap()` becomes: if `VITE_USE_MOCK === "true"` return mock, **else** call the real API and let errors propagate to the page's error state (render an explicit "data unavailable" banner, never fabricated data). Default `VITE_USE_MOCK` to `false`; the production build must fail if it is `true` (`vite.config.ts` check on `mode === "production"`).

- [ ] **Step 3: Replace the always-mock endpoints** — `health()` ← Prometheus `up` query; `sessions()` ← new forensics route `GET /v1/forensics/sessions` (reads the existing `sessions` table); `topRules` ← new `GET /v1/forensics/stats/top-rules` (aggregate over `policy_decisions`); `decisionsSeries` ← Prometheus `sum by (decision) (rate(aztdp_policy_decisions_total[5m]))`; `heatmap` ← forensics aggregate over `policy_decisions` grouped by hour × day. Each new forensics route is test-first (`test_stats.py`), authenticated, and parameterized.

- [ ] **Step 4: Containerize** with the same non-root nginx pattern and the Task 3 proxy allow-list (GET-only, internal token injected server-side, basic-auth gate or oauth2-proxy → Keycloak depending on the Q1/Q2 outcome).

- [ ] **Step 5: Verify** — `docker compose up -d --build`, open the UI, stop the forensics container → UI shows the unavailable banner (not mock rows); restart → real events from `audit_events`. `npm test && npm run build` green. Remove `services/dashboard`, update compose/README/CI matrix, commit — `git commit -m "feat(ui): sentinel dashboard on real APIs, no silent mock fallback; retire legacy dashboard"`

---

## Dependency order

`1 → 2 → (3,4,5,6,7 in any order after 2) → 8 → 9 → 10 → 11 → (12,13,14) → 15 → 16 → 17 → 18`.
Tasks 3–7 are independent of each other but all assume Task 1's green baseline. Task 8 must precede 9 (new `aztdp_gateway` DB role) and Task 16 (integration job runs the role test). Task 16 should be merged early in minimal form (see its sequencing note).

## Definition of "production-ready" (exit criteria)

1. `bash scripts/run_tests.sh`, `opa test policies`, `mvn verify` and both frontend builds are green locally and in CI on `main`.
2. `bash scripts/check_exposure.sh` passes; the base `docker-compose.yml` contains no dev secrets, `DEBUG=true`, `start-dev`, or default credentials.
3. A fresh `git clone` + `.env` generation + `docker compose up -d --wait` yields an all-healthy stack and a passing attack-sim integration run.
4. Revocation survives a Redis restart; the audit table rejects UPDATE/DELETE from service roles; telemetry loss is observable and alerting.
5. Restore drill executed and timed; alert delivery tested end-to-end.
6. Load test meets the SLOs recorded in `docs/PERFORMANCE_BASELINE.md`.
7. `docs/PRODUCTION_READINESS.md` has no item marked done that is not covered by an automated test or a checklist entry, and Open Questions Q1–Q3 are answered.

## Self-review

- **Spec coverage:** every finding F-01…F-20 maps to at least one task (F-01→1, F-02→2/16, F-03→2/15/18, F-04/F-05→3, F-06→5, F-07→9, F-08→8/10, F-09→4, F-10→6, F-11→6, F-12→7/14, F-13→11, F-14→8, F-15→12/13, F-16→16, F-17→18, F-18→1/10, F-19→7/16, F-20→15/17).
- **Placeholder scan:** three spots are intentionally "resolve at execution time" because the analysis observed but did not resolve them, each with a concrete command: Task 1 Step 4 (risk-engine drift test and gateway telemetry test failures not root-caused), Task 7 Step 2 (base-image digest to be fetched), Task 8 Step 2 (V1 migration vs `schema.sql` not diffed). No other TBD/TODO items.
- **Type/name consistency:** `require_internal_token`, `X-Internal-Token`, `RevocationStore.revoke(token_hash, expires_at)`, `RevocationPersistError`, `verify_step_up_token(token, user_id, access_jti_hash)`, `create_challenge(challenge_id, user_id, jti_hash)`, `aztdp_telemetry_dropped_total` / `metrics.TELEMETRY_DROPPED`, `AZTDP_MODEL_HMAC_KEY`, `REDIS_PASSWORD(_URLENCODED)` are used identically wherever they appear.
- **Not verified during analysis (executors should check first):** Spring `RiskEnforcementFilter` revocation/step-up behavior beyond the config reviewed; `core/client_ip.py` behavior once `AZTDP_TRUSTED_PROXIES` is set to nginx's network (Task 6 Step 3 says to verify); that the OPA healthcheck (`/opa eval true`) works in the pinned image; the feature-vector width used in Task 11's test fixture.
