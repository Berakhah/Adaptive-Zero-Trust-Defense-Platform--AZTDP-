# AZTDP Component Port Map

## Service Ports

| Service | Container Internal Port | Host Port (dev) | Protocol | Health Endpoint |
|---|---|---|---|---|
| Keycloak | 8080 | 8080 | HTTP | `/health/ready` |
| PostgreSQL | 5432 | 5432 | TCP | pg_isready |
| Redis | 6379 | 6379 | TCP | `redis-cli ping` |
| OPA | 8181 | 8181 | HTTP | `GET /health` |
| Gateway | 8080 | 8000 | HTTP | `GET /health` (Phase 6B) |
| Risk Engine | 8080 | 8001 | HTTP | `GET /health` (Phase 6B) |
| Anomaly Service | 8080 | 8002 | HTTP | `GET /health` |
| Telemetry Ingest | 8080 | 8003 | HTTP | `GET /health` |
| Forensics | 8080 | 8004 | HTTP | `GET /health` |
| Django App | 8080 | 8010 | HTTP | `GET /health` |
| Spring Boot App | 8082 | 8011 | HTTP | `GET /health` |
| Prometheus | 9090 | 9090 | HTTP | `GET /-/healthy` |
| Grafana | 3000 | 3000 | HTTP | `GET /api/health` |

## Metrics Endpoints

| Service | Metrics Path | Library |
|---|---|---|
| Gateway | `/metrics` | `prometheus_client` (Phase 11) |
| Risk Engine | `/metrics` | `prometheus_client` (Phase 11) |
| Anomaly Service | `/metrics` | `prometheus_client` |
| Telemetry Ingest | `/metrics` | `prometheus_client` |
| Forensics | `/metrics` | `prometheus_client` |
| Django App | `/metrics` | `prometheus_client` (Phase 11) |
| Spring Boot App | `/actuator/prometheus` | `micrometer-registry-prometheus` (Phase 11) |

## Environment Variables (master reference)

| Variable | Used By | Default | Notes |
|---|---|---|---|
| `AZTDP_REDIS_URL` | risk-engine, anomaly-service, gateway (Phase 6B) | `""` | Empty = in-memory fallback |
| `AZTDP_OPA_URL` | gateway | `http://opa:8181` | |
| `AZTDP_OPA_DECISION_PATH` | gateway | `/v1/data/aztdp/authz/decision` | |
| `AZTDP_POLICY_TIMEOUT` | gateway | `0.8` | Seconds |
| `AZTDP_FAIL_OPEN` | gateway, risk-engine, django-app, spring-app | `false` | `true` in dev only |
| `AZTDP_OIDC_ISSUER` | django-app, spring-app | `http://keycloak:8080/realms/aztdp` | |
| `AZTDP_JWKS_URL` | django-app | `http://keycloak:8080/realms/aztdp/protocol/openid-connect/certs` | |
| `AZTDP_AUDIENCE` | django-app | `aztdp-api` | |
| `AZTDP_RISK_ENGINE_URL` | django-app, spring-app | `http://risk-engine:8080` | |
| `AZTDP_POLICY_GATEWAY_URL` | django-app, spring-app | `http://gateway:8080` | |
| `AZTDP_TOKEN_REVOKE_URL` | django-app, spring-app | `http://gateway:8080/v1/tokens/revoke` | |
| `AZTDP_TIMEOUT_CONNECT` | django-app | `0.2` | Seconds |
| `AZTDP_TIMEOUT_READ` | django-app | `0.8` | Seconds |
| `AZTDP_TIMEOUT_CONNECT_MS` | spring-app | `200` | Milliseconds |
| `AZTDP_TIMEOUT_READ_MS` | spring-app | `800` | Milliseconds |
| `AZTDP_RISK_BASE` | risk-engine | `0.1` | |
| `AZTDP_RISK_SENSITIVITY_WEIGHT` | risk-engine | `0.15` | |
| `AZTDP_RISK_IP_DRIFT_WEIGHT` | risk-engine | `0.35` | |
| `AZTDP_RISK_UA_DRIFT_WEIGHT` | risk-engine | `0.2` | |
| `AZTDP_RISK_GEO_DRIFT_WEIGHT` | risk-engine | `0.2` | |
| `AZTDP_REPLAY_WINDOW_SECONDS` | risk-engine | `60` | |
| `AZTDP_TOKEN_TTL_SECONDS` | risk-engine | `1800` | |
| `AZTDP_ANOMALY_URL` | risk-engine | `""` | Empty = anomaly disabled (Phase 7) |
| `AZTDP_ANOMALY_THRESHOLD` | anomaly-service | `0.7` | |
| `AZTDP_MODEL_PATH` | anomaly-service | `/app/models` | |
| `AZTDP_DB_HOST` | django-app, telemetry-ingest, forensics | `postgres` | |
| `AZTDP_DB_NAME` | django-app | `aztdp` | |
| `AZTDP_DB_USER` | django-app | `aztdp` | |
| `AZTDP_DB_PASSWORD` | django-app | `aztdp` | Change in production |
| `AZTDP_DB_URL` | anomaly-service, telemetry-ingest, forensics | `postgresql://aztdp:aztdp@postgres:5432/aztdp` | |
| `AZTDP_TELEMETRY_URL` | gateway, risk-engine, anomaly-service | `http://telemetry-ingest:8080` | |
| `AZTDP_SECRET_KEY` | django-app | `change-me` | Django SECRET_KEY |
| `AZTDP_DEBUG` | django-app | `false` | |
| `AZTDP_ALLOWED_HOSTS` | django-app | `*` | Comma-separated |

## Inter-Service Call Graph

```
django-app ──────── POST /v1/risk/evaluate ──────────────▶ risk-engine
django-app ──────── POST /v1/policy/decision ────────────▶ gateway
django-app ──────── POST /v1/tokens/revoke ──────────────▶ gateway

spring-app ──────── POST /v1/risk/evaluate ──────────────▶ risk-engine
spring-app ──────── POST /v1/policy/decision ────────────▶ gateway
spring-app ──────── POST /v1/tokens/revoke ──────────────▶ gateway

gateway ─────────── POST /v1/data/aztdp/authz/decision ──▶ opa
gateway ─────────── GET/SET revocation ──────────────────▶ redis (Phase 6B)
gateway ─────────── POST /v1/telemetry/event ────────────▶ telemetry-ingest (Phase 11)

risk-engine ──────── GET/SET token:last_seen:{hash} ─────▶ redis
risk-engine ──────── POST /v1/anomaly/score ─────────────▶ anomaly-service (Phase 7)
risk-engine ──────── POST /v1/telemetry/event ───────────▶ telemetry-ingest (Phase 11)

anomaly-service ─── GET user:request_rate:{id} ──────────▶ redis
anomaly-service ─── GET token:last_seen:{hash} ──────────▶ redis (read-only)
anomaly-service ─── POST /v1/telemetry/event ────────────▶ telemetry-ingest (Phase 11)

telemetry-ingest ── INSERT audit_events / risk_evals / policy_decisions ▶ postgres

forensics ──────── SELECT audit_events / sessions ───────▶ postgres

prometheus ─────── GET /metrics ─────────────────────────▶ all python services (Phase 11)
prometheus ─────── GET /actuator/prometheus ─────────────▶ spring-app (Phase 11)

grafana ─────────── Query ───────────────────────────────▶ prometheus
```
