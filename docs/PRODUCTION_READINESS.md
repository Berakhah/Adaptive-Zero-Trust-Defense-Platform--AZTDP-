# AZTDP Production-Readiness Tracker

Each task references the workstream/ID from the principal-level audit (2026-05-03). Status legend: `[ ]` pending · `[~]` in progress · `[x]` done · `[-]` won't do

## P0 — Deployment Blockers
- [x] P0.1 Mount schema.sql in docker-compose
- [x] P0.2 Anomaly model persistent volume
- [x] P0.3 Verify Spring Boot 4.0.6 / Java 25 build (confirmed in Maven Central metadata 2026-05-03)

## P1 — Security-Critical
- [x] P1.1 Trusted-proxy IP/geo extraction (Django `client_ip.py` + Spring `ClientIpResolver.java`)
- [x] P1.2 OPA policy ladder fix: low-risk allows all sensitivities, very_high_risk → revoke, + `authz_test.rego` (14 tests)
- [x] P1.3 Internal service authentication (`X-Internal-Token` on all 6 services — gateway, risk-engine, anomaly-service, telemetry-ingest, django-app, spring-app; env var in docker-compose)
- [x] P1.4 Remove dead `is_token_revoked` path (OPA rule removed, middleware field removed)
- [x] P1.5 Step-up TOTP verification endpoint (`core/stepup.py`, `POST /v1/auth/step-up/verify`, X-Step-Up-Token header check in middleware)

## P2 — Functional Correctness
- [x] P2.1 Gateway revocation cold-start recovery (loads from `token_revocations` table via psycopg on startup)
- [x] P2.2 Telemetry shutdown-safe executor (ThreadPoolExecutor + shutdown_executor in gateway and risk-engine)
- [x] P2.3 Delete decision_log.py (source already removed; stale .pyc cleaned)
- [x] P2.4 Surface silent revocation failures (middleware now logs error instead of silently returning)

## P3 — ML Retraining Loop
- [x] P3.1 Persist feature vectors to `anomaly_baselines` (UPSERT on each score via `persist_baseline()`)
- [x] P3.2 Scheduled retraining background job (`start_retrain_scheduler()` — 6-hour interval, min 1000 rows)
- [x] P3.3 Manual retrain endpoint (`POST /v1/anomaly/retrain` with internal auth)
- [x] P3.4 Model evaluation metrics (anomaly rate, p50/p95/p99, precision/recall on 20% holdout; Prometheus gauges `aztdp_model_score_p99`, `aztdp_model_holdout_precision`, etc.)

## P4 — Operational Hardening (SOC 2)
- [x] P4.1 Docker secrets migration (all plaintext credentials moved to `.env` / `${VAR}` references; `.env.example` template committed; `.env` and `secrets/` in `.gitignore`)
- [x] P4.2 TLS reverse proxy (nginx service in docker-compose; `infra/nginx/nginx.conf`; self-signed cert script `infra/nginx/gen-certs.sh`; HTTP → HTTPS redirect; HSTS headers)
- [x] P4.3 Django security settings (`ALLOWED_HOSTS` from explicit env — no wildcard fallback; `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS=31536000`)
- [x] P4.4 Audit log partitioning + retention (`scripts/db/migrations/V2__audit_partitioning.sql` — monthly range partitions; `aztdp_audit_maintenance()` procedure; `docs/runbooks/AUDIT_RETENTION.md` — 90-day hot / 7-year cold)
- [x] P4.5 Prometheus alert rules (`infra/prometheus/rules/aztdp.rules.yml` — anomaly_flagged >5/min, policy_denied >10/min, eval_latency p99 >500ms, model stale >24h; wired into `prometheus.yml`)
- [x] P4.6 Structured JSON logging (`json_logging.py` in all 5 FastAPI services; `python-json-logger==2.0.7` added to all requirements; standardized fields: timestamp, service, level, message)

## P5 — Test & CI Coverage
- [x] P5.1 pyproject.toml at repo root (unified pytest config, asyncio_mode=auto, testpaths across all services)
- [x] P5.2 OPA policy tests (`authz_test.rego` — 14 tests)
- [x] P5.3 IP-spoof regression test (`tests/test_ip_spoof_regression.py` — 8 tests covering untrusted-source rejection and trusted-proxy acceptance)
- [x] P5.4 Step-up E2E test (`tests/test_stepup_flow.py` — 12 tests covering full challenge → TOTP → token → verify flow including expiry and replay prevention)
- [x] P5.5 Telemetry drain unit test (`services/gateway/tests/test_telemetry_drain.py` — 5 tests verifying in-flight events drain before shutdown and no loss under concurrency)

## SOC 2 Type II Evidence Map
| Control | Source of evidence |
|---|---|
| Audit log completeness | `audit_events` + retention runbook (P4.4) |
| Access control | `X-Internal-Token` (P1.3) + OPA decision log |
| Change management | Manual retrain endpoint (P3.3) + CI (P5) |
| Encryption in transit | nginx TLS at ingress (P4.2) |
| Monitoring | Alert rules (P4.5) + structured logs (P4.6) |

## Open Questions
- (none currently)

## Decisions Log
- 2026-05-03: Target Docker Compose only (no K8s) — owner
- 2026-05-03: Keep Spring Boot 4.0.6 + Java 25 pending build verification — owner (verified OK)
- 2026-05-03: Implement full ML retraining loop in scope — owner
- 2026-05-03: SOC 2 Type II in scope, no PCI/GDPR — owner
