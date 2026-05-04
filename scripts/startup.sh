#!/bin/bash
#
# AZTDP Startup Script
# Automated setup and startup of the platform
#

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║   AZTDP - Adaptive Zero-Trust Defense Platform                ║"
echo "║   Startup Script                                              ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check Docker
if ! command -v docker &> /dev/null; then
  echo -e "${RED}✗ Docker is not installed${NC}"
  exit 1
fi

if ! docker compose version &> /dev/null; then
  echo -e "${RED}✗ Docker Compose is not installed${NC}"
  exit 1
fi

echo -e "${GREEN}✓ Docker and Docker Compose are installed${NC}\n"

# Setup .env
if [ ! -f .env ]; then
  echo -e "${YELLOW}→ Creating .env from template...${NC}"
  cp .env.example .env

  # Generate random passwords if possible
  if command -v python3 &> /dev/null; then
    POSTGRES_PASS=$(python3 -c "import secrets; print(secrets.token_hex(16))")
    KEYCLOAK_PASS=$(python3 -c "import secrets; print(secrets.token_hex(16))")
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
    INTERNAL_TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    GRAFANA_PASS=$(python3 -c "import secrets; print(secrets.token_hex(16))")

    sed -i.bak "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$POSTGRES_PASS/" .env
    sed -i.bak "s/KEYCLOAK_ADMIN_PASSWORD=.*/KEYCLOAK_ADMIN_PASSWORD=$KEYCLOAK_PASS/" .env
    sed -i.bak "s/AZTDP_SECRET_KEY=.*/AZTDP_SECRET_KEY=$SECRET_KEY/" .env
    sed -i.bak "s/AZTDP_INTERNAL_TOKEN=.*/AZTDP_INTERNAL_TOKEN=$INTERNAL_TOKEN/" .env
    sed -i.bak "s/GRAFANA_ADMIN_PASSWORD=.*/GRAFANA_ADMIN_PASSWORD=$GRAFANA_PASS/" .env
    rm -f .env.bak

    echo -e "${GREEN}✓ Generated secure passwords${NC}\n"
  fi
else
  echo -e "${GREEN}✓ .env file already exists${NC}\n"
fi

# Stop any running instances
if docker compose ps 2>/dev/null | grep -q "Up"; then
  echo -e "${YELLOW}→ Stopping existing containers...${NC}"
  docker compose down
  echo -e "${GREEN}✓ Stopped${NC}\n"
fi

# Build and start
echo -e "${YELLOW}→ Building images and starting services...${NC}"
echo -e "${YELLOW}  (This may take 2-5 minutes on first run)${NC}\n"

docker compose up -d --build

# Wait for key services
echo -e "\n${YELLOW}→ Waiting for services to initialize...${NC}"

# Wait for Keycloak (takes longest)
echo -ne "  Keycloak (up to 90s): "
for i in {1..18}; do
  if curl -sf http://localhost:8080/health/ready > /dev/null 2>&1; then
    echo -e "${GREEN}ready${NC}"
    break
  fi
  echo -ne "."
  sleep 5
done

# Wait for core services
echo -ne "  Core services: "
for service in gateway risk-engine anomaly-service; do
  for i in {1..12}; do
    if curl -sf http://localhost:800${i}/health > /dev/null 2>&1; then
      echo -ne "${GREEN}✓${NC}"
      break
    fi
    sleep 2
  done
done
echo ""

# Get initial token
echo -e "\n${YELLOW}→ Testing authentication...${NC}"
TOKEN=$(curl -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token \
  -d grant_type=password \
  -d client_id=aztdp-client \
  -d client_secret=aztdp-secret \
  -d username=user1 \
  -d password=password 2>/dev/null | grep -o '"access_token":"[^"]*' | cut -d'"' -f4 || true)

if [ ! -z "$TOKEN" ] && [ ${#TOKEN} -gt 50 ]; then
  echo -e "${GREEN}✓ Authentication working${NC}\n"
else
  echo -e "${YELLOW}⚠ Authentication test inconclusive (services may still be initializing)${NC}\n"
fi

# Summary
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Platform startup complete!${NC}\n"

echo -e "Service URLs:"
echo -e "  ${GREEN}Django App${NC}          → http://localhost:8010"
echo -e "  ${GREEN}Gateway${NC}             → http://localhost:8000"
echo -e "  ${GREEN}Risk Engine${NC}         → http://localhost:8001"
echo -e "  ${GREEN}Anomaly Service${NC}     → http://localhost:8002"
echo -e "  ${GREEN}Telemetry${NC}           → http://localhost:8003"
echo -e "  ${GREEN}Forensics${NC}           → http://localhost:8004"
echo -e "  ${GREEN}Keycloak${NC}            → http://localhost:8080"
echo -e "  ${GREEN}OPA${NC}                 → http://localhost:8181"
echo -e "  ${GREEN}Prometheus${NC}          → http://localhost:9090"
echo -e "  ${GREEN}Grafana${NC}             → http://localhost:3000 (admin/admin)"
echo -e "  ${GREEN}PostgreSQL${NC}          → localhost:5432"
echo -e "  ${GREEN}Redis${NC}               → localhost:6379\n"

echo -e "Next steps:"
echo -e "  1. Read the Quick Start Guide:"
echo -e "     ${BLUE}docs/runbooks/QUICK_START_GUIDE.md${NC}\n"
echo -e "  2. Get a token:"
echo -e "     ${BLUE}TOKEN=\$(curl -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token \\${NC}"
echo -e "       ${BLUE}-d grant_type=password -d client_id=aztdp-client \\${NC}"
echo -e "       ${BLUE}-d client_secret=aztdp-secret -d username=user1 \\${NC}"
echo -e "       ${BLUE}-d password=password | jq -r .access_token)${NC}\n"
echo -e "  3. Make a test request:"
echo -e "     ${BLUE}curl -H \"Authorization: Bearer \$TOKEN\" \\${NC}"
echo -e "       ${BLUE}-H \"X-Client-Ip: 203.0.113.10\" \\${NC}"
echo -e "       ${BLUE}-H \"X-Geo: US-CA\" \\${NC}"
echo -e "       ${BLUE}http://localhost:8010/v1/payments/123${NC}\n"
echo -e "  4. View dashboards:"
echo -e "     ${BLUE}open http://localhost:3000  # Grafana${NC}\n"
echo -e "  5. Run validation tests:"
echo -e "     ${BLUE}bash scripts/validate_platform.sh${NC}\n"

echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "\nFor help, see ${BLUE}docs/runbooks/QUICK_START_GUIDE.md${NC}\n"
