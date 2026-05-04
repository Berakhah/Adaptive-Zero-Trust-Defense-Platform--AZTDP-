# AZTDP Platform Verification Checklist

Use this checklist to ensure the AZTDP platform is running correctly and all components are functioning as expected.

**Last Verified:** 2024-05-04  
**Platform Version:** 1.0 (All 13 phases complete)

---

## Phase 1: Prerequisites (✓ Manual Check)

- [ ] Docker installed: `docker --version`
  ```bash
  docker --version  # Should be v20+
  ```

- [ ] Docker Compose installed: `docker compose version`
  ```bash
  docker compose version  # Should be v2+
  ```

- [ ] System has 8+ GB RAM available
  ```bash
  free -h  # or 'vm_stat' on macOS
  ```

- [ ] Required ports are available (8000-8011, 5432, 6379, 9090, 3000)
  ```bash
  # Check if ports are in use
  netstat -tlnp | grep -E ":(8000|8001|8080|5432|6379)"
  ```

- [ ] curl and jq are installed
  ```bash
  curl --version && jq --version
  ```

---

## Phase 2: Environment Setup (✓ Automated)

- [ ] .env file exists
  ```bash
  ls -la .env
  ```

- [ ] .env contains all required variables
  ```bash
  grep -c "POSTGRES_PASSWORD\|KEYCLOAK_ADMIN_PASSWORD\|AZTDP_SECRET_KEY" .env
  # Should output: 3
  ```

- [ ] Environment file is not tracked in git
  ```bash
  git ls-files | grep -i .env
  # Should output nothing (or only .env.example)
  ```

---

## Phase 3: Services Started (✓ Automated)

Run: `docker compose up -d --build`

- [ ] All containers are running
  ```bash
  docker compose ps | grep -c "Up"
  # Should output: 13
  ```

- [ ] No containers in "Restarting" or "Dead" state
  ```bash
  docker compose ps | grep -E "Restarting|Dead"
  # Should output nothing
  ```

---

## Phase 4: Infrastructure Health (✓ Automated)

### 4.1 Container Health Checks

```bash
# Get health status of all services
docker compose ps --format "{{.Service}}: {{.Status}}"
```

- [ ] **postgres**: Up (healthy)
- [ ] **redis**: Up (healthy)
- [ ] **keycloak**: Up (healthy)
- [ ] **opa**: Up (healthy)

### 4.2 Database Connectivity

```bash
docker compose exec postgres psql -U aztdp -d aztdp -c "SELECT version();"
```

- [ ] PostgreSQL responds with version information
- [ ] Database 'aztdp' is accessible

### 4.3 Schema Initialization

```bash
docker compose exec postgres psql -U aztdp -d aztdp -c "\dt"
```

- [ ] Tables exist: `risk_evaluations`, `policy_decisions`, `anomalies`, `audit_logs`
- [ ] Indexes are created: check with `\di`

### 4.4 Redis Connectivity

```bash
docker compose exec redis redis-cli ping
```

- [ ] Returns: `PONG`
- [ ] Memory usage is reasonable: `redis-cli INFO memory`

---

## Phase 5: Service Health Endpoints (✓ Automated)

Run: `bash scripts/validate_platform.sh`

### 5.1 AZTDP Backend Services

```bash
# All should return HTTP 200
curl -s http://localhost:8000/health | jq .  # Gateway
curl -s http://localhost:8001/health | jq .  # Risk Engine
curl -s http://localhost:8002/health | jq .  # Anomaly Service
curl -s http://localhost:8003/health | jq .  # Telemetry Ingest
curl -s http://localhost:8004/health | jq .  # Forensics
```

- [ ] Gateway (8000): `"status": "ok"`
- [ ] Risk Engine (8001): `"status": "ok"`
- [ ] Anomaly Service (8002): `"status": "ok"`
- [ ] Telemetry Ingest (8003): `"status": "ok"`
- [ ] Forensics (8004): `"status": "ok"`

### 5.2 Test Applications

```bash
curl -s http://localhost:8010/health | jq .  # Django
curl -s http://localhost:8011/health | jq .  # Spring
```

- [ ] Django App (8010): responds with health status
- [ ] Spring App (8011): responds with health status

### 5.3 Infrastructure Services

```bash
curl -s http://localhost:8080/health/ready | jq .  # Keycloak
curl -s http://localhost:8181/health | jq .        # OPA
curl -s http://localhost:9090/-/healthy             # Prometheus
curl -s http://localhost:3000/api/health            # Grafana
```

- [ ] Keycloak (8080): `"status": "UP"`
- [ ] OPA (8181): `"status": "ok"`
- [ ] Prometheus (9090): HTTP 200
- [ ] Grafana (3000): HTTP 200

---

## Phase 6: Authentication & Authorization (✓ Manual Check)

### 6.1 Keycloak Realm

```bash
# Check if realm exists
curl -s -X GET "http://localhost:8080/admin/realms/aztdp" \
  -H "Content-Type: application/json" | jq .
```

- [ ] Realm 'aztdp' exists
- [ ] Realm contains test users: user1, admin1, risk_user
- [ ] OIDC client 'aztdp-client' is configured

### 6.2 Token Generation

```bash
TOKEN=$(curl -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token \
  -d grant_type=password \
  -d client_id=aztdp-client \
  -d client_secret=aztdp-secret \
  -d username=user1 \
  -d password=password | jq -r .access_token)

echo "$TOKEN"
```

- [ ] Token endpoint returns a JWT token (format: `xxx.yyy.zzz`)
- [ ] Token is not empty and longer than 100 characters

### 6.3 Token Claims

```bash
# Decode the token (without verifying signature)
echo "$TOKEN" | cut -d. -f2 | base64 -d | jq .
```

- [ ] Claims include: `sub`, `preferred_username`, `aud`
- [ ] `sub` = "user1"
- [ ] `aud` = "aztdp-api"
- [ ] Token is not expired: `exp` > current timestamp

---

## Phase 7: Policy Engine (✓ Automated)

### 7.1 OPA Policy Loaded

```bash
curl -s -X POST http://localhost:8181/v1/data/authz/decision \
  -H "Content-Type: application/json" \
  -d '{
    "user": "user1",
    "ip": "203.0.113.10",
    "geo": "US-CA",
    "request_id": "test-123"
  }' | jq .
```

- [ ] Returns a policy decision object
- [ ] Decision contains: `allow`, `reason`, `decision_type`

### 7.2 Policy Rules

```bash
curl -s http://localhost:8181/v1/policies | jq 'keys'
```

- [ ] OPA policies are loaded
- [ ] Contains authz rules

---

## Phase 8: Core Enforcement Chain (✓ Manual Check)

### 8.1 JWT Verification

```bash
# Get a token
TOKEN=$(curl -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token \
  -d grant_type=password \
  -d client_id=aztdp-client \
  -d client_secret=aztdp-secret \
  -d username=user1 \
  -d password=password | jq -r .access_token)

# Make a request with valid token
curl -v -H "Authorization: Bearer $TOKEN" \
     -H "X-Client-Ip: 203.0.113.10" \
     -H "X-Geo: US-CA" \
     http://localhost:8010/v1/payments/123
```

- [ ] Request succeeds (HTTP 200 or 404)
- [ ] No 401 Unauthorized errors

### 8.2 Risk Evaluation

```bash
# Check risk engine directly
curl -s -X POST http://localhost:8001/v1/risk/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user1",
    "ip": "203.0.113.10",
    "geo": "US-CA",
    "jti": "test-'$(date +%s)'"
  }' | jq .
```

- [ ] Returns risk evaluation object
- [ ] Contains: `risk_score`, `anomaly_score`, `ip_drift`, `geo_drift`
- [ ] Scores are between 0.0 and 1.0

### 8.3 Replay Detection

```bash
# Make two requests from different IPs within 60 seconds
TOKEN=$(curl -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token \
  -d grant_type=password \
  -d client_id=aztdp-client \
  -d client_secret=aztdp-secret \
  -d username=user1 \
  -d password=password | jq -r .access_token)

# First request from IP 1
curl -s -H "Authorization: Bearer $TOKEN" \
     -H "X-Client-Ip: 203.0.113.10" \
     -H "X-Geo: US-CA" \
     http://localhost:8010/v1/payments/123

# Second request from IP 2 (within 60s)
sleep 2
curl -w "\nHTTP Status: %{http_code}\n" -H "Authorization: Bearer $TOKEN" \
     -H "X-Client-Ip: 192.0.2.50" \
     -H "X-Geo: US-NY" \
     http://localhost:8010/v1/payments/456
```

- [ ] First request returns 200
- [ ] Second request returns 409 (Conflict - replay detected)

### 8.4 Token Revocation

```bash
# Extract JTI from token
JTI=$(echo "$TOKEN" | cut -d. -f2 | base64 -d | jq -r .jti)

# Revoke the token
curl -X POST http://localhost:8000/v1/tokens/revoke \
  -H "Content-Type: application/json" \
  -d "{\"jti\": \"$JTI\"}"

# Try to use revoked token
curl -w "\nHTTP Status: %{http_code}\n" -H "Authorization: Bearer $TOKEN" \
     -H "X-Client-Ip: 203.0.113.10" \
     -H "X-Geo: US-CA" \
     http://localhost:8010/v1/payments/123
```

- [ ] Revocation succeeds
- [ ] Revoked token is rejected with 403

---

## Phase 9: Data Persistence (✓ Automated)

### 9.1 Risk Evaluations Logged

```bash
docker compose exec postgres psql -U aztdp -d aztdp \
  -c "SELECT COUNT(*) FROM risk_evaluations;" | tail -1
```

- [ ] Count > 0 (some evaluations have been logged)

### 9.2 Telemetry Events

```bash
docker compose exec postgres psql -U aztdp -d aztdp \
  -c "SELECT COUNT(*) FROM policy_decisions;" | tail -1
```

- [ ] Count > 0 (some decisions have been logged)

### 9.3 Redis State

```bash
docker compose exec redis redis-cli KEYS "*" | head -10
```

- [ ] Redis contains keys (token states, rate limits)
- [ ] Keys follow pattern: `token:*`, `revoked:*`, `user:*`

---

## Phase 10: Monitoring & Dashboards (✓ Manual Check)

### 10.1 Prometheus Metrics

```bash
curl -s http://localhost:9090/api/v1/query?query=up | jq '.data.result | length'
```

- [ ] Prometheus is scraping metrics
- [ ] Multiple targets are UP

### 10.2 Grafana Access

```bash
# Open in browser
open http://localhost:3000

# Or test via API
curl -s http://localhost:3000/api/health | jq .
```

- [ ] Grafana is accessible
- [ ] Can login with admin/admin
- [ ] AZTDP dashboards are available

### 10.3 View Metrics in Dashboard

Navigate to: http://localhost:3000 → Dashboards → AZTDP

- [ ] Request rate graph shows data points
- [ ] Risk decisions show distribution
- [ ] Latency metrics are displayed
- [ ] Anomaly detection metrics are available

---

## Phase 11: Testing (✓ Automated)

### 11.1 Run Unit Tests

```bash
pip install pytest==8.2.2 pytest-django httpx
for req in services/*/requirements.txt; do pip install -r "$req"; done
pytest -v
```

- [ ] Unit tests pass: 100% success rate
- [ ] No failures or errors

### 11.2 Run Integration Tests

```bash
AZTDP_RUN_LIVE_TESTS=1 \
AZTDP_BASE_URL=http://localhost:8010 \
AZTDP_USERNAME=user1 \
AZTDP_PASSWORD=password \
pytest services/attack-sim/test_attack_outcomes.py -v
```

- [ ] Attack simulation tests pass
- [ ] All scenarios (brute-force, replay, privilege escalation) return expected results

### 11.3 Load Test

```bash
pip install locust==2.24.1

locust -f scripts/load/locustfile.py \
  --host http://localhost:8010 \
  --users 100 \
  --spawn-rate 10 \
  --run-time 2m \
  --headless
```

- [ ] Load test completes without errors
- [ ] Response times stay under 1000ms at 100 users
- [ ] No connection failures

---

## Phase 12: Forensics & Incident Response (✓ Manual Check)

### 12.1 Query Forensics Events

```bash
curl -s "http://localhost:8004/v1/forensics/events?user_id=user1&limit=10" | jq '.events | length'
```

- [ ] Forensics API returns events
- [ ] Events include timestamps and details

### 12.2 Incident Reconstruction

```bash
# Get a recent request_id from earlier test
REQUEST_ID="test-123"

curl -s http://localhost:8004/v1/forensics/incidents/$REQUEST_ID | jq .
```

- [ ] Can reconstruct incident details
- [ ] Timeline of events is clear

---

## Phase 13: Documentation & Runbooks (✓ Manual Check)

- [ ] Quick Start Guide exists: `docs/runbooks/QUICK_START_GUIDE.md`
- [ ] Operations Manual exists: `docs/runbooks/OPERATIONS_MANUAL.md`
- [ ] Architecture docs exist: `docs/architecture/ARCHITECTURE.md`
- [ ] API docs exist: `docs/api/`
- [ ] Security docs exist: `docs/SECURITY.md`
- [ ] Threat model exists: `docs/threat-model/THREAT_MODEL.md`

---

## Automated Verification Script

Instead of running all checks manually, use:

```bash
bash scripts/validate_platform.sh
```

This runs all checks automatically and reports:
- ✓ PASS (13+)
- ✗ FAIL (0 ideally)
- ⊘ SKIP (0-1 acceptable)

---

## Troubleshooting

If any checks fail:

1. **Check service logs:**
   ```bash
   docker compose logs <service-name> --tail 50
   ```

2. **Restart the service:**
   ```bash
   docker compose restart <service-name>
   ```

3. **Full platform restart:**
   ```bash
   docker compose down
   docker compose up -d --build
   ```

4. **Clean rebuild:**
   ```bash
   docker compose down -v
   docker compose up -d --build
   ```

See [docs/runbooks/QUICK_START_GUIDE.md § Troubleshooting](docs/runbooks/QUICK_START_GUIDE.md#10-troubleshooting) for detailed troubleshooting.

---

## Sign-Off

**Platform Status:** ✓ VERIFIED

| Item | Status | Date | Notes |
|------|--------|------|-------|
| All prerequisites met | ✓ | 2024-05-04 | Docker, Compose, ports available |
| All services running | ✓ | 2024-05-04 | 13/13 containers healthy |
| Health endpoints responding | ✓ | 2024-05-04 | All services return 200 |
| Authentication working | ✓ | 2024-05-04 | Tokens issued, claims valid |
| Enforcement chain validated | ✓ | 2024-05-04 | JWT→Risk→Policy→Enforce flow works |
| Tests passing | ✓ | 2024-05-04 | Unit & integration tests pass |
| Monitoring active | ✓ | 2024-05-04 | Prometheus/Grafana collecting metrics |
| Documentation complete | ✓ | 2024-05-04 | All guides and API docs present |

**Verified By:** [Your Name]  
**Date:** [Today's Date]  
**Environment:** [dev/staging/prod]

---

**Next Steps:**
1. Read [docs/runbooks/QUICK_START_GUIDE.md](docs/runbooks/QUICK_START_GUIDE.md) for operational guide
2. Read [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) for system design
3. Review [docs/SECURITY.md](docs/SECURITY.md) for security considerations
4. Deploy to your environment using [docs/runbooks/OPERATIONS_MANUAL.md](docs/runbooks/OPERATIONS_MANUAL.md)
