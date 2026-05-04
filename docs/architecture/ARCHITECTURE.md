# AZTDP System Architecture

## 1. Overview

AZTDP enforces zero-trust authorization on every authenticated request. Instead of granting access based solely on a valid token, it evaluates behavioral signals — IP drift, geolocation changes, device fingerprint shifts, request rate anomalies — and combines them into a risk score that drives real-time policy decisions.

The system is intentionally **synchronous on the request path**: risk scoring and policy evaluation happen before the business logic handler executes. This trades a bounded latency overhead (~50–150ms) for the security property that no request reaches application code without a fresh authorization decision.

---

## 2. Component Inventory

| Component | Technology | Role | Internal Port | Host Port |
|---|---|---|---|---|
| **Keycloak** | `quay.io/keycloak/keycloak:25.0` | OIDC identity provider; issues JWTs; JWKS endpoint | 8080 | 8080 |
| **PostgreSQL** | `postgres:16-alpine` | Durable audit storage; session aggregation | 5432 | 5432 |
| **Redis** | `redis:7.2-alpine` | Token last-seen state; request rate counters; revocation cache (Phase 6B) | 6379 | 6379 |
| **OPA** | `openpolicyagent/opa:0.65.0-rootless` | Policy decision point; evaluates `authz.rego` | 8181 | 8181 |
| **Gateway** | FastAPI (Python 3.12) | Policy proxy: revocation check → OPA call → decision log | 8080 | 8000 |
| **Risk Engine** | FastAPI (Python 3.12) | Behavioral risk scoring; replay detection | 8080 | 8001 |
| **Anomaly Service** | FastAPI + scikit-learn (Python 3.12) | ML anomaly detection (Isolation Forest); Phase 7 | 8080 | 8002 |
| **Telemetry Ingest** | FastAPI (Python 3.12) | Event persistence to PostgreSQL; Phase 11 | 8080 | 8003 |
| **Forensics** | FastAPI (Python 3.12) | Audit query API; incident reconstruction; Phase 11 | 8080 | 8004 |
| **Django App** | Django 5.x + gunicorn | Business service A; RiskAuthzMiddleware enforces zero-trust | 8080 | 8010 |
| **Spring Boot App** | Spring Boot 4.x, Java 25 | Business service B; RiskEnforcementFilter enforces zero-trust | 8082 | 8011 |
| **Prometheus** | `prom/prometheus:latest` | Metrics collection; scrapes all services | 9090 | 9090 |
| **Grafana** | `grafana/grafana:latest` | Dashboards for policy decisions, risk scores, latency, attack detection | 3000 | 3000 |

---

## 3. Enforcement Architecture

Every protected request follows this decision chain:

```
Request
  │
  ▼
[App Service Middleware / Filter]
  │
  ├─ 1. JWT Verification (JWKS, RS256) ──── fail → 401
  │
  ├─ 2. Risk Evaluation (Risk Engine) ─────── replay_detected → 403
  │         │
  │         └─ 2a. Anomaly Score (Anomaly Service, async) ← Phase 7
  │
  ├─ 3. Policy Decision (Gateway → OPA) ──── unavailable + fail_closed → 403
  │
  └─ 4. Enforcement Action
          ├─ allow   → pass to handler
          ├─ deny    → 403
          ├─ stepup  → 401 + MFA challenge
          └─ revoke  → revoke token + 403
```

Both app services (Django middleware and Spring `RiskEnforcementFilter`) implement this chain identically. They call the same external services with the same timeout budget.

---

## 4. Service Descriptions

### 4.1 Gateway (Policy Gateway)

**Role:** Sole interface between app services and OPA. Adds two responsibilities that OPA cannot own: revocation checking and decision persistence.

**Key behavior:**
- Receives `POST /v1/policy/decision` with a fully-formed `{input: {...}}` body
- Checks in-memory (→ Redis in Phase 6B) revocation store *before* calling OPA — revoked tokens short-circuit immediately
- Calls OPA at `POST /v1/data/aztdp/authz/decision` with the full input
- Logs each decision to stdout as newline-delimited JSON (→ telemetry-ingest in Phase 11)
- Exposes token revocation write endpoint: `POST /v1/tokens/revoke`
- Exposes token revocation read endpoint: `GET /v1/tokens/revoked/{hash}`

**Fail mode:** Configurable via `AZTDP_FAIL_OPEN`. Default: `false` (fail-closed → 503 to caller). Set to `true` in development only.

**Known gap (Phase 6B):** `RevocationStore` is in-memory with no Redis backing. Gateway restart clears all revocations. The risk-engine's `ReplayStore` already demonstrates the correct Redis-backed pattern (`storage.py`); the gateway revocation store will be updated to mirror it.

### 4.2 Risk Engine

**Role:** Stateful behavioral risk scorer. Maintains a per-token "last seen" record (IP, geo, user-agent hash, timestamp) and computes a risk score delta on each request.

**Scoring model:**

```
risk = RISK_BASE (0.10)
     + RISK_SENSITIVITY_WEIGHT (0.15)  ← if endpoint.sensitivity >= 4
     + RISK_IP_DRIFT_WEIGHT    (0.35)  ← if ip != last_seen.ip
     + RISK_UA_DRIFT_WEIGHT    (0.20)  ← if user_agent_hash != last_seen.ua
     + RISK_GEO_DRIFT_WEIGHT   (0.20)  ← if geo != last_seen.geo
     (capped at 1.0)

trust_score = 1.0 - risk_score
```

All weights are configurable via environment variables.

**Replay detection:** If the token's IP changes *and* the change happened within `REPLAY_WINDOW_SECONDS` (60s) of the last recorded request, `replay_detected=True`. The endpoint returns HTTP 409; the calling middleware maps this to a hard 403 regardless of `fail_open`.

**State backend:** `ReplayStore` uses Redis when `AZTDP_REDIS_URL` is set; falls back to `InMemoryStore` otherwise. Redis key: `token:last_seen:{jti_hash}` with TTL = `TOKEN_TTL_SECONDS` (1800s).

**Known gap (Phase 7):** The `POST /v1/risk/evaluate` response currently returns `{risk_score, trust_score, reasons, ttl_seconds}`. The `anomaly_score` field — referenced in both the Java `RiskResponse` model and the Django middleware — is not yet in the Python response. Phase 7 wires the anomaly service call and adds `anomaly_score` to the response.

**Known gap (Phase 6B):** No `/health` endpoint. Required for docker-compose `condition: service_healthy` dependency ordering.

### 4.3 Anomaly Service (Phase 7)

**Role:** ML-based behavioral anomaly detector. Complements the rule-based risk engine with an unsupervised model that can flag unusual patterns without explicitly enumerating attack signatures.

**Model:** Isolation Forest (`scikit-learn`), `n_estimators=100`, `contamination=0.05`. Trained on 11 engineered features: time-of-day, day-of-week, endpoint sensitivity, IP/geo/UA drift flags, request rate, interaction terms, and time-since-last-request. Cold-start uses synthetic baseline; retrains from `anomaly_baselines` table as data accumulates.

**Integration point:** Risk engine calls anomaly service synchronously (150ms timeout) after computing its own risk score. The `anomaly_score` returned is included in the risk engine response and forwarded to the policy gateway as part of the OPA input.

### 4.4 Django App

**Role:** Business service A. Demonstrates zero-trust enforcement in the Python/Django ecosystem. All protected routes go through `RiskAuthzMiddleware` before any view logic runs.

**Middleware chain (in order):**
1. `SecurityMiddleware` (Django built-in)
2. `RiskAuthzMiddleware` (AZTDP enforcement)
3. `CommonMiddleware` (Django built-in)

The middleware short-circuits at step 2 for all protected paths; view handlers only execute on `allow` decisions.

**Endpoint sensitivity (from `settings.py`):**

| Path Prefix | Method | Sensitivity |
|---|---|---|
| `/v1/payments` | GET | 4 (high) |
| `/v1/admin` | POST | 5 (critical) |
| All others | any | 2 (default) |

**Allowlisted paths** (bypass enforcement): `/health`, `/metrics`

### 4.5 Spring Boot App

**Role:** Business service B. Mirrors the Django app's zero-trust enforcement in the Java/Spring ecosystem. The `RiskEnforcementFilter` (`OncePerRequestFilter`) implements the identical decision chain.

**Security configuration:** Spring Security's OAuth2 resource server handles JWT validation against Keycloak's OIDC metadata. `RiskEnforcementFilter` runs *after* Spring Security's JWT validation — the filter receives a fully authenticated `JwtAuthenticationToken` and only then calls the risk engine.

**Bypass paths:** `/health`, `/metrics` are excluded via `shouldNotFilter()`.

**Internal port:** 8082 (from `application.yml`), not 8080 like the Python services.

### 4.6 OPA

**Role:** Policy decision point. Evaluates `policies/opa/rules/authz.rego` against a fully-structured input object.

**Policy location (in container):** Mounted at `/policies`; OPA started with `--watch` flag so it hot-reloads on file change during development.

**Decision path:** `POST /v1/data/aztdp/authz/decision`

**Current rules in `authz.rego`:**

| Rule | Condition | Action |
|---|---|---|
| Default | (none match) | deny |
| `admin_required` | path starts with `/v1/admin`, `admin` not in roles | deny |
| `token_revoked` | `is_token_revoked == true` | revoke |
| `very_high_risk` | `risk_score >= 0.90` | deny |
| `high_risk_stepup` | `risk_score >= 0.65` AND `sensitivity >= 4` | stepup |
| `low_risk_allow` | `risk_score < 0.65` AND `sensitivity < 4` | allow |

### 4.7 Keycloak

**Role:** OIDC identity provider. Issues short-lived access tokens (5 min) with custom claims.

**Realm:** `aztdp`

**Custom JWT claims (added via protocol mappers):**
- `realm_access.roles`: list of realm roles (`user`, `admin`, `risk_override`)
- `risk_score`: user attribute (float) — allows pre-seeding a known-risky user's baseline
- `session_trust`: user attribute (float)
- `jti`: unique token ID (used as revocation handle; hashed before transit)
- `sid`: session ID (used for session-level forensics grouping)

**Brute-force protection:** Enabled; `failureFactor=5`, `maxFailureWaitSeconds=900`.

---

## 5. Communication Patterns

### Synchronous (request path, latency-critical)

All inter-service calls on the enforcement path are synchronous HTTP with enforced timeouts:

| Call | From | To | Timeout (connect / read) | On failure |
|---|---|---|---|---|
| JWT JWKS | App services | Keycloak | 0.2s / 0.8s | 401 (cache miss) |
| Risk evaluation | App services | Risk Engine | 0.2s / 0.8s | 403 or fail-open |
| Anomaly score | Risk Engine | Anomaly Service | — / 0.15s | anomaly_score=0.0 (fail-open) |
| Policy decision | App services | Gateway | 0.2s / 0.8s | 403 or fail-open |
| OPA evaluation | Gateway | OPA | — / 0.8s | 503 or fail-open |
| Token revocation write | App services | Gateway | 0.2s / 0.8s | logged, continues |

### Fire-and-Forget (off request path)

| Call | From | To | Timeout | On failure |
|---|---|---|---|---|
| Telemetry event | Gateway, Risk Engine | Telemetry Ingest | 0.1s | logged, stdout fallback |
| Telemetry event | Anomaly Service | Telemetry Ingest | 0.2s | logged, continues |

### Async (background)

| Process | Service | Schedule |
|---|---|---|
| Model version poll | Anomaly Service | Every 60s |
| JWKS cache refresh | App services | On TTL expiry (5 min) |
| Prometheus scrape | Prometheus | Every 15s |

---

## 6. Latency Budget

The synchronous enforcement chain adds overhead to every protected request. Worst-case (all services respond at p95):

| Step | p95 target | Notes |
|---|---|---|
| JWT verify (JWKS cached) | ~1ms | In-process crypto; JWKS rarely re-fetched |
| Risk evaluation | 50ms | Includes Redis read/write |
| Anomaly score (within risk engine) | 30ms | 150ms hard timeout; Isolation Forest inference <1ms |
| Policy decision (gateway) | 30ms | Includes OPA evaluation |
| OPA policy eval | 5ms | Compiled rego; in-memory |
| **Total enforcement overhead** | **~120ms** | p95 target end-to-end enforcement |

Business logic latency is additive on top of this. The SLO for total p95 request latency is 200ms (enforcement + handler).

---

## 7. Architectural Decisions

### ADR-1: Synchronous enforcement on request path

**Decision:** Risk evaluation and policy decision are synchronous; no request reaches a handler without a fresh decision.

**Alternatives considered:**
- *Async pre-authorization (shadow mode)*: compute risk asynchronously, use cached decisions. Faster (near-zero overhead) but creates a window where stolen tokens pass on cached allow decisions.
- *Sidecar proxy (Envoy + OPA)*: moves enforcement out of application code. More operationally complex; requires service mesh; harder to demonstrate portability across Django and Spring.

**Rationale:** The security guarantee (every request has a fresh behavioral assessment) outweighs the latency cost, which is bounded and measurable. 120ms enforcement overhead is acceptable for payment-related APIs.

### ADR-2: App services call Gateway, not OPA directly

**Decision:** Django and Spring call the policy gateway's `/v1/policy/decision`, not OPA's `/v1/data/aztdp/authz` directly.

**Rationale:** The gateway adds two capabilities OPA cannot provide alone: (1) revocation checking against a shared store, and (2) decision logging/telemetry. Routing through the gateway keeps OPA stateless and swappable. If OPA is replaced with Cedar or Casbin, only the gateway changes.

### ADR-3: Fail-open is configurable, not hardcoded

**Decision:** Each service has its own `AZTDP_FAIL_OPEN` env var. The enforcement services (gateway, risk engine) and the app middlewares each honor it independently.

**Rationale:** Fail-closed is the secure default for production. Fail-open allows development without running the full stack. Splitting by service allows staged rollouts where, e.g., the anomaly service fails open but the risk engine fails closed.

**Operational risk:** A misconfigured `FAIL_OPEN=true` in production means the system silently bypasses enforcement on dependency failure. Deployment runbook must verify this setting before every production deploy.

### ADR-4: Token hash (SHA-256 of JTI) used as revocation handle, not raw JTI

**Decision:** The JTI is hashed before transmission in all inter-service calls and before storage in Redis/PostgreSQL.

**Rationale:** The JTI is a sensitive bearer credential — if the revocation store is compromised, raw JTIs cannot be reused. SHA-256 is collision-resistant and sufficient for a lookup key. The original JTI never leaves the app service process.

### ADR-5: Replay detection uses 60-second window, not full token lifetime

**Decision:** Replay is flagged only if the same token is seen from two different IPs within 60 seconds.

**Rationale:** A 5-minute window would create too many false positives for mobile users on changing LTE/WiFi connections. 60 seconds is tight enough to catch automated replay tools while being loose enough for normal mobile network transitions. Gap: an attacker who waits 61 seconds can replay undetected; mitigated by drift scoring (IP+geo still adds 0.35+0.20 to risk even outside the replay window).

### ADR-6: Anomaly service fails open

**Decision:** If the anomaly service is unavailable or exceeds the 150ms timeout, the risk engine sets `anomaly_score=0.0` and continues. The request is not blocked.

**Rationale:** The anomaly service is a detection enhancement, not a gate. The rule-based risk engine (IP drift, geo drift, sensitivity) provides the primary defense. Failing closed on anomaly service unavailability would mean every request is blocked when the ML service is restarting or retraining, which is operationally unacceptable.

---

## 8. Known Implementation Gaps

These are documented gaps in the current codebase, each with its fix phase:

| Gap | Location | Description | Fix |
|---|---|---|---|
| No `/health` endpoint | `services/gateway/app.py`, `services/risk-engine/app.py` | docker-compose health checks will fail | Phase 6B |
| Revocation store ephemeral | `services/gateway/revocation_store.py` | Pure in-memory; lost on restart | Phase 6B |
| `anomaly_score` not in response | `services/risk-engine/app.py` | Response dict omits `anomaly_score`; Java model and Django middleware reference it but receive `None`/`0.0` | Phase 7 |
| `prometheus_client` not in requirements | `services/django-app/requirements.txt` | Settings allowlists `/metrics` but library is not installed | Phase 11 |
| No Dockerfiles | All services | No container build artifacts | Phase 6A |
| `docker-compose.yml` placeholder | Root | Busybox placeholder; no real services | Phase 6B |
| No tests anywhere | All services | No pytest, no JUnit | Phase 9 |
| No `anomaly_score` in `audit_events` return | `services/risk-engine/app.py` | OPA receives `anomaly_score: None` from app services that use `.get("anomaly_score", 0.0)` | Phase 7 |
