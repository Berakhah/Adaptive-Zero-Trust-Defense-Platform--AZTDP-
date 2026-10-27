# AZTDP Production-Readiness Tracker

Status legend: `[ ]` pending · `[~]` in progress · `[x]` done · `[-]` won't do

The 2026-05-03 audit tracker (P0-P5) marked everything done. An analysis on 2026-10-19 found that several of those claims were false, and the work to fix them is in [the implementation plan](superpowers/plans/2026-10-19-aztdp-production-readiness.md) (Findings Register F-01 to F-20, Tasks 1-18). This file is the current, honest status. Related documents: [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md), [GO_LIVE_CHECKLIST.md](GO_LIVE_CHECKLIST.md), [PERFORMANCE_BASELINE.md](PERFORMANCE_BASELINE.md), [../CHANGELOG.md](../CHANGELOG.md).

**Not ready for production yet.** Open blockers: both provisional SLOs are missed ([PERFORMANCE_BASELINE.md](PERFORMANCE_BASELINE.md)), the go-live checklist has not been executed, CI has not been rewritten (Task 16), and the owner decisions below are unanswered.

## Plan progress

| Task | Scope | Findings | Status |
|---|---|---|---|
| 1 | Green, isolated, per-service test runs | F-01, F-18 | [x] |
| 2 | Repo hygiene, restored `.env.example` | F-02, F-03 | [x] |
| 3 | Authenticate forensics; fix and shrink dashboard proxy | F-04, F-05 | [x] |
| 4 | Network exposure, Redis auth, OPA isolation | F-09 | [x] |
| 5 | Safe step-up (Redis-backed, rate-limited, no default secrets) | F-06 | [x] |
| 6 | Production profile for identity, Django, demo tooling | F-10, F-11 | [x] |
| 7 | Container hardening, Prometheus port mismatch | F-12, F-19 | [x] |
| 8 | One migration path, per-service DB roles, append-only audit | F-08, F-14 | [x] |
| 9 | Durable, correct token revocation | F-07 | [x] |
| 10 | Audit telemetry reliability, tests for the two untested services | F-08, F-18 | [x] |
| 11 | Signed anomaly-model artifacts | F-13 | [x] |
| 12 | Alertmanager and availability alerts | F-15 | [x] |
| 13 | Backups and tested restore | F-15 | [x] |
| 14 | Resource limits, restart policy, load-test baseline | F-12 | [x] SLOs not met |
| 15 | Documentation truth pass | F-20, F-03 | [x] written; quickstart not yet run end-to-end on a clean clone |
| 16 | CI/CD rewrite (tests, security gates, release) | F-16, F-19 | [ ] |
| 17 | Quarantine Kubernetes/Helm | F-20 | [ ] |
| 18 | One SOC dashboard wired to real data | F-17, F-03 | [ ] blocked on Q2 |

## Original audit items

Items the 2026-10-19 analysis showed were falsely "done" were reopened, and are marked with what closed them.

### P0 - Deployment blockers
- [x] P0.1 Schema applied: now the one-shot `db-migrate` service runs `scripts/db/migrations/` (reopened by F-14; closed by Task 8)
- [x] P0.2 Anomaly model persistent volume
- [x] P0.3 Spring Boot 4.0.6 / Java 25 build verified (Maven Central metadata, 2026-05-03)

### P1 - Security-critical
- [x] P1.1 Trusted-proxy IP/geo extraction (Django `client_ip.py`, Spring `ClientIpResolver.java`)
- [x] P1.2 OPA policy ladder, `authz_test.rego`
- [x] P1.3 Internal service authentication via `X-Internal-Token` (**reopened**: tests never sent the token and the suite was red, F-01; the dashboard proxy sent the wrong header, F-04; forensics had no auth, F-05. Closed by Tasks 1 and 3)
- [x] P1.4 Dead `is_token_revoked` path removed
- [x] P1.5 Step-up TOTP (**reopened**: per-process challenge store broken across workers, brute-forceable, shared default secret, F-06. Closed by Task 5)

### P2 - Functional correctness
- [x] P2.1 Gateway revocation cold-start recovery (**reopened**: revocations were not durable, F-07. Closed by Task 9)
- [x] P2.2 Telemetry shutdown-safe executor
- [x] P2.3 `decision_log.py` removed
- [x] P2.4 Silent revocation failures surfaced

### P3 - ML retraining loop
- [x] P3.1 Feature vectors persisted to `anomaly_baselines`
- [x] P3.2 Scheduled retraining (6 h, minimum 1000 rows)
- [x] P3.3 Manual retrain endpoint `POST /v1/anomaly/retrain`
- [x] P3.4 Model evaluation metrics
- [x] P3.5 Model artifacts HMAC-verified before load (F-13, Task 11)

### P4 - Operational hardening (SOC 2)
- [x] P4.1 Secrets in `.env` / `${VAR}` references (**reopened**: `.env.example` had been deleted, F-02. Restored in Task 2; production profile refuses to start with unset secrets, Task 6)
- [x] P4.2 TLS reverse proxy (nginx). Certificate is still self-signed: replace before go-live
- [x] P4.3 Django security settings
- [x] P4.4 Audit log partitioning and retention (**reopened**: `V2__audit_partitioning.sql` was never applied, F-14. Closed by Task 8; the audit table is now append-only)
- [x] P4.5 Prometheus alert rules (extended: availability, audit-drop and anomaly-fallback alerts, Alertmanager; Tasks 10, 12 and the anomaly metric)
- [x] P4.6 Structured JSON logging
- [x] P4.7 Backups with automated restore verification (Task 13)
- [x] P4.8 Resource limits and restart policies (Task 14)

### P5 - Test and CI coverage
- [x] P5.1 Per-service pytest runs through `scripts/run_tests.sh` (the root `pytest` cannot collect: package names collide)
- [x] P5.2 OPA policy tests
- [x] P5.3 IP-spoof regression test
- [x] P5.4 Step-up end-to-end test
- [x] P5.5 Telemetry drain test
- [ ] P5.6 CI runs OPA tests, frontend builds, SAST, dependency and image scanning, and a coverage gate (F-16, Task 16)

## SOC 2 Type II evidence map

| Control | Source of evidence |
|---|---|
| Audit log completeness | `audit_events` with retry/drop metric and `AuditTelemetryDropping` alert (Task 10); retention runbook [AUDIT_RETENTION.md](runbooks/AUDIT_RETENTION.md) |
| Audit log immutability | Append-only `audit_events` and per-service DB roles (Task 8, `infra/postgres/04_roles.sql`, `05_grants.sql`) |
| Access control | `X-Internal-Token` on every internal service incl. forensics (Task 3); OPA decisions; network exposure limited to ingress (`scripts/check_exposure.sh`, Task 4) |
| Change management | Signed model artifacts and manual retrain endpoint (Tasks 11, P3.3); CI (Task 16, pending) |
| Encryption in transit | nginx TLS at ingress (P4.2). Replace the self-signed certificate (see go-live checklist) |
| Monitoring and alerting | Prometheus rules and Alertmanager (Task 12), `scripts/check_prometheus.sh`, structured logs (P4.6) |
| Backup and recovery | Automated backups, tested restore, [BACKUP_RESTORE.md](runbooks/BACKUP_RESTORE.md) (Task 13). Restore drill sign-off is a go-live item |
| Capacity and availability | Resource limits and restart policies (`scripts/check_compose_limits.sh`); baseline measured and **SLOs not met** ([PERFORMANCE_BASELINE.md](PERFORMANCE_BASELINE.md)) |

## Open questions for the owner

- **Q1 Step-up:** keep self-hosted TOTP (needs enrollment UI and per-user secret provisioning) or delegate step-up to Keycloak (`acr_values`)? Work so far assumes "harden what exists".
- **Q2 Dashboard:** which UI is the product, `services/dashboard` or `sentinel-command-main`? Task 18 assumes sentinel becomes primary and `services/dashboard` is removed once parity is verified.
- **Q3 Release target:** is there a target host and container registry for releases? Task 16 assumes GHCR.
- **Q4 Anomaly fail-open:** when the anomaly service is slow or down, should high-sensitivity requests fail closed instead of being scored without the ML signal? The fallback is now measured and alerted on, not changed.
- **Q5 SLOs:** what request rate must the platform sustain? The provisional targets (p99 under 250 ms, errors under 0.1%) are met in no load-test run, and the anomaly service tops out near 29 req/s.

## Decisions log

- 2026-05-03: Target Docker Compose only (no K8s) - owner
- 2026-05-03: Keep Spring Boot 4.0.6 + Java 25 pending build verification - owner (verified OK)
- 2026-05-03: Implement full ML retraining loop in scope - owner
- 2026-05-03: SOC 2 Type II in scope, no PCI/GDPR - owner
- 2026-10-19: Production-readiness plan adopted; the 2026-05-03 "all done" status is superseded by this file
- 2026-10-20: Anomaly fallback made observable (counter, logs, alert) with fail-open behavior unchanged, pending Q4
