# AZTDP — Getting Started Guide

Complete guide to understanding, running, using, and validating the **Adaptive Zero-Trust Defense Platform**.

**Status:** ✅ All 13 phases complete  
**Last Updated:** May 4, 2024  
**Platform Version:** 1.0.0

---

## Quick Links

📖 **New to AZTDP?** Start with [Quick Start Guide](docs/runbooks/QUICK_START_GUIDE.md)

🪟 **Using Windows?** Read [Windows Setup Guide](WINDOWS_SETUP_GUIDE.md) **← START HERE IF ON WINDOWS**

🚀 **Ready to deploy?** Read [Operations Manual](docs/runbooks/OPERATIONS_MANUAL.md)

✅ **Verify everything works?** Run [Platform Verification Checklist](PLATFORM_VERIFICATION_CHECKLIST.md)

🏗️ **Want to understand the architecture?** See [Architecture Documentation](docs/architecture/ARCHITECTURE.md)

🔒 **Security concerns?** Check [Security Guide](docs/SECURITY.md)

---

## What is AZTDP?

AZTDP is a **production-grade zero-trust security platform** that enforces continuous, behavioral risk assessment on every API request. Built entirely with open-source tools:

- **Keycloak** — Identity & authentication
- **FastAPI/Django/Spring Boot** — Sample protected applications
- **OPA (Open Policy Agent)** — Policy decisions
- **PostgreSQL** — Event & decision logs
- **Redis** — Session & token state
- **Isolation Forest (scikit-learn)** — Anomaly detection
- **Prometheus/Grafana** — Monitoring & observability

Every request flows through a 4-step enforcement chain:

```
JWT Verification → Risk Evaluation → Policy Decision → Enforce Decision
```

If a user's behavior deviates (IP drift, geo jump, device change, request rate spike), the platform denies or challenges the request—even with a valid JWT.

**Key Features:**
- ✅ Per-request risk scoring (0.0 - 1.0)
- ✅ Replay attack protection (60s window)
- ✅ ML-based anomaly detection
- ✅ Policy-driven decisions (OPA)
- ✅ Token revocation & management
- ✅ Full forensics & incident reconstruction
- ✅ Production-ready with Kubernetes support

---

## Getting Started in 5 Minutes

### 1. Start the Platform

```bash
cd /path/to/AZTDP

# Automated setup + startup
bash scripts/startup.sh
```

**What it does:**
- Creates `.env` with random secure passwords
- Builds all Docker images
- Starts all 13 services (2-5 minutes)
- Tests authentication
- Shows you the next steps

### 2. Get an Authentication Token

```bash
TOKEN=$(curl -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token \
  -d grant_type=password \
  -d client_id=aztdp-client \
  -d client_secret=aztdp-secret \
  -d username=user1 \
  -d password=password \
  | jq -r .access_token)

echo "Token acquired: ${TOKEN:0:50}..."
```

### 3. Make Your First Protected Request

```bash
curl -H "Authorization: Bearer $TOKEN" \
     -H "X-Client-Ip: 203.0.113.10" \
     -H "X-Geo: US-CA" \
     http://localhost:8010/v1/payments/123

# Expected: HTTP 200 with JSON response
```

### 4. View the Dashboards

Open your browser:
- **Grafana:** http://localhost:3000 (admin/admin)
- **Keycloak:** http://localhost:8080 (admin/admin)
- **Prometheus:** http://localhost:9090

### 5. Verify Everything Works

```bash
bash scripts/validate_platform.sh
```

Expected output:
```
✓ PASS: All services running
✓ PASS: All health endpoints responding
✓ PASS: Authentication working
✓ PASS: Enforcement chain validated
```

---

## Understanding the Platform

### Architecture Overview

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ Bearer JWT
       ↓
┌─────────────────────────────────────────────────────┐
│             Django / Spring App                      │
│  (Protected service + middleware enforcement)        │
└───────────┬─────────────────────────┬───────────────┘
            │ 1. Verify JWT           │ 3. Policy Decision
            ↓                         ↓
         ┌──────────────┐        ┌─────────────┐
         │  Keycloak    │        │   Gateway   │
         │  (Auth)      │        │ (OPA + OPA) │
         └──────────────┘        └──┬──────┬───┘
                                    │      │
                        ┌───────────┘      │
                        ↓                  ↓
                   ┌─────────────┐   ┌──────────────┐
                   │ Risk Engine │   │    Redis     │
                   │ (Scoring)   │   │ (State/Cache)│
                   └──────┬──────┘   └──────────────┘
                          │
                          ↓
                   ┌──────────────────┐
                   │ Anomaly Service  │
                   │ (ML Detection)   │
                   └──────────────────┘

       Observability:
       Prometheus → Grafana (http://localhost:3000)
       PostgreSQL → Telemetry & Forensics
```

### Request Flow

Each request goes through:

**Step 1: JWT Verification**
- Extract token from Authorization header
- Verify RS256 signature against Keycloak JWKS
- Cache JWKS for 5 minutes
- Extract claims: user, ip, geo, jti

**Step 2: Risk Evaluation**
- Score IP drift (same user, different IP in 60s? → high risk)
- Score geo drift (location jump >6500 km? → high risk)
- Score device change (User-Agent changed? → medium risk)
- Score request rate (>10x normal? → medium risk)
- Call Anomaly Service for ML score
- Return: risk_score (0.0 - 1.0)

**Step 3: Policy Decision**
- Query OPA with: user, ip, geo, risk_score
- Check Redis for token revocation
- Check Redis for replay attack
- Return decision: allow | deny | stepup (MFA) | revoke

**Step 4: Enforce Decision**
- **Allow:** Pass to business logic
- **Deny (403):** Block request
- **Stepup (401):** Return MFA challenge
- **Revoke:** Revoke token + return 403

---

## Key Concepts

### Risk Scoring (0.0 - 1.0)

Each request gets a risk score based on:
- **IP Drift:** Did the user's IP change within 60 seconds?
- **Geo Drift:** Did the user travel >6500 km in impossible time?
- **Device Change:** Did the User-Agent change?
- **Request Rate:** Is the user making >10x normal requests/minute?
- **Anomaly Score:** Does ML model flag unusual behavior?

Example:
```
Normal request:
  - Same IP → 0.0
  - Same geo → 0.0
  - Same device → 0.0
  - Normal rate → 0.0
  - Baseline behavior → 0.0
  → SCORE: 0.0 (allow)

Suspicious request:
  - Different IP → +0.2
  - Geo jump → +0.3
  - New device → +0.2
  - Rate spike → +0.2
  - Anomaly detected → +0.3
  → SCORE: 1.0 (deny or stepup)
```

### Policy Decisions

OPA rules determine outcomes based on risk score:

```python
# pseudocode
if risk_score < 0.3:
    decision = "allow"
elif risk_score < 0.7:
    decision = "stepup"  # Require MFA
else:
    decision = "deny"

# Also check revocation list
if jti in revoked_tokens:
    decision = "revoke"  # Revoke + deny

# Replay protection is hard-deny
if ip_changed_in_60s:
    return 409  # Conflict (replay detected)
```

### Replay Protection

If the same token is used from two different IPs within 60 seconds:

```
10:00:00 - Token used from IP 203.0.113.10 (USA)
10:00:05 - Same token from IP 1.2.3.4 (China)
          → HTTP 409 Conflict (replay detected)
          → Token is revoked
          → Future requests with this token: 403
```

---

## Common Tasks

### Get Tokens for Different Users

```bash
# Regular user
USER_TOKEN=$(curl -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token \
  -d grant_type=password \
  -d client_id=aztdp-client \
  -d client_secret=aztdp-secret \
  -d username=user1 \
  -d password=password | jq -r .access_token)

# Admin user
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token \
  -d grant_type=password \
  -d client_id=aztdp-client \
  -d client_secret=aztdp-secret \
  -d username=admin1 \
  -d password=password | jq -r .access_token)

# Risk analyst
RISK_TOKEN=$(curl -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token \
  -d grant_type=password \
  -d client_id=aztdp-client \
  -d client_secret=aztdp-secret \
  -d username=risk_user \
  -d password=password | jq -r .access_token)
```

### Simulate a Geo Drift Attack

```bash
# Token from US
RESPONSE=$(curl -s -w "\n%{http_code}" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Client-Ip: 203.0.113.10" \
  -H "X-Geo: US-CA" \
  http://localhost:8010/v1/payments/123)

echo "Response: $RESPONSE"

# Wait 10 seconds, then from UK
sleep 10
curl -w "\nStatus: %{http_code}\n" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Client-Ip: 192.0.2.50" \
  -H "X-Geo: GB-LND" \
  http://localhost:8010/v1/payments/456
```

### Revoke a Token

```bash
# Extract JTI from token
JTI=$(echo "$TOKEN" | cut -d. -f2 | base64 -d | jq -r .jti)

# Revoke it
curl -X POST http://localhost:8000/v1/tokens/revoke \
  -H "Content-Type: application/json" \
  -d "{\"jti\": \"$JTI\"}"

# Try to use revoked token (should fail)
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8010/v1/payments/123
# Expected: 403 Forbidden
```

### View Forensics & Incident Timeline

```bash
# Get all events for a user
curl -s "http://localhost:8004/v1/forensics/events?user_id=user1" | jq '.events[]'

# Get incident details by request_id
curl -s "http://localhost:8004/v1/forensics/incidents/request-123" | jq .

# Get attack timeline
curl -s "http://localhost:8004/v1/forensics/replay/session-123" | jq '.timeline[]'
```

### Run Attack Simulation Tests

```bash
# Start the platform
docker compose up -d

# Install test dependencies
pip install pytest==8.2.2

# Run attack simulations
AZTDP_RUN_LIVE_TESTS=1 \
AZTDP_BASE_URL=http://localhost:8010 \
AZTDP_USERNAME=user1 \
AZTDP_PASSWORD=password \
pytest services/attack-sim/test_attack_outcomes.py -v
```

---

## Service Details

### Core AZTDP Services

| Service | Port | Purpose | Endpoints |
|---------|------|---------|-----------|
| **Gateway** | 8000 | Policy decision API | `/v1/policies/evaluate`, `/v1/tokens/revoke` |
| **Risk Engine** | 8001 | Risk scoring | `/v1/risk/evaluate` |
| **Anomaly Service** | 8002 | ML anomaly detection | `/v1/anomaly/score` |
| **Telemetry Ingest** | 8003 | Event persistence | `/v1/telemetry/event` |
| **Forensics** | 8004 | Incident query & replay | `/v1/forensics/events`, `/v1/forensics/incidents/{id}` |
| **Django App** | 8010 | Protected app (Python) | `/v1/payments/{id}`, `/health` |
| **Spring App** | 8011 | Protected app (Java) | `/v1/orders/{id}`, `/health` |

### Infrastructure Services

| Service | Port | Purpose |
|---------|------|---------|
| **Keycloak** | 8080 | OIDC identity provider |
| **OPA** | 8181 | Open Policy Agent (Rego rules) |
| **PostgreSQL** | 5432 | Risk/decision/anomaly/audit logs |
| **Redis** | 6379 | Session state & token revocation |
| **Prometheus** | 9090 | Metrics scraping |
| **Grafana** | 3000 | Dashboards & visualization |

---

## Troubleshooting Quick Reference

**Services won't start:**
```bash
docker compose logs <service-name>  # Check logs
docker compose restart <service-name>  # Restart
```

**Token request fails:**
```bash
curl http://localhost:8080/health/ready  # Check Keycloak
docker compose logs keycloak | tail -20
```

**Request gets 403:**
```bash
docker compose logs gateway  # Check policy decision reason
curl http://localhost:8001/v1/risk/evaluate  # Check risk engine
```

**High latency:**
```bash
docker stats  # Check resource usage
docker compose exec redis redis-cli INFO memory  # Check Redis memory
```

**Database issues:**
```bash
docker compose exec postgres psql -U aztdp -d aztdp -c "SELECT 1;"
```

For detailed troubleshooting, see [docs/runbooks/QUICK_START_GUIDE.md § Troubleshooting](docs/runbooks/QUICK_START_GUIDE.md#10-troubleshooting).

---

## Documentation Map

### Getting Started
- **This file** — Overview & quick start (you are here)
- **[Quick Start Guide](docs/runbooks/QUICK_START_GUIDE.md)** — Detailed operational guide (80+ pages)
- **[Platform Verification Checklist](PLATFORM_VERIFICATION_CHECKLIST.md)** — 100-item validation checklist

### Architecture & Design
- **[Architecture Documentation](docs/architecture/ARCHITECTURE.md)** — Component inventory, ADRs, known gaps
- **[Sequence Diagrams](docs/architecture/sequence-diagrams.md)** — 8 request flows (normal, replay, stepup, etc.)
- **[Threat Model](docs/threat-model/THREAT_MODEL.md)** — STRIDE analysis, 8 security gaps, 6 attack scenarios

### API & Integration
- **[Gateway API](docs/api/gateway.openapi.yaml)** — Policy decision endpoints
- **[Risk Engine API](docs/api/risk-engine.openapi.yaml)** — Risk scoring endpoint
- **[Anomaly Service API](docs/api/anomaly-service.openapi.yaml)** — ML scoring endpoint
- **[Telemetry API](docs/api/telemetry-ingest.openapi.yaml)** — Event ingestion
- **[Forensics API](docs/api/forensics.openapi.yaml)** — Incident query endpoints

### Operations & Deployment
- **[Operations Manual](docs/runbooks/OPERATIONS_MANUAL.md)** — Production deployment, scaling, backups, HA
- **[Incident Response Playbook](docs/runbooks/INCIDENT_RESPONSE.md)** — Security incident handling
- **[Contributing Guide](docs/CONTRIBUTING.md)** — Development setup, PR checklist

### Security & Compliance
- **[Security Guide](docs/SECURITY.md)** — Vulnerability reporting, known gaps, hardening

### Data & Configuration
- **[Redis Patterns](docs/data-model/REDIS_PATTERNS.md)** — 5 key patterns, TTLs, memory sizing
- **[Database Schema](scripts/db/schema.sql)** — 6 tables, 22 indexes
- **[Component Ports](docs/architecture/component-ports.md)** — Port map, 30+ env vars

---

## Deployment Options

### Option 1: Docker Compose (Easiest)
✅ Best for: Development, testing, POCs  
⏱️ Setup time: 5 minutes  
💾 Persistence: Volumes

```bash
bash scripts/startup.sh
```

### Option 2: Docker Swarm
✅ Best for: Small production deployments  
⏱️ Setup time: 15 minutes  
💾 Persistence: Volumes + backup automation

```bash
docker swarm init
docker stack deploy -c docker-compose.yml aztdp
```

### Option 3: Kubernetes with Helm
✅ Best for: Enterprise, multi-region, auto-scaling  
⏱️ Setup time: 30 minutes  
💾 Persistence: PVCs + backup policies

```bash
helm install aztdp infra/helm/ -n aztdp --create-namespace
```

---

## Testing & Validation

### Automated Testing

```bash
# Unit tests (all services)
pytest

# Integration tests (against running stack)
AZTDP_RUN_LIVE_TESTS=1 pytest services/attack-sim/

# Load testing
locust -f scripts/load/locustfile.py --host http://localhost:8010
```

### Manual Testing

See [Quick Start Guide § 5. Getting Started with Requests](docs/runbooks/QUICK_START_GUIDE.md#5-getting-started-with-requests) for:
- Token generation
- Authenticated requests
- IP drift detection
- Geo drift detection
- Replay detection
- Token revocation

---

## Support & Next Steps

✅ **Platform is running?**
- Read [Quick Start Guide](docs/runbooks/QUICK_START_GUIDE.md) for detailed operations

✅ **Want to understand the architecture?**
- Read [Architecture Documentation](docs/architecture/ARCHITECTURE.md)

✅ **Need to deploy to production?**
- Read [Operations Manual](docs/runbooks/OPERATIONS_MANUAL.md)

✅ **Need to respond to a security incident?**
- Read [Incident Response Playbook](docs/runbooks/INCIDENT_RESPONSE.md)

✅ **Want to contribute or modify?**
- Read [Contributing Guide](docs/CONTRIBUTING.md)

---

## Key Statistics

| Metric | Value |
|--------|-------|
| **Total Services** | 13 (core + infra) |
| **Lines of Code** | 10,000+ |
| **Test Cases** | 50+ |
| **API Endpoints** | 20+ |
| **OPA Policy Rules** | 15+ |
| **Database Tables** | 6 |
| **Prometheus Metrics** | 30+ |
| **Grafana Dashboards** | 3 |
| **Documentation Pages** | 40+ |
| **Deployment Models** | 3 (Docker, Swarm, K8s) |

---

## License & Attribution

AZTDP is a reference architecture for zero-trust security. Built with open-source tools:
- **Keycloak** (Apache 2.0)
- **OPA** (Apache 2.0)
- **FastAPI** (MIT)
- **Django** (BSD)
- **Spring Boot** (Apache 2.0)
- **PostgreSQL** (PostgreSQL License)
- **Redis** (Redis License)
- **Prometheus** (Apache 2.0)
- **Grafana** (AGPL)

---

## Getting Help

**Issue with the platform?**
1. Check [Quick Start Guide § Troubleshooting](docs/runbooks/QUICK_START_GUIDE.md#10-troubleshooting)
2. Run `bash scripts/validate_platform.sh`
3. Check service logs: `docker compose logs <service>`

**Question about architecture?**
- Read [Architecture Documentation](docs/architecture/ARCHITECTURE.md)
- Check [Threat Model](docs/threat-model/THREAT_MODEL.md)

**Want to contribute?**
- Read [Contributing Guide](docs/CONTRIBUTING.md)
- Check [Milestones](docs/milestones/MILESTONES.md) for what's next

---

**Happy securing! 🔒**

For questions or feedback, see [Contributing Guide](docs/CONTRIBUTING.md).
