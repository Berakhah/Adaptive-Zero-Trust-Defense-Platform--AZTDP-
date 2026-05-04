# AZTDP Quick Start & Operational Guide

Complete guide to running, using, and validating the Adaptive Zero-Trust Defense Platform.

**Table of Contents:**
- [1. Prerequisites](#1-prerequisites)
- [2. Initial Setup](#2-initial-setup)
- [3. Starting the Platform](#3-starting-the-platform)
- [4. Health Checks & Validation](#4-health-checks--validation)
- [5. Getting Started with Requests](#5-getting-started-with-requests)
- [6. Understanding the Enforcement Chain](#6-understanding-the-enforcement-chain)
- [7. Monitoring & Dashboards](#7-monitoring--dashboards)
- [8. Running Tests](#8-running-tests)
- [9. Common Tasks](#9-common-tasks)
- [10. Troubleshooting](#10-troubleshooting)

---

## 1. Prerequisites

### System Requirements
- **Docker & Docker Compose** (v3.8+)
- **8 GB RAM** minimum (recommend 16 GB for comfortable testing)
- **Bash/Zsh shell** (or PowerShell on Windows)
- **curl** (for command-line testing)
- **jq** (optional, for JSON parsing)

### Port Availability
Ensure the following ports are available:
- `8000, 8001, 8002, 8003, 8004` — AZTDP backend services
- `8010, 8011` — Django & Spring test apps
- `8080` — Keycloak (OIDC)
- `8181` — OPA (policy engine)
- `5432` — PostgreSQL
- `6379` — Redis
- `9090` — Prometheus
- `3000` — Grafana

### Platform Requirements
- Docker installed: `docker --version`
- Docker Compose installed: `docker compose version`

---

## 2. Initial Setup

### 2.1 Clone or Extract the Project

```bash
cd /path/to/AZTDP
```

### 2.2 Create Environment File

```bash
cp .env.example .env
```

Edit `.env` with your values:

```bash
# Database
POSTGRES_PASSWORD=aztdp_password_here

# Keycloak
KEYCLOAK_ADMIN_PASSWORD=keycloak_admin_here

# Optional: Set per-service fail-open behavior
AZTDP_FAIL_OPEN=false  # Change to 'true' to allow requests on backend errors
```

### 2.3 Verify Project Structure

```bash
# Should show the following key directories:
ls -d services docs policies infra scripts
# Expected: services  docs  policies  infra  scripts
```

---

## 3. Starting the Platform

### 3.1 Build and Start All Services (First Time)

```bash
# Build all Docker images and start services
docker compose up -d --build

# This will start:
# - PostgreSQL (data persistence)
# - Redis (session & rate-limit state)
# - Keycloak (OIDC identity)
# - OPA (policy engine)
# - 5 AZTDP backend services
# - 2 test apps (Django & Spring)
# - Prometheus & Grafana (monitoring)
```

### 3.2 Wait for Services to Start

Keycloak takes ~60 seconds to initialize the realm. Wait for it:

```bash
# Poll until Keycloak is ready
until curl -sf http://localhost:8080/health/ready > /dev/null; do
  echo "Waiting for Keycloak..."
  sleep 5
done
echo "Keycloak ready!"
```

Or just wait a moment and move to health checks.

### 3.3 Stop the Platform

```bash
# Graceful stop (keeps data)
docker compose down

# Stop and remove all data (fresh start next time)
docker compose down -v
```

---

## 4. Health Checks & Validation

### 4.1 Check All Services Are Running

```bash
# List all running containers
docker compose ps

# Expected output:
# NAME                STATUS              PORTS
# gateway             Up (healthy)        0.0.0.0:8000->8080/tcp
# risk-engine         Up (healthy)        0.0.0.0:8001->8080/tcp
# anomaly-service     Up (healthy)        0.0.0.0:8002->8080/tcp
# telemetry-ingest    Up (healthy)        0.0.0.0:8003->8080/tcp
# forensics           Up (healthy)        0.0.0.0:8004->8080/tcp
# django-app          Up (healthy)        0.0.0.0:8010->8080/tcp
# spring-app          Up (healthy)        0.0.0.0:8011->8080/tcp
# keycloak            Up (healthy)        0.0.0.0:8080->8080/tcp
# opa                 Up (healthy)        0.0.0.0:8181->8181/tcp
# postgres            Up (healthy)        0.0.0.0:5432->5432/tcp
# redis               Up (healthy)        0.0.0.0:6379->6379/tcp
# prometheus          Up                  0.0.0.0:9090->9090/tcp
# grafana             Up                  0.0.0.0:3000->3000/tcp
```

### 4.2 Validate Each Service Health Endpoint

```bash
# Core AZTDP services
curl -s http://localhost:8000/health | jq .
curl -s http://localhost:8001/health | jq .
curl -s http://localhost:8002/health | jq .
curl -s http://localhost:8003/health | jq .
curl -s http://localhost:8004/health | jq .

# Test apps
curl -s http://localhost:8010/health | jq .
curl -s http://localhost:8011/health | jq .

# Infrastructure
curl -s http://localhost:8080/health/ready | jq .
curl -s http://localhost:8181/health | jq .
```

All should return HTTP 200 with health status.

### 4.3 Test Database Connectivity

```bash
# Connect to PostgreSQL
docker compose exec postgres psql -U aztdp -d aztdp -c "SELECT version();"

# Should return the PostgreSQL version
```

### 4.4 Test Redis Connectivity

```bash
# Connect to Redis
docker compose exec redis redis-cli ping

# Expected: PONG
```

### 4.5 Test OPA Policy Engine

```bash
# Query OPA for a simple policy
curl -s -X POST http://localhost:8181/v1/data/authz/decision \
  -H "Content-Type: application/json" \
  -d '{
    "user": "user1",
    "ip": "203.0.113.10",
    "geo": "US-CA",
    "request_id": "test-123"
  }' | jq .

# Should return a policy decision object
```

---

## 5. Getting Started with Requests

### 5.1 Get an Authentication Token

```bash
# Request a token from Keycloak (valid for 5 min)
TOKEN=$(curl -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token \
  -d grant_type=password \
  -d client_id=aztdp-client \
  -d client_secret=aztdp-secret \
  -d username=user1 \
  -d password=password \
  | jq -r .access_token)

# Verify you got a token
echo "Token: ${TOKEN:0:50}..."

# (Or without jq, manually copy the access_token from the response)
```

### 5.2 Decode & Inspect the Token

```bash
# Decode the JWT claims (no verification)
echo "$TOKEN" | cut -d. -f2 | base64 -d | jq .

# Expected claims:
# {
#   "sub": "user1",
#   "preferred_username": "user1",
#   "aud": "aztdp-api",
#   "exp": <timestamp>,
#   "iat": <timestamp>,
#   ...
# }
```

### 5.3 Make an Authenticated Request to Django App

```bash
# Simple request with token + location headers
curl -v -H "Authorization: Bearer $TOKEN" \
     -H "X-Client-Ip: 203.0.113.10" \
     -H "X-Geo: US-CA" \
     http://localhost:8010/v1/payments/123

# Expected response: HTTP 200
# JSON response with payment details
```

### 5.4 View the Request in Logs

```bash
# Follow the Django app logs
docker compose logs -f django-app

# You should see:
# - JWT verification
# - Risk evaluation
# - Policy decision
# - Response
```

---

## 6. Understanding the Enforcement Chain

Every authenticated request flows through this decision chain:

```
Client Request
  ↓
[1] JWT Verification
    - Verify RS256 signature against Keycloak's JWKS
    - Cache JWKS for 5 min
    - Extract: user, ip, geo, jti
  ↓
[2] Risk Evaluation (Risk Engine)
    - Score IP drift (same user, different IP in 60s window?)
    - Score geo drift (calc km between geos, flag >6500 km jumps)
    - Score device change (count unique User-Agent per session)
    - Score request rate (count requests/min, flag >10x normal)
    - Call Anomaly Service for ML score
    - Return risk score (0.0 - 1.0)
  ↓
[3] Policy Decision (Gateway)
    - Query OPA with: user, ip, geo, risk_score
    - Check token revocation (Redis lookup by sha256(jti))
    - Check replay detection (same token + IP change in 60s → HTTP 409)
    - Return decision: allow | deny (403) | stepup (401) | revoke
  ↓
[4] Enforce Decision
    - If allow: pass request to Django/Spring app
    - If deny: return HTTP 403 Forbidden
    - If stepup: return HTTP 401 + MFA challenge
    - If revoke: revoke token + return HTTP 403
  ↓
Response sent to client
```

### 6.1 Test IP Drift Detection

```bash
# First request from one IP
curl -H "Authorization: Bearer $TOKEN" \
     -H "X-Client-Ip: 203.0.113.10" \
     -H "X-Geo: US-CA" \
     http://localhost:8010/v1/payments/123

# Immediate second request from different IP (within 60s)
# Risk engine will flag "replay_detected = true"
curl -H "Authorization: Bearer $TOKEN" \
     -H "X-Client-Ip: 192.0.2.50" \
     -H "X-Geo: US-NY" \
     http://localhost:8010/v1/payments/456

# Expected: HTTP 409 Conflict (replay detected)
```

### 6.2 Test Policy-Based Denial

```bash
# Request with high-risk geolocation (e.g., from China)
curl -H "Authorization: Bearer $TOKEN" \
     -H "X-Client-Ip: 1.2.3.4" \
     -H "X-Geo: CN" \
     http://localhost:8010/v1/payments/123

# OPA policy may deny based on geography
# Expected: HTTP 403 Forbidden (if policy blocks CN)
# Check the OPA rules in policies/opa/rules/authz.rego
```

### 6.3 Test Token Revocation

```bash
# Revoke a token via the gateway
curl -X POST http://localhost:8000/v1/tokens/revoke \
  -H "Content-Type: application/json" \
  -d "{\"jti\": \"<extracted-jti>\"}"

# Now use that token again
curl -H "Authorization: Bearer $TOKEN" \
     -H "X-Client-Ip: 203.0.113.10" \
     -H "X-Geo: US-CA" \
     http://localhost:8010/v1/payments/123

# Expected: HTTP 403 Forbidden (token revoked)
```

---

## 7. Monitoring & Dashboards

### 7.1 Access Grafana

```bash
# Open in browser
open http://localhost:3000

# Or navigate manually: http://localhost:3000
# Default credentials: admin / admin
```

### 7.2 View AZTDP Dashboard

1. In Grafana, click **Home** → **Dashboards**
2. Look for the **AZTDP** folder
3. Click **AZTDP Overview** dashboard

You should see:
- Request count (total & by status)
- Risk score distribution
- Policy decisions (allow/deny/stepup/revoke counts)
- Anomaly detections
- Service latencies
- Error rates

### 7.3 View Prometheus Metrics

```bash
# Open Prometheus
open http://localhost:9090

# Or: http://localhost:9090
```

Useful queries:

```promql
# Request count by status
rate(http_requests_total[5m])

# Average response time
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Risk scores by decision type
rate(risk_decisions_total[5m])

# Anomaly service latency
histogram_quantile(0.99, rate(anomaly_service_duration_seconds_bucket[5m]))
```

### 7.4 Check Service Logs

```bash
# View logs for a specific service
docker compose logs gateway
docker compose logs risk-engine
docker compose logs anomaly-service

# Stream logs in real-time
docker compose logs -f django-app

# View logs for multiple services
docker compose logs gateway risk-engine anomaly-service
```

---

## 8. Running Tests

### 8.1 Unit Tests (Python Services)

```bash
# Install test dependencies
pip install pytest==8.2.2 pytest-django httpx

# Install all service dependencies
for req in services/*/requirements.txt; do pip install -r "$req"; done

# Run all tests
pytest

# Run tests for a specific service
pytest services/risk-engine/tests/
pytest services/gateway/tests/
pytest services/anomaly-service/tests/

# Run with verbose output
pytest -v

# Run with coverage
pip install pytest-cov
pytest --cov=services --cov-report=html
```

### 8.2 Integration Tests (Against Running Stack)

```bash
# Ensure the full stack is running
docker compose up -d

# Run attack simulation tests
AZTDP_RUN_LIVE_TESTS=1 \
AZTDP_BASE_URL=http://localhost:8010 \
AZTDP_USERNAME=user1 \
AZTDP_PASSWORD=password \
pytest services/attack-sim/test_attack_outcomes.py -v

# Expected: All tests pass with various attack scenarios
```

### 8.3 Java Tests (Spring App)

```bash
# Navigate to Spring app
cd services/spring-app

# Run tests with Maven
mvn test

# Or run a specific test class
mvn test -Dtest=RiskEnforcementFilterTest
```

### 8.4 Load Testing

```bash
# Install Locust
pip install locust==2.24.1

# Run load test (100 users, 10 spawn rate, 5 min duration)
locust -f scripts/load/locustfile.py \
       --host http://localhost:8010 \
       --users 100 \
       --spawn-rate 10 \
       --run-time 5m \
       --headless

# Or with Grafana UI
locust -f scripts/load/locustfile.py \
       --host http://localhost:8010

# Then open http://localhost:8089 and start the test
```

---

## 9. Common Tasks

### 9.1 Get Tokens for Different Users

```bash
# user1 (regular user)
USER1_TOKEN=$(curl -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token \
  -d grant_type=password \
  -d client_id=aztdp-client \
  -d client_secret=aztdp-secret \
  -d username=user1 \
  -d password=password \
  | jq -r .access_token)

# admin1 (admin user)
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token \
  -d grant_type=password \
  -d client_id=aztdp-client \
  -d client_secret=aztdp-secret \
  -d username=admin1 \
  -d password=password \
  | jq -r .access_token)

# risk_user (risk analyst)
RISK_TOKEN=$(curl -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token \
  -d grant_type=password \
  -d client_id=aztdp-client \
  -d client_secret=aztdp-secret \
  -d username=risk_user \
  -d password=password \
  | jq -r .access_token)
```

### 9.2 Query Forensics Events

```bash
# Get all events for user1
curl -s http://localhost:8004/v1/forensics/events?user_id=user1 | jq .

# Get events in a time range
curl -s "http://localhost:8004/v1/forensics/events?start_time=2024-01-01T00:00:00Z&end_time=2024-12-31T23:59:59Z" | jq .

# Get incident details by request_id
curl -s http://localhost:8004/v1/forensics/incidents/request-123 | jq .
```

### 9.3 View Telemetry Data

```bash
# Connect to PostgreSQL
docker compose exec postgres psql -U aztdp -d aztdp

# View risk evaluations
SELECT request_id, user_id, risk_score, decision, created_at 
FROM risk_evaluations 
ORDER BY created_at DESC 
LIMIT 10;

# View anomalies detected
SELECT request_id, user_id, anomaly_score, is_anomalous, created_at 
FROM anomalies 
ORDER BY created_at DESC 
LIMIT 10;

# View policy decisions
SELECT request_id, user_id, decision, reason, created_at 
FROM policy_decisions 
ORDER BY created_at DESC 
LIMIT 10;

# View revocations
SELECT jti, user_id, reason, created_at 
FROM token_revocations 
ORDER BY created_at DESC 
LIMIT 10;
```

### 9.4 Check Redis State

```bash
# Connect to Redis
docker compose exec redis redis-cli

# View all keys (be careful on production!)
KEYS *

# Check a specific user's request rate
ZRANGE user:request_rate:user1 0 -1 WITHSCORES

# Check token revocations
KEYS revoked:token:*

# Check token last-seen timestamps
KEYS token:last_seen:*

# Get Redis memory stats
INFO memory
```

### 9.5 Add a New Test User to Keycloak

```bash
# Use the Keycloak admin console
open http://localhost:8080

# Login: admin / <KEYCLOAK_ADMIN_PASSWORD>
# Navigate: Clients > aztdp-client > Realm roles > Create role
# Or: Users > Create user > Set password > Assign roles
```

### 9.6 Change OPA Policies at Runtime

```bash
# Edit the policy file
vim policies/opa/rules/authz.rego

# Reload OPA (no restart needed)
curl -X PUT http://localhost:8181/v1/policies/authz \
  -H "Content-Type: application/json" \
  -d @policies/opa/rules/authz.rego
```

---

## 10. Troubleshooting

### 10.1 Service Fails to Start

```bash
# Check the logs
docker compose logs <service-name>

# Common issues:
# - Port already in use: "bind: address already in use"
#   → Kill the process using the port or change docker-compose.yml
# - Out of memory: "docker: Error response from daemon: OCI runtime create failed"
#   → Increase Docker memory limit or stop other containers
# - Network issues: "Name or service not known"
#   → Ensure all services are connected to the 'aztdp' network
```

### 10.2 Keycloak Won't Start

```bash
# Keycloak takes 60+ seconds to initialize
# Watch the logs
docker compose logs keycloak | tail -20

# Wait for: "Keycloak 25.0.0 on JVM"

# If it still fails:
# 1. Check PostgreSQL is healthy
docker compose exec postgres psql -U aztdp -d aztdp -c "SELECT 1;"

# 2. Check network connectivity
docker compose exec keycloak nc -zv postgres 5432

# 3. Restart Keycloak
docker compose restart keycloak
```

### 10.3 Token Request Fails

```bash
# Ensure Keycloak is healthy
curl http://localhost:8080/health/ready

# Try token request with verbose output
curl -v -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token \
  -d grant_type=password \
  -d client_id=aztdp-client \
  -d client_secret=aztdp-secret \
  -d username=user1 \
  -d password=password

# Common responses:
# 401: Wrong credentials
# 400: Invalid client_id or client_secret
# 500: Keycloak backend error (check logs)
```

### 10.4 Request Denied with 403

```bash
# Check OPA logs
docker compose logs opa

# Check Gateway logs for policy decision reason
docker compose logs gateway

# Check if token is revoked
docker compose exec redis redis-cli
> GET revoked:token:<sha256_jti>

# Check if risk score is too high
docker compose logs risk-engine

# Verify policy rules
curl http://localhost:8181/v1/policies/authz | jq .

# See the actual policy decision
curl -X POST http://localhost:8000/v1/policies/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user1",
    "ip": "203.0.113.10",
    "geo": "US-CA",
    "risk_score": 0.3
  }' | jq .
```

### 10.5 High Latency or Timeout Issues

```bash
# Check service resource usage
docker stats

# Check if any service is at capacity
docker compose exec prometheus curl -s http://gateway:8080/metrics | grep http_request_duration

# Look for high latencies
docker compose logs gateway | grep "duration"

# Check Redis performance
docker compose exec redis redis-cli --latency-history

# Check PostgreSQL query performance
docker compose exec postgres psql -U aztdp -d aztdp -c "\timing"
SELECT * FROM risk_evaluations LIMIT 1;
```

### 10.6 Database Issues

```bash
# Check if PostgreSQL is accepting connections
docker compose exec postgres pg_isready -U aztdp -d aztdp

# Check disk space
docker compose exec postgres df -h

# Check table sizes
docker compose exec postgres psql -U aztdp -d aztdp -c "SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) FROM pg_tables ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;"

# Rebuild schema
docker compose down -v
docker compose up -d
# Services will auto-initialize schema on first run
```

### 10.7 Redis Out of Memory

```bash
# Check Redis memory
docker compose exec redis redis-cli INFO memory

# Clear old data
docker compose exec redis redis-cli FLUSHDB

# Or with selective cleanup
docker compose exec redis redis-cli
> EVAL "return redis.call('del', unpack(redis.call('keys', ARGV[1])))" 0 'token:last_seen:*'
> EVAL "return redis.call('del', unpack(redis.call('keys', ARGV[1])))" 0 'revoked:token:*'
```

### 10.8 View Debug Logs

```bash
# Set all Python services to debug mode
docker compose down

# Edit docker-compose.yml and add for each service:
# environment:
#   LOG_LEVEL: DEBUG

docker compose up -d --build

# Or enable for one service
docker compose exec gateway python -c "import logging; logging.getLogger().setLevel(logging.DEBUG)"
```

### 10.9 Reproduce a Specific Issue

```bash
# 1. Save request details
REQUEST_ID="test-$(date +%s)"
TOKEN="..."
IP="203.0.113.10"
GEO="US-CA"

# 2. Make the request
curl -v \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Client-Ip: $IP" \
  -H "X-Geo: $GEO" \
  -H "X-Request-Id: $REQUEST_ID" \
  http://localhost:8010/v1/payments/123

# 3. Check logs for that request
docker compose logs | grep "$REQUEST_ID"

# 4. Check database
docker compose exec postgres psql -U aztdp -d aztdp \
  -c "SELECT * FROM risk_evaluations WHERE request_id = '$REQUEST_ID';"

# 5. Check forensics
curl http://localhost:8004/v1/forensics/incidents/$REQUEST_ID | jq .
```

---

## Quick Reference

### Most Common Commands

```bash
# Start platform
docker compose up -d --build

# Check status
docker compose ps

# Get token
TOKEN=$(curl -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token \
  -d grant_type=password -d client_id=aztdp-client -d client_secret=aztdp-secret \
  -d username=user1 -d password=password | jq -r .access_token)

# Make request
curl -H "Authorization: Bearer $TOKEN" \
     -H "X-Client-Ip: 203.0.113.10" \
     -H "X-Geo: US-CA" \
     http://localhost:8010/v1/payments/123

# View logs
docker compose logs -f <service-name>

# Access dashboards
open http://localhost:3000     # Grafana
open http://localhost:9090     # Prometheus
open http://localhost:8080     # Keycloak

# Stop platform
docker compose down

# Clean everything
docker compose down -v
```

---

## Additional Resources

- **Architecture:** [docs/architecture/ARCHITECTURE.md](../architecture/ARCHITECTURE.md)
- **API Specs:** [docs/api/](../api/)
- **Security Model:** [docs/SECURITY.md](../SECURITY.md)
- **Threat Model:** [docs/threat-model/THREAT_MODEL.md](../threat-model/THREAT_MODEL.md)
- **Incident Response:** [docs/runbooks/INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md)
- **Contributing:** [docs/CONTRIBUTING.md](../CONTRIBUTING.md)

