# Contributing to AZTDP

## Dev environment

Requirements:

- Docker + Docker Compose
- Python 3.12
- Java 25 (Temurin recommended)
- Maven 3.9+

## Local setup

```bash
# 1. Bring up infrastructure only (postgres, redis, keycloak, opa)
docker compose up -d postgres redis keycloak opa

# 2. Install Python deps
python -m venv .venv && source .venv/bin/activate
pip install pytest==8.2.2 pytest-django httpx ruff
for req in services/*/requirements.txt; do pip install -r "$req"; done

# 3. Run individual service in dev mode (auto-reload)
cd services/risk-engine
AZTDP_REDIS_URL=redis://localhost:6379/0 \
AZTDP_ANOMALY_URL=http://localhost:8002 \
uvicorn risk_engine.app:app --reload --port 8001
```

## Repository layout

```
services/                      # One subdirectory per microservice
  gateway/                     # FastAPI policy gateway (calls OPA)
  risk-engine/                 # FastAPI rule-based risk scoring
  anomaly-service/             # FastAPI + Isolation Forest ML
  telemetry-ingest/            # FastAPI + PostgreSQL writer
  forensics/                   # FastAPI read-only event search
  django-app/                  # Sample protected service (Python)
  spring-app/                  # Sample protected service (Java)
  attack-sim/                  # Adversary simulation scripts
infra/
  postgres/                    # init.sql
  keycloak/                    # Realm export
  redis/                       # redis.conf
  prometheus/                  # prometheus.yml
  grafana/                     # Dashboards + provisioning
  k8s/                         # K8s manifests
  helm/                        # Helm chart
policies/opa/rules/            # Rego policies
scripts/
  db/                          # Schema migrations
  load/                        # Load tests
docs/                          # All documentation
```

## Adding a new endpoint

1. Add the route to the relevant app service (Django or Spring).
2. Add an entry to the endpoint sensitivity map (Django: `aztdp_django/settings.py` `AZTDP_ENDPOINT_SENSITIVITY`; Spring: `RiskEnforcementFilter.endpointSensitivity()`).
3. If the endpoint should require admin role, add a Rego rule in `policies/opa/rules/authz.rego`.
4. Add tests in `services/<service>/tests/`.

## Code style

- Python: `ruff check services/ --select=E,F,W,I --ignore=E501`
- Java: standard Spring Boot conventions
- No comments unless they explain non-obvious *why*

## Testing requirements

| Change type           | Required                                               |
|-----------------------|--------------------------------------------------------|
| Bug fix               | Regression test reproducing the original bug           |
| New endpoint          | Unit test + entry in `services/attack-sim/test_attack_outcomes.py` if security-relevant |
| Risk model change     | Update `services/risk-engine/tests/test_risk_model.py` |
| OPA policy change     | OPA test in `policies/opa/rules/`                      |
| Telemetry/forensics   | Test against an integration container running PostgreSQL |

## PR checklist

- [ ] `pytest` passes
- [ ] `mvn test` passes (if Spring code touched)
- [ ] `ruff check services/` clean
- [ ] No new dev secrets committed
- [ ] Updated relevant docs (`docs/`, `README.md`, `docs/milestones/MILESTONES.md`)
- [ ] If you added a new env var: add it to `docs/architecture/component-ports.md` and `docker-compose.yml`
