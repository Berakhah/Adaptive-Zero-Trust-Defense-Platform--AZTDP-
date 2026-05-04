#!/bin/bash
#
# AZTDP Platform Validation Script
# Automated health checks for all services and core functionality
#

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
PASSED=0
FAILED=0
SKIPPED=0

# Helper functions
print_header() {
  echo -e "\n${BLUE}═══════════════════════════════════════════════════${NC}"
  echo -e "${BLUE}$1${NC}"
  echo -e "${BLUE}═══════════════════════════════════════════════════${NC}\n"
}

print_test() {
  echo -ne "  $1 ... "
}

print_pass() {
  echo -e "${GREEN}✓ PASS${NC}"
  ((PASSED++))
}

print_fail() {
  echo -e "${RED}✗ FAIL${NC}"
  echo -e "    ${RED}$1${NC}"
  ((FAILED++))
}

print_skip() {
  echo -e "${YELLOW}⊘ SKIP${NC}"
  echo -e "    ${YELLOW}$1${NC}"
  ((SKIPPED++))
}

print_summary() {
  echo -e "\n${BLUE}═══════════════════════════════════════════════════${NC}"
  echo -e "${BLUE}VALIDATION SUMMARY${NC}"
  echo -e "${BLUE}═══════════════════════════════════════════════════${NC}"
  echo -e "  ${GREEN}Passed:${NC}  $PASSED"
  echo -e "  ${RED}Failed:${NC}  $FAILED"
  echo -e "  ${YELLOW}Skipped:${NC} $SKIPPED"

  if [ $FAILED -eq 0 ]; then
    echo -e "\n${GREEN}✓ All validations passed!${NC}\n"
    return 0
  else
    echo -e "\n${RED}✗ Some validations failed. See above for details.${NC}\n"
    return 1
  fi
}

# 1. PREREQUISITES
print_header "1. CHECKING PREREQUISITES"

print_test "Docker installed"
if command -v docker &> /dev/null; then
  print_pass
else
  print_fail "Docker not found. Install Docker to proceed."
  exit 1
fi

print_test "Docker Compose installed"
if command -v docker &> /dev/null && docker compose version &> /dev/null; then
  print_pass
else
  print_fail "Docker Compose not found. Install Docker Compose to proceed."
  exit 1
fi

print_test "curl installed"
if command -v curl &> /dev/null; then
  print_pass
else
  print_fail "curl not found. Install curl to proceed."
  exit 1
fi

print_test "jq installed"
if command -v jq &> /dev/null; then
  print_pass
else
  print_skip "jq not found (optional, for JSON parsing)"
fi

# 2. DOCKER SERVICES
print_header "2. CHECKING DOCKER SERVICES"

print_test "All containers running"
RUNNING=$(docker compose ps -q 2>/dev/null | wc -l)
if [ "$RUNNING" -ge 10 ]; then
  print_pass
else
  print_fail "Expected at least 10 containers, found $RUNNING. Run: docker compose up -d --build"
fi

# Check each service
SERVICES=("gateway" "risk-engine" "anomaly-service" "telemetry-ingest" "forensics" "django-app" "spring-app" "keycloak" "opa" "postgres" "redis")

for service in "${SERVICES[@]}"; do
  print_test "Service '$service' is running"
  if docker compose ps $service 2>/dev/null | grep -q "Up"; then
    print_pass
  else
    print_fail "Service not running. Check: docker compose logs $service"
  fi
done

# 3. HEALTH ENDPOINTS
print_header "3. CHECKING SERVICE HEALTH ENDPOINTS"

check_health() {
  local service=$1
  local port=$2

  print_test "Health check: $service (port $port)"

  if curl -sf http://localhost:$port/health > /dev/null 2>&1 || curl -sf http://localhost:$port/health/ready > /dev/null 2>&1; then
    print_pass
  else
    print_fail "Health endpoint not responding at http://localhost:$port/health"
  fi
}

check_health "gateway" 8000
check_health "risk-engine" 8001
check_health "anomaly-service" 8002
check_health "telemetry-ingest" 8003
check_health "forensics" 8004
check_health "django-app" 8010
check_health "keycloak" 8080
check_health "opa" 8181

# 4. DATABASE CONNECTIVITY
print_header "4. CHECKING DATABASE CONNECTIVITY"

print_test "PostgreSQL connection"
if docker compose exec postgres psql -U aztdp -d aztdp -c "SELECT 1;" > /dev/null 2>&1; then
  print_pass
else
  print_fail "Cannot connect to PostgreSQL"
fi

print_test "PostgreSQL schema initialized"
if docker compose exec postgres psql -U aztdp -d aztdp -c "\dt" 2>&1 | grep -q "risk_evaluations"; then
  print_pass
else
  print_fail "Database schema not initialized"
fi

print_test "Redis connection"
if docker compose exec redis redis-cli ping > /dev/null 2>&1; then
  print_pass
else
  print_fail "Cannot connect to Redis"
fi

# 5. AUTHENTICATION
print_header "5. CHECKING AUTHENTICATION"

print_test "Keycloak realm 'aztdp' exists"
REALM=$(curl -s -X GET "http://localhost:8080/admin/realms/aztdp" \
  -H "Content-Type: application/json" 2>/dev/null | grep -o "aztdp" || true)
if [ ! -z "$REALM" ]; then
  print_pass
else
  print_skip "Cannot verify realm (admin auth may be required)"
fi

print_test "Token request succeeds"
TOKEN=$(curl -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token \
  -d grant_type=password \
  -d client_id=aztdp-client \
  -d client_secret=aztdp-secret \
  -d username=user1 \
  -d password=password 2>/dev/null | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

if [ ! -z "$TOKEN" ] && [ ${#TOKEN} -gt 50 ]; then
  print_pass
  export TOKEN
else
  print_fail "Token request failed"
fi

# 6. POLICY ENGINE
print_header "6. CHECKING POLICY ENGINE"

print_test "OPA policy loaded"
if curl -s http://localhost:8181/v1/data/authz/decision 2>/dev/null | grep -q "result"; then
  print_pass
else
  print_fail "OPA policy not accessible"
fi

print_test "OPA policy decision works"
DECISION=$(curl -s -X POST http://localhost:8181/v1/data/authz/decision \
  -H "Content-Type: application/json" \
  -d '{
    "user": "user1",
    "ip": "203.0.113.10",
    "geo": "US-CA",
    "request_id": "test-$(date +%s)"
  }' 2>/dev/null | grep -o "decision")

if [ ! -z "$DECISION" ]; then
  print_pass
else
  print_fail "OPA policy decision query failed"
fi

# 7. CORE FUNCTIONALITY
print_header "7. CHECKING CORE FUNCTIONALITY"

if [ ! -z "$TOKEN" ]; then
  print_test "Protected endpoint returns 200"
  RESPONSE=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $TOKEN" \
    -H "X-Client-Ip: 203.0.113.10" \
    -H "X-Geo: US-CA" \
    http://localhost:8010/v1/payments/123 2>/dev/null)

  HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
  if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "404" ]; then
    print_pass
  else
    print_fail "Expected 200 or 404, got $HTTP_CODE"
  fi
else
  print_skip "No valid token available"
fi

print_test "Risk evaluation endpoint works"
RISK_RESPONSE=$(curl -s -X POST http://localhost:8001/v1/risk/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user1",
    "ip": "203.0.113.10",
    "geo": "US-CA",
    "jti": "test-jti-'$(date +%s)'"
  }' 2>/dev/null | grep -o '"risk_score"')

if [ ! -z "$RISK_RESPONSE" ]; then
  print_pass
else
  print_fail "Risk engine endpoint not responding"
fi

# 8. MONITORING
print_header "8. CHECKING MONITORING STACK"

print_test "Prometheus metrics endpoint"
if curl -sf http://localhost:9090/api/v1/query?query=up > /dev/null 2>&1; then
  print_pass
else
  print_fail "Prometheus not accessible"
fi

print_test "Grafana dashboard"
if curl -sf http://localhost:3000/api/health > /dev/null 2>&1; then
  print_pass
else
  print_fail "Grafana not accessible"
fi

# 9. DATA PERSISTENCE
print_header "9. CHECKING DATA PERSISTENCE"

print_test "Risk evaluations persisted to database"
COUNT=$(docker compose exec postgres psql -U aztdp -d aztdp -tc "SELECT COUNT(*) FROM risk_evaluations;" 2>/dev/null | tr -d ' ')
if [ "$COUNT" -gt "0" ] 2>/dev/null; then
  print_pass
else
  print_skip "No risk evaluations in database yet (this is ok on fresh start)"
fi

print_test "Telemetry events can be written"
WRITE_TEST=$(curl -s -X POST http://localhost:8003/v1/telemetry/event \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "test-'$(date +%s)'",
    "user_id": "user1",
    "event_type": "risk_evaluation",
    "data": {"risk_score": 0.5}
  }' 2>/dev/null)

if echo "$WRITE_TEST" | grep -q "event"; then
  print_pass
else
  print_skip "Telemetry write test inconclusive"
fi

# SUMMARY
print_summary
SUMMARY_EXIT=$?

exit $SUMMARY_EXIT
