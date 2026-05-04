# AZTDP — Project Milestones

Tracks implementation progress phase by phase. Each phase maps to a discrete deliverable set.
Status: ✅ Complete | 🔄 In Progress | ⬜ Pending — **All 13 phases complete.**

---

## Phase 1 — Threat Model ✅

**Output:** `docs/threat-model/`

- [x] `THREAT_MODEL.md` — STRIDE analysis, 8 security gaps (G-1–G-8), 6 attack scenarios
- [x] `data-flow-diagram.md` — Mermaid DFD with trust boundary map

---

## Phase 2 — Architecture Documentation ✅

**Output:** `docs/architecture/`

- [x] `ARCHITECTURE.md` — Component inventory, latency budget, 7 ADRs, known gaps table
- [x] `sequence-diagrams.md` — 8 sequence diagrams (normal flow, replay, step-up, privilege escalation, revocation, fail-open, forensics)
- [x] `component-ports.md` — Port map, 30+ env vars, inter-service call graph

---

## Phase 3 — Data Model ✅

**Output:** `docs/data-model/`, `scripts/db/`, `infra/postgres/`

- [x] `docs/data-model/REDIS_PATTERNS.md` — 5 key patterns, TTLs, memory sizing
- [x] `scripts/db/schema.sql` — 6 tables, 22 indexes, idempotent `BEGIN/COMMIT`
- [x] `infra/postgres/init.sql` — Docker init entrypoint script

---

## Phase 4 — API Contracts ✅

**Output:** `docs/api/`

- [x] `gateway.openapi.yaml` — 4 endpoints, full request/response schemas
- [x] `risk-engine.openapi.yaml` — `/v1/risk/evaluate`, 409 replay schema
- [x] `anomaly-service.openapi.yaml` — 11 features documented
- [x] `telemetry-ingest.openapi.yaml` — event_type payload variants
- [x] `forensics.openapi.yaml` — 3 endpoints, index annotations

---

## Phase 5 — Milestones ✅

**Output:** `docs/milestones/MILESTONES.md`

- [x] This file

---

## Phase 6A — Dockerfiles ✅

**Output:** One `Dockerfile` per service directory

- [x] `services/gateway/Dockerfile`
- [x] `services/risk-engine/Dockerfile`
- [x] `services/anomaly-service/Dockerfile`
- [x] `services/telemetry-ingest/Dockerfile`
- [x] `services/forensics/Dockerfile`
- [x] `services/django-app/Dockerfile`
- [x] `services/spring-app/Dockerfile`

---

## Phase 6B — Docker Compose + Infra Configs + Code Fixes ✅

**Output:** `docker-compose.yml`, `infra/keycloak/`, `infra/redis/`, code fixes

- [x] `docker-compose.yml` — 13-service stack (replaces busybox placeholder)
- [x] `infra/keycloak/aztdp-realm.json` — realm export with test users, clients, roles, mappers
- [x] `infra/redis/redis.conf` — `maxmemory 256mb`, `allkeys-lru`
- [x] **Fix:** `services/gateway/revocation_store.py` — add Redis backing
- [x] **Fix:** `services/gateway/app.py` — add `GET /health`
- [x] **Fix:** `services/risk-engine/app.py` — add `GET /health`
- [x] **Fix:** `services/risk-engine/config.py` — add `ANOMALY_URL` env var

---

## Phase 7 — Anomaly Service ✅

**Output:** `services/anomaly-service/`

- [x] `requirements.txt` — fastapi, uvicorn, scikit-learn, joblib, redis, psycopg
- [x] `config.py` — env-var driven configuration
- [x] `feature_engineering.py` — 11-feature extractor, sliding window rate from Redis
- [x] `model.py` — IsolationForest, joblib persistence, background hot-reload thread
- [x] `training.py` — cold-start synthetic baseline (10k samples), retrain from `anomaly_baselines`
- [x] `app.py` — `POST /v1/anomaly/score`, `GET /health`, `GET /metrics`
- [x] **Update:** `services/risk-engine/app.py` — call anomaly service, include `anomaly_score` in response

---

## Phase 8 — Attack Simulation Enhancements ✅

**Output:** `services/attack-sim/` additions

- [x] `geo_drift_attack.py` — escalating geo (US→GB→DE→CN) with same token
- [x] `anomaly_flood.py` — 100 requests/10s to spike `request_rate_1m`
- [x] `run_all.py` — orchestrator for all attack scripts
- [x] `test_attack_outcomes.py` — pytest assertions on HTTP status codes

---

## Phase 9 — Tests ✅

**Output:** Test files per service + `pytest.ini`

- [x] `pytest.ini` — root-level config, testpaths, markers
- [x] `services/gateway/tests/` — revocation_store, opa_client, policy endpoint
- [x] `services/risk-engine/tests/` — risk_model (7 cases), replay detection, endpoint
- [x] `services/anomaly-service/tests/` — feature engineering, model scoring
- [x] `services/telemetry-ingest/tests/` — event ingestion, DB writes
- [x] `services/forensics/tests/` — query filters, replay timeline
- [x] `services/django-app/tests/` — middleware enforcement, JWT verifier
- [x] `services/spring-app/src/test/` — `RiskEnforcementFilterTest`, `RiskClientTest` (JUnit 5)
- [x] Critical: `test_replay_returns_403_even_with_fail_open()`

---

## Phase 10 — CI/CD ✅

**Output:** `.github/workflows/ci.yml`, `infra/k8s/`, `infra/helm/`

- [x] `.github/workflows/ci.yml` — 5 jobs: lint-python, test-python, test-java, build-images, integration-test
- [x] `infra/k8s/` — Deployment + Service + ConfigMap per service (2 replicas, resource limits, probes)
- [x] `infra/helm/Chart.yaml` + `values.yaml`

---

## Phase 11A — Telemetry + Forensics Services ✅

**Output:** `services/telemetry-ingest/`, `services/forensics/`

**Telemetry Ingest:**
- [x] `requirements.txt`, `config.py`, `db.py` — psycopg_pool (min 2 / max 10)
- [x] `app.py` — `POST /v1/telemetry/event`, DB writes to 4 tables based on event_type
- [x] `GET /health`, `GET /metrics`

**Forensics:**
- [x] `requirements.txt`, `config.py`, `db.py`
- [x] `app.py` — `GET /v1/forensics/events`, `GET /v1/forensics/replay/{session_id}`, `GET /v1/forensics/incidents/{request_id}`
- [x] `GET /health`, `GET /metrics`

---

## Phase 11B — Prometheus + Grafana + Metrics Endpoints ✅

**Output:** `infra/prometheus/`, `infra/grafana/`, per-service `metrics.py`

- [x] `metrics.py` for each Python service (gateway, risk-engine, anomaly, telemetry, forensics)
- [x] Django `/metrics` endpoint with `prometheus_client`
- [x] Spring Boot: add `spring-boot-starter-actuator` + `micrometer-registry-prometheus` to `pom.xml`
- [x] `infra/prometheus/prometheus.yml` — scrape configs for all 8 services
- [x] `infra/grafana/dashboards/` — 4 dashboards: policy-decisions, risk-scores, service-latency, attack-detection
- [x] **Update:** `services/gateway/decision_log.py` — fire-and-forget POST to telemetry-ingest
- [x] **Update:** `services/risk-engine/app.py` — fire-and-forget POST to telemetry-ingest

---

## Phase 12 — Load Testing ✅

**Output:** `scripts/load/locustfile.py`

- [x] `NormalUser` task (weight=80) — consistent IP/UA headers, varied endpoints
- [x] `AttackUser` task (weight=20) — rotating attack scenarios
- [x] SLO assertions: p95 < 200ms, replay detection > 99%, FPR < 0.1%, throughput > 200 RPS @ 100 concurrent

---

## Phase 13 — Final Documentation ✅

**Output:** `README.md`, `docs/SECURITY.md`, `docs/CONTRIBUTING.md`, `docs/runbooks/INCIDENT_RESPONSE.md`

- [x] `README.md` — Mermaid arch diagram, quick start, env vars table, all runbooks
- [x] `docs/SECURITY.md` — vulnerability disclosure, known gaps, patch process
- [x] `docs/CONTRIBUTING.md` — dev setup, test requirements, PR checklist
- [x] `docs/runbooks/INCIDENT_RESPONSE.md` — forensics queries per attack type (replay, geo-drift, brute force)
