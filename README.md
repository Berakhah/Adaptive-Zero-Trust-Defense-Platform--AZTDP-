# AZTDP — Adaptive Zero-Trust Defense Platform

Production-grade zero-trust security platform that enforces **per-request behavioral risk scoring** on top of valid JWTs. Every protected request is evaluated for IP drift, geo drift, device change, request rate anomalies, and ML-based anomaly detection **before** any business logic runs.

Built entirely with open-source tools.

---

## Architecture

```mermaid
flowchart LR
    Client -->|Bearer JWT| App[Django / Spring]
    App -->|1. Verify JWT JWKS| KC[Keycloak]
    App -->|2. Risk Eval| RE[Risk Engine]
    RE -->|2a. Anomaly Score| AS[Anomaly Service]
    RE -->|read/write| Redis[(Redis)]
    App -->|3. Policy Decision| GW[Gateway]
    GW -->|OPA query| OPA[OPA]
    GW -->|revocation check| Redis
    GW -->|telemetry| TI[Telemetry Ingest]
    RE -->|telemetry| TI
    TI -->|persist| PG[(PostgreSQL)]
    Forensics --> PG
    AS --> PG
    Prometheus --> GW
    Prometheus --> RE
    Prometheus --> AS
    Grafana --> Prometheus
```

The full enforcement chain runs **synchronously on the request path**:

1. **JWT verify** (RS256, JWKS cached 5 min)
2. **Risk evaluation** — drift scoring + ML anomaly score
3. **Policy decision** — gateway calls OPA, applies revocation
4. **Enforce** — `allow` | `deny (403)` | `stepup (401 + MFA)` | `revoke (revoke + 403)`

**Replay protection:** if the same token's IP changes within 60 s, the request is hard-denied (HTTP 409 → 403) regardless of fail-open mode.

See [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) for the full ADR set, latency budget, and known gaps.

---

## Quick start

```bash
# 1. Bring up the full 13-service stack
docker compose up -d --build

# 2. Wait for Keycloak to import the realm (~60s)
curl -sf http://localhost:8080/health/ready

# 3. Get a token
TOKEN=$(curl -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token \
  -d grant_type=password -d client_id=aztdp-client -d client_secret=aztdp-secret \
  -d username=user1 -d password=password | jq -r .access_token)

# 4. Make an authenticated request to the Django app
curl -H "Authorization: Bearer $TOKEN" \
     -H "X-Client-Ip: 203.0.113.10" \
     -H "X-Geo: US-CA" \
     http://localhost:8010/v1/payments/123

# 5. Watch the policy decision in Grafana
open http://localhost:3000  # admin / admin -> AZTDP folder
```

---

## Service URLs (host ports)

| Service           | URL                            | Purpose                                 |
|-------------------|--------------------------------|-----------------------------------------|
| Django App        | http://localhost:8010          | Sample protected service                |
| Spring App        | http://localhost:8011          | Sample protected service (Java)         |
| Gateway           | http://localhost:8000          | Policy decision API                     |
| Risk Engine       | http://localhost:8001          | Risk scoring API                        |
| Anomaly Service   | http://localhost:8002          | ML anomaly scoring API                  |
| Telemetry Ingest  | http://localhost:8003          | Event persistence                       |
| Forensics         | http://localhost:8004          | Incident replay & event search          |
| Keycloak          | http://localhost:8080          | OIDC provider (admin / admin)           |
| OPA               | http://localhost:8181          | Policy engine                           |
| Prometheus        | http://localhost:9090          | Metrics                                 |
| Grafana           | http://localhost:3000          | Dashboards (admin / admin)              |

---

## Configuration

Every service is environment-driven. Key shared variables:

| Variable                   | Default                                       | Purpose                                      |
|----------------------------|-----------------------------------------------|----------------------------------------------|
| `AZTDP_FAIL_OPEN`          | `false`                                       | Per-service. `true` = allow on backend error |
| `AZTDP_REDIS_URL`          | `redis://redis:6379/0`                        | Risk-engine + gateway shared store           |
| `AZTDP_DB_URL`             | `postgresql://aztdp:aztdp@postgres:5432/aztdp`| Telemetry, forensics, anomaly                |
| `AZTDP_OPA_URL`            | `http://opa:8181`                             | Gateway -> OPA                               |
| `AZTDP_RISK_ENGINE_URL`    | `http://risk-engine:8080`                     | App -> risk engine                           |
| `AZTDP_POLICY_GATEWAY_URL` | `http://gateway:8080`                         | App -> gateway                               |
| `AZTDP_ANOMALY_URL`        | `http://anomaly-service:8080`                 | Risk-engine -> anomaly service               |
| `AZTDP_TELEMETRY_URL`      | `http://telemetry-ingest:8080`                | Risk-engine + gateway -> telemetry           |
| `AZTDP_OIDC_ISSUER`        | `http://keycloak:8080/realms/aztdp`           | App OIDC issuer                              |
| `AZTDP_AUDIENCE`           | `aztdp-api`                                   | JWT audience claim                           |
| `AZTDP_REPLAY_WINDOW_SECONDS` | `60`                                       | Replay detection window                      |
| `AZTDP_ANOMALY_THRESHOLD`  | `0.7`                                         | `is_anomalous` cutoff                        |

Full list in [docs/architecture/component-ports.md](docs/architecture/component-ports.md).

---

## Testing

```bash
# Unit tests (Python)
pip install pytest==8.2.2 pytest-django httpx
for req in services/*/requirements.txt; do pip install -r "$req"; done
pytest

# Java tests
cd services/spring-app && mvn test

# Live attack-sim tests (against running stack)
AZTDP_RUN_LIVE_TESTS=1 \
AZTDP_BASE_URL=http://localhost:8010 \
AZTDP_USERNAME=user1 AZTDP_PASSWORD=password \
pytest services/attack-sim/test_attack_outcomes.py

# Load test
locust -f scripts/load/locustfile.py --host http://localhost:8010 \
       --users 100 --spawn-rate 10 --run-time 5m --headless
```

---

## Deploying to Kubernetes

```bash
kubectl apply -f infra/k8s/namespace.yaml
kubectl apply -f infra/k8s/

# Or via Helm
helm install aztdp infra/helm/ -n aztdp --create-namespace
```

---

## Documentation map

- [docs/threat-model/](docs/threat-model/) — STRIDE analysis, 8 gaps, attack scenarios
- [docs/architecture/](docs/architecture/) — Component inventory, sequence diagrams, 7 ADRs
- [docs/data-model/REDIS_PATTERNS.md](docs/data-model/REDIS_PATTERNS.md) — All 5 Redis key patterns
- [docs/api/](docs/api/) — Per-service contracts (5 services)
- [docs/milestones/MILESTONES.md](docs/milestones/MILESTONES.md) — Phase tracker
- [docs/runbooks/INCIDENT_RESPONSE.md](docs/runbooks/INCIDENT_RESPONSE.md) — Forensics queries by attack type
- [docs/SECURITY.md](docs/SECURITY.md) — Vulnerability reporting, known gaps
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) — Dev setup, PR checklist
- [scripts/db/schema.sql](scripts/db/schema.sql) — PostgreSQL schema (6 tables, 22 indexes)

---

## Known limitations

- `X-Client-Ip` and `X-Geo` headers are user-controllable. **In production, only trust them from a verified upstream reverse proxy** (Envoy, nginx with `real_ip_header` pinned to the LB).
- Replay window is 60 s, not the full token lifetime — an attacker who waits 61 s avoids the replay flag but still triggers IP-drift scoring.
- Anomaly service fails open: if it's restarting or retraining, requests are not blocked.
- Single-region only. No multi-region replication for Redis or PostgreSQL.

See [docs/SECURITY.md](docs/SECURITY.md) and [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) § "Known gaps" for details.

---

## License

This project is provided as a reference architecture. Adapt freely for your own use.
