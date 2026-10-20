# Go-Live Checklist

Work top to bottom on the release candidate. Every box needs a name and a date next to it before launch. The base `docker-compose.yml` is the production profile; never add `docker-compose.dev.yml` or `.env.dev` to a production deployment.

## 1. Secrets

- [ ] Copy `.env.example` to `.env` and fill **every** value. The base compose file refuses to start while any required secret is empty.
- [ ] Generate each secret independently, for example `openssl rand -hex 32`. Do not reuse one value for several keys, and do not copy anything from `.env.dev` (its values are public).
- [ ] Keep the URL-encoded Redis password in step with the plain one (`REDIS_PASSWORD_URLENCODED`).
- [ ] Store `.env` outside the repository with owner-only permissions. Confirm `git status` shows no `.env` and no `secrets/` directory.
- [ ] Record a rotation owner and interval for the internal token, database role passwords, Redis password, Grafana admin, Keycloak admin and the model-signing key. Rotating requires restarting the services that read them.

## 2. TLS and hostnames

- [ ] Replace the self-signed certificate from `infra/nginx/gen-certs.sh` with one from a real CA, placed in `infra/nginx/certs/`.
- [ ] DNS records point at the host; `ALLOWED_HOSTS` and the OIDC issuer URL use those hostnames.
- [ ] HTTP redirects to HTTPS and the HSTS header is present: `curl -sI https://<host>/ | grep -i strict-transport`.

## 3. Identity

- [ ] Review `infra/keycloak/aztdp-realm.json` (the production realm): no seeded users, no static passwords, no wildcard `webOrigins`, `sslRequired` set, direct access grants off. Never import `aztdp-realm.dev.json`.
- [ ] Create real users and roles in Keycloak, and set the client secret to a generated value.
- [ ] Decide the long-term step-up approach ([KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)).

## 4. Exposure

- [ ] `bash scripts/check_exposure.sh` passes: only the nginx ingress ports are published.
- [ ] The attack simulator is not running (it exists only behind the dev `sim` profile).
- [ ] From outside the host, ports 5432, 6379, 8181, 8080, 9090 and the service ports 8000-8011 are closed.

## 5. Data protection

- [ ] The backup job has run at least once and the restore drill from [BACKUP_RESTORE.md](runbooks/BACKUP_RESTORE.md) was executed against the release candidate's backup. Record the measured restore time and who signed it off.
- [ ] Backups are copied off the host.
- [ ] Audit retention is understood and scheduled ([AUDIT_RETENTION.md](runbooks/AUDIT_RETENTION.md)).

## 6. Monitoring

- [ ] `bash scripts/check_prometheus.sh` passes (config, rules, rule unit tests, Alertmanager config).
- [ ] `ALERT_WEBHOOK_URL` points at the real receiver, and a test alert was delivered to a human.
- [ ] All Prometheus targets are up and the alerts `ServiceDown`, `AuditTelemetryDropping` and `AnomalyScoringDegraded` are loaded.

## 7. Capacity and limits

- [ ] `bash scripts/check_compose_limits.sh` passes (memory limits and restart policies).
- [ ] A target request rate and SLOs are agreed, and a load test on the reference host meets them. The numbers in [PERFORMANCE_BASELINE.md](PERFORMANCE_BASELINE.md) do not.
- [ ] The anomaly-scoring fail-open policy is decided ([KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)).

## 8. Quality gates

- [ ] `bash scripts/run_tests.sh` is green, and the OPA tests pass.
- [ ] `bash scripts/lint_dockerfiles.sh` passes.
- [ ] CI is green on the release tag. (The CI rewrite, plan Task 16, is not done yet; until it lands, run the scripts above by hand.)

## 9. Sign-off

| Role | Name | Date |
|---|---|---|
| Release owner | | |
| Security reviewer | | |
| Operations | | |
