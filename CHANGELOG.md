# Changelog

All notable changes to AZTDP. Entries for the production-readiness effort follow the plan in [docs/superpowers/plans/2026-10-19-aztdp-production-readiness.md](docs/superpowers/plans/2026-10-19-aztdp-production-readiness.md); finding IDs (F-xx) refer to its Findings Register.

## [Unreleased] - production readiness (branch `feat/production-readiness`)

### Security
- Internal token now required on the forensics service; dashboard proxy fixed and reduced to what it needs (F-04, F-05).
- Only the nginx ingress is published; Redis requires a password, AOF is on, and eviction is off; OPA is no longer reachable from the host (F-09, F-07).
- Step-up rewritten: Redis-backed challenges, attempt limit and per-user lockout, per-user secrets, tokens bound to the access token; nginx overwrites client IP headers (F-06).
- Production profile: fail-closed settings, split dev and production Keycloak realms, attack simulator moved behind a dev-only profile (F-10, F-11).
- Revocations are written synchronously with a token-expiry TTL, kept alive past expiry by a clock-skew grace, and resynced periodically (F-07).
- Anomaly model artifacts are HMAC-verified before `joblib.load`; a corrupt signature or path now fails closed without raising (F-13).
- `audit_events` is append-only, with `TRUNCATE` guarded on every partition (F-08).

- Allowlisted paths are matched exactly (Django and Spring); `/metrics` is also blocked at the ingress. In DEBUG, `/ui` and its subtree are allowed on a segment boundary.
- A TOTP code can be used once per user; a replay is rejected and counts toward the per-user lockout.
- Django step-up keys and forensics' internal token are validated at startup; a step-up store outage returns 503.
- Gateway telemetry no longer retries 4xx responses; `expires_at` on token revoke is range-checked.
- Dependency advisories cleared: FastAPI/Starlette bumped per service, Django, PyJWT, requests, a jackson-bom pin for Spring, and frontend npm packages.

### Reliability and operations
- CI: lint and bandit, per-service tests with coverage gates, OPA, Java, frontend, secret and dependency scanning, compose and exposure checks, and a compose integration run with ingress smoke tests. The release workflow is gated on green CI.
- One migration path with per-service least-privilege database roles (F-14).
- Containers run as non-root with health checks and digest-pinned base images; Prometheus scrapes the right Django port (F-12).
- Audit telemetry retries, counts drops (`aztdp_telemetry_dropped_total`), and alerts on them; telemetry-ingest and forensics gained tests (F-08, F-18).
- Alertmanager with `ServiceDown` and denial-spike alerts (F-15).
- PostgreSQL backups with automated restore verification and a validated restore runbook (F-15).
- Memory limits and restart policies on every service, checked by `scripts/check_compose_limits.sh`.
- Multiprocess-safe Prometheus metrics for the multi-worker services.
- Measured load-test baseline ([docs/PERFORMANCE_BASELINE.md](docs/PERFORMANCE_BASELINE.md)); both provisional SLOs are currently missed.
- The anomaly-service fallback is no longer silent: `aztdp_anomaly_calls_total{outcome}`, warning logs, and the `AnomalyScoringDegraded` alert. Fail-open behavior itself is unchanged.

### Fixed
- Prometheus no longer loads the promtool test file as a rules file (it crash-looped).
- The nginx health check passes (it resolved `localhost` to IPv6 while nginx listens on IPv4).
- Test suite is green and runs per service via `scripts/run_tests.sh`; `.env.example` restored; stray build output and a broken worktree link removed (F-01, F-02, F-03).

### Documentation
- Truthful readiness tracker, [known limitations](docs/KNOWN_LIMITATIONS.md) and [go-live checklist](docs/GO_LIVE_CHECKLIST.md); the overlapping root guides were merged into [docs/runbooks/QUICK_START_GUIDE.md](docs/runbooks/QUICK_START_GUIDE.md) (F-20).

### Not yet done
The release workflow has not run on a tag. Kubernetes/Helm quarantine (Task 17) and the single SOC dashboard (Task 18).
