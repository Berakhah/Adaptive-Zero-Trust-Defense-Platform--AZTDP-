# AZTDP Runbooks & Guides

Operational documentation for running, managing, and troubleshooting the Adaptive Zero-Trust Defense Platform.

## Quick Navigation

### Getting Started
- **[GETTING_STARTED.md](../../GETTING_STARTED.md)** — Start here! Overview, 5-minute quickstart, common tasks
- **[QUICK_START_GUIDE.md](QUICK_START_GUIDE.md)** — Detailed 80+ page operational guide with all commands

### Setup & Startup
- **[Startup Script](../../scripts/startup.sh)** — Automated setup and platform startup
- **[Validation Script](../../scripts/validate_platform.sh)** — Automated health checks

### Verification & Testing
- **[PLATFORM_VERIFICATION_CHECKLIST.md](../../PLATFORM_VERIFICATION_CHECKLIST.md)** — 100-item verification checklist

### Operations & Deployment
- **[OPERATIONS_MANUAL.md](OPERATIONS_MANUAL.md)** — Production deployment, scaling, HA, disaster recovery
- **[INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md)** — Security incident handling playbook

## Service Commands

```bash
# Start platform
bash scripts/startup.sh

# Verify everything works
bash scripts/validate_platform.sh

# View service logs
docker compose logs -f <service-name>

# Access dashboards
open http://localhost:3000   # Grafana
open http://localhost:8080   # Keycloak
open http://localhost:9090   # Prometheus

# Stop platform
docker compose down

# Full reset
docker compose down -v
```

## Common Issues

| Issue | Command |
|-------|---------|
| Service won't start | `docker compose logs <service>` |
| Token request fails | `curl http://localhost:8080/health/ready` |
| High latency | `docker stats` |
| Database problems | `docker compose exec postgres psql -U aztdp -d aztdp -c "SELECT 1;"` |

## Support Hierarchy

1. **[GETTING_STARTED.md](../../GETTING_STARTED.md)** — Start here for overview and quick tasks
2. **[QUICK_START_GUIDE.md](QUICK_START_GUIDE.md)** — Detailed operational guide (80+ pages)
3. **[OPERATIONS_MANUAL.md](OPERATIONS_MANUAL.md)** — Production deployment and scaling
4. **[INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md)** — Security incident handling

## Deployment Models

- **Docker Compose** (5 min setup) — See [QUICK_START_GUIDE.md § 3. Starting the Platform](QUICK_START_GUIDE.md#3-starting-the-platform)
- **Docker Swarm** (15 min setup) — See [OPERATIONS_MANUAL.md § Deployment Models](OPERATIONS_MANUAL.md#deployment-models)
- **Kubernetes** (30 min setup) — See [OPERATIONS_MANUAL.md § Deployment Models](OPERATIONS_MANUAL.md#deployment-models)

## Testing

```bash
# Unit tests
pytest

# Integration tests (full stack)
AZTDP_RUN_LIVE_TESTS=1 pytest services/attack-sim/

# Load testing
locust -f scripts/load/locustfile.py --host http://localhost:8010

# Validation checklist
bash scripts/validate_platform.sh
```

## Architecture References

- **Full Architecture:** [docs/architecture/ARCHITECTURE.md](../architecture/ARCHITECTURE.md)
- **Threat Model:** [docs/threat-model/THREAT_MODEL.md](../threat-model/THREAT_MODEL.md)
- **API Specs:** [docs/api/](../api/)
- **Security Guide:** [docs/SECURITY.md](../SECURITY.md)
