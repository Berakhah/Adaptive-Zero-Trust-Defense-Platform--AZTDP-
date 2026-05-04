# AZTDP Operations Manual

Complete operational documentation for running and managing the Adaptive Zero-Trust Defense Platform in production and development environments.

**Table of Contents:**
- [Environment Setup](#environment-setup)
- [Deployment Models](#deployment-models)
- [Service Management](#service-management)
- [Scaling & Performance](#scaling--performance)
- [Backup & Recovery](#backup--recovery)
- [Monitoring & Alerting](#monitoring--alerting)
- [Security Hardening](#security-hardening)
- [High Availability](#high-availability)

---

## Environment Setup

### Configuration Hierarchy

AZTDP services follow this configuration precedence (highest to lowest):

1. **Environment Variables** (.env file or shell exports)
2. **Config Files** (config.py in each service)
3. **Default Values** (hard-coded in service code)

### Required Environment Variables

```bash
# Database
POSTGRES_PASSWORD=<strong-random-password>

# Identity Provider
KEYCLOAK_ADMIN_PASSWORD=<strong-random-password>

# Django/Spring Apps
AZTDP_SECRET_KEY=<output-of-python-secrets>
AZTDP_ALLOWED_HOSTS=localhost,127.0.0.1,yourdomain.com
AZTDP_INTERNAL_TOKEN=<output-of-python-secrets>

# Grafana
GRAFANA_ADMIN_PASSWORD=<strong-random-password>

# Optional: Per-service behavior
AZTDP_FAIL_OPEN=false  # Per-service: allow on backend error
AZTDP_LOG_LEVEL=INFO   # DEBUG, INFO, WARNING, ERROR
AZTDP_REPLAY_WINDOW_SECONDS=60
AZTDP_ANOMALY_THRESHOLD=0.7
```

### Development vs Production

**Development (.env):**
```bash
POSTGRES_PASSWORD=dev-password
KEYCLOAK_ADMIN_PASSWORD=dev-password
AZTDP_FAIL_OPEN=false
AZTDP_LOG_LEVEL=DEBUG
```

**Production (.env.prod):**
```bash
POSTGRES_PASSWORD=$(python3 -c "import secrets; print(secrets.token_hex(32))")
KEYCLOAK_ADMIN_PASSWORD=$(python3 -c "import secrets; print(secrets.token_hex(32))")
AZTDP_FAIL_OPEN=false  # Never fail open in production
AZTDP_LOG_LEVEL=WARNING
```

---

## Deployment Models

### 1. Docker Compose (Development/Testing)

**Recommended for:**
- Local development
- Integration testing
- POCs and demonstrations

**Startup:**
```bash
bash scripts/startup.sh
```

**Verification:**
```bash
bash scripts/validate_platform.sh
```

### 2. Docker Swarm (Small Production)

**Recommended for:**
- Single-region deployments
- <1000 requests/sec
- Teams without Kubernetes expertise

**Initialize swarm:**
```bash
docker swarm init
```

**Deploy stack:**
```bash
docker stack deploy -c docker-compose.yml aztdp
```

**Scale service:**
```bash
docker service update --replicas 3 aztdp_gateway
```

### 3. Kubernetes (Enterprise Production)

**Recommended for:**
- High-availability requirements
- Multi-region deployments
- >1000 requests/sec
- Compliance requirements

**Deploy with kubectl:**
```bash
kubectl apply -f infra/k8s/
```

**Deploy with Helm:**
```bash
helm install aztdp infra/helm/ -n aztdp --create-namespace
```

**Monitor deployment:**
```bash
kubectl get pods -n aztdp
kubectl logs -n aztdp deployment/gateway
```

---

## Service Management

### Docker Compose Commands

```bash
# Start all services
docker compose up -d

# Stop all services (preserves data)
docker compose down

# Stop and remove all data
docker compose down -v

# Restart a specific service
docker compose restart gateway

# View logs
docker compose logs -f gateway

# Execute command in container
docker compose exec gateway python app.py

# Resource usage
docker stats
```

### Health Checks

Every AZTDP service includes a `/health` endpoint returning:

```json
{
  "status": "ok",
  "timestamp": "2024-01-15T10:30:00Z",
  "version": "1.0.0",
  "dependencies": {
    "database": "ok",
    "redis": "ok",
    "keycloak": "ok"
  }
}
```

**Automated health monitoring:**
```bash
# Check all services every 30 seconds
watch -n 30 '
  for port in 8000 8001 8002 8003 8004 8010 8080 8181; do
    echo -n "Port $port: "
    curl -s http://localhost:$port/health | jq -r .status || echo "down"
  done
'
```

### Rolling Updates

```bash
# Build new image
docker compose build gateway

# Start new container (old one still running)
docker compose up -d gateway

# Docker Compose automatically handles rolling restart
```

---

## Scaling & Performance

### Horizontal Scaling (Docker Compose)

```bash
# Scale the gateway to 3 replicas
docker-compose up -d --scale gateway=3

# Scale all Python services
docker-compose up -d --scale gateway=3 --scale risk-engine=3
```

### Vertical Scaling

Increase per-service resources in docker-compose.yml:

```yaml
services:
  gateway:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G
```

### Performance Tuning

**PostgreSQL:**
```bash
# Increase shared_buffers (25% of RAM, max 40GB)
docker compose exec postgres psql -U aztdp -d aztdp \
  -c "ALTER SYSTEM SET shared_buffers = '2GB';"

# Restart to apply
docker compose restart postgres
```

**Redis:**
```bash
# Monitor memory
docker compose exec redis redis-cli INFO memory

# Increase max memory
docker compose exec redis redis-cli CONFIG SET maxmemory 2gb

# Set eviction policy
docker compose exec redis redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

**Python Services:**
Add gunicorn workers in docker-compose.yml:
```yaml
environment:
  WORKERS=4  # Change from 1 to match CPU cores
```

### Load Testing

```bash
# Install locust
pip install locust==2.24.1

# Run load test
locust -f scripts/load/locustfile.py \
  --host http://localhost:8010 \
  --users 500 \
  --spawn-rate 50 \
  --run-time 10m \
  --headless
```

---

## Backup & Recovery

### Database Backups

**Manual backup:**
```bash
# Dump entire database
docker compose exec postgres pg_dump -U aztdp -d aztdp \
  -v > backup_$(date +%Y%m%d_%H%M%S).sql

# Compressed backup
docker compose exec postgres pg_dump -U aztdp -d aztdp \
  -F custom > backup_$(date +%Y%m%d_%H%M%S).dump
```

**Automated daily backup:**
```bash
# Create backup script
cat > scripts/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/backups/aztdp"
mkdir -p $BACKUP_DIR
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

docker compose exec postgres pg_dump -U aztdp -d aztdp \
  -F custom > $BACKUP_DIR/db_backup_$TIMESTAMP.dump

# Keep only last 30 days
find $BACKUP_DIR -name "db_backup_*.dump" -mtime +30 -delete
EOF

chmod +x scripts/backup.sh

# Schedule with cron (daily at 2 AM)
echo "0 2 * * * /path/to/AZTDP/scripts/backup.sh" | crontab -
```

### Redis Persistence

Redis is configured with AOF (append-only file) enabled:

```bash
# Check AOF status
docker compose exec redis redis-cli CONFIG GET appendonly

# Force AOF rewrite
docker compose exec redis redis-cli BGREWRITEAOF
```

### Recovery Procedures

**Restore PostgreSQL from backup:**
```bash
# Stop services
docker compose down

# Restore database
docker compose exec postgres psql -U aztdp -d aztdp < backup_20240115_100000.sql

# Start services
docker compose up -d
```

**Restore Redis:**
```bash
# Check AOF file
docker compose exec redis cat /data/appendonly.aof | tail -100

# Or restore from RDB dump
docker compose exec redis redis-cli SHUTDOWN
# Replace appendonly.aof in volume
docker compose up -d redis
```

---

## Monitoring & Alerting

### Metrics Collection

AZTDP exports Prometheus metrics on `GET /metrics`:

```bash
curl http://localhost:8000/metrics | head -20
```

Key metrics:
- `http_requests_total` — total requests by endpoint
- `http_request_duration_seconds` — response time histogram
- `risk_evaluations_total` — risk decisions by type
- `token_revocations_total` — revocations by reason

### Grafana Dashboards

**AZTDP Overview Dashboard:**
- Request rate and latency
- Risk decision distribution
- Policy decision outcomes
- Anomaly detection rate

**Access at:** http://localhost:3000 (admin/admin)

**Create custom dashboard:**
1. Click **+** → **New Dashboard**
2. Click **+ Add Panel**
3. Select data source: Prometheus
4. Write PromQL query
5. Save

### Alert Rules

Create alert rules in Prometheus:

```yaml
# prometheus-alerts.yml
groups:
  - name: aztdp
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        annotations:
          summary: "High error rate on {{ $labels.service }}"

      - alert: HighLatency
        expr: histogram_quantile(0.99, http_request_duration_seconds) > 1.0
        for: 5m
        annotations:
          summary: "High p99 latency: {{ $value }}s"

      - alert: AnomalyServiceDown
        expr: up{job="anomaly-service"} == 0
        for: 2m
        annotations:
          summary: "Anomaly service is down"
```

### Alert Notifications

Configure alert destinations in Prometheus:

```yaml
alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']
```

---

## Security Hardening

### Network Security

**Firewall rules (production):**
```bash
# Only expose public-facing services
# Block all services except reverse proxy

# Allow traffic from load balancer to services
sudo ufw allow from 10.0.0.0/8 to any port 8000  # Gateway
sudo ufw allow from 10.0.0.0/8 to any port 8080  # Keycloak

# Block direct database access
sudo ufw deny 5432
sudo ufw deny 6379
```

**Network segmentation:**
```yaml
# docker-compose.yml
networks:
  public:
    driver: bridge
  private:
    driver: bridge

services:
  gateway:
    networks:
      - public
      - private  # Can talk to internal services
  redis:
    networks:
      - private  # Only accessible from internal services
```

### Secret Management

**Don't use .env for production secrets.** Use:

1. **Kubernetes Secrets:**
```bash
kubectl create secret generic aztdp-secrets \
  --from-literal=postgres-password=$POSTGRES_PASSWORD \
  -n aztdp
```

2. **HashiCorp Vault:**
```bash
vault kv put secret/aztdp \
  postgres_password=$POSTGRES_PASSWORD \
  keycloak_admin_password=$KEYCLOAK_ADMIN_PASSWORD
```

3. **Docker Swarm Secrets:**
```bash
echo "$POSTGRES_PASSWORD" | docker secret create postgres_password -
```

### SSL/TLS

**Enable HTTPS on reverse proxy:**
```nginx
# nginx.conf
server {
  listen 443 ssl;
  ssl_certificate /etc/ssl/certs/aztdp.crt;
  ssl_certificate_key /etc/ssl/private/aztdp.key;

  location / {
    proxy_pass http://gateway:8080;
  }
}
```

### Access Control

**Restrict Grafana access:**
```bash
# Change default password
# Open http://localhost:3000
# Admin > Configuration > Users > admin > Change password
```

**Restrict Keycloak access:**
```bash
# Only allow access from reverse proxy
docker-compose exec keycloak \
  kcadm.sh update realms/aztdp -s sslRequired=EXTERNAL
```

### Audit Logging

Enable audit logging for all access:

```python
# In each service's config.py
AUDIT_LOG_ENABLED = True
AUDIT_LOG_LEVEL = "INFO"  # All requests
```

**Query audit logs:**
```sql
SELECT timestamp, user_id, action, resource, result
FROM audit_logs
WHERE created_at > NOW() - INTERVAL '24 hours'
ORDER BY created_at DESC;
```

---

## High Availability

### Redis Replication (Active-Passive)

```yaml
# docker-compose.yml
redis:
  image: redis:7.2-alpine
  command: redis-server /usr/local/etc/redis/redis.conf
  volumes:
    - ./infra/redis/redis.conf:/usr/local/etc/redis/redis.conf:ro

redis-replica:
  image: redis:7.2-alpine
  command: redis-server --slaveof redis 6379 --read-only yes
  depends_on:
    - redis
```

### PostgreSQL Replication

```yaml
# docker-compose.yml
postgres-primary:
  image: postgres:16-alpine
  environment:
    POSTGRES_REPLICATION_MODE: master
    POSTGRES_REPLICATION_USER: replicator
    POSTGRES_REPLICATION_PASSWORD: ${REPLICATION_PASSWORD}

postgres-replica:
  image: postgres:16-alpine
  environment:
    POSTGRES_REPLICATION_MODE: slave
    POSTGRES_MASTER_SERVICE: postgres-primary
```

### Multi-Region Setup

**Kubernetes with federation:**
```bash
# Deploy to multiple clusters
kubefed join cluster-us-west \
  --host-cluster-context=admin@us-west \
  --cluster-context=admin@us-west

kubefed join cluster-eu-west \
  --host-cluster-context=admin@eu-west \
  --cluster-context=admin@eu-west
```

**DNS failover:**
```bash
# Use weighted DNS records
# us-west.aztdp.com:  50% weight
# eu-west.aztdp.com:  50% weight
# Clients connect to aztdp.com (geolocation-based routing)
```

---

## Disaster Recovery Plan

### RTO/RPO Targets
- **RTO (Recovery Time Objective):** 5 minutes
- **RPO (Recovery Point Objective):** 1 minute

### Disaster Scenarios

**Scenario 1: Single Service Fails**
1. Health check detects failure
2. Orchestrator (Docker/K8s) restarts service
3. Service reconnects to shared resources
- Recovery time: 30 seconds

**Scenario 2: Database Corruption**
1. Switch to read-only mode
2. Restore from hourly backup
3. Replay transaction log
- Recovery time: 5 minutes

**Scenario 3: Region Outage**
1. DNS failover to standby region
2. Activate replica as primary
3. Verify data consistency
- Recovery time: 30-60 seconds

---

## Maintenance Windows

**Recommended schedule:**
- **OS patches:** Monthly (2nd Sunday, 2-3 AM UTC)
- **Docker updates:** Quarterly (1st Monday, 2-3 AM UTC)
- **Database maintenance:** Weekly (Sunday, 1-2 AM UTC)

**During maintenance:**
1. Notify users of downtime
2. Drain connections (set max_connections = 1)
3. Stop services gracefully
4. Apply updates
5. Run smoke tests
6. Resume service

```bash
# Graceful drain
docker compose down

# Apply updates
git pull
docker compose build --no-cache

# Resume
docker compose up -d

# Verify
bash scripts/validate_platform.sh
```

---

## Support & Troubleshooting

See [docs/runbooks/QUICK_START_GUIDE.md § Troubleshooting](QUICK_START_GUIDE.md#10-troubleshooting) for common issues and solutions.

For incident response procedures, see [docs/runbooks/INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md).
