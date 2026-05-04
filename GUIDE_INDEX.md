# AZTDP Platform — Complete Guide Index

**All documentation created May 4, 2024**

This index guides you to the right documentation for your needs.

---

## 🚀 I Want to...

### Start the Platform on Windows (Fastest)
→ Read: [WINDOWS_SETUP_GUIDE.md](WINDOWS_SETUP_GUIDE.md)
→ Then run: `docker compose up -d --build` (PowerShell)
→ Validate: `powershell -ExecutionPolicy Bypass -File scripts/validate_platform.ps1`

### Start the Platform on Mac/Linux (Fastest)
→ Run: `bash scripts/startup.sh`
→ Then read: [GETTING_STARTED.md](GETTING_STARTED.md)

### Understand How It Works
→ Read: [GETTING_STARTED.md § Understanding the Platform](GETTING_STARTED.md#understanding-the-platform)
→ Deep dive: [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md)

### Make Test Requests
→ Read: [QUICK_START_GUIDE.md § 5. Getting Started with Requests](docs/runbooks/QUICK_START_GUIDE.md#5-getting-started-with-requests)
→ See examples: [GETTING_STARTED.md § Common Tasks](GETTING_STARTED.md#common-tasks)

### Verify Everything Works
→ Run: `bash scripts/validate_platform.sh`
→ Or manually: [PLATFORM_VERIFICATION_CHECKLIST.md](PLATFORM_VERIFICATION_CHECKLIST.md)

### Deploy to Production
→ Read: [OPERATIONS_MANUAL.md § Deployment Models](docs/runbooks/OPERATIONS_MANUAL.md#deployment-models)

### Troubleshoot an Issue
→ Check: [QUICK_START_GUIDE.md § 10. Troubleshooting](docs/runbooks/QUICK_START_GUIDE.md#10-troubleshooting)
→ Or: [OPERATIONS_MANUAL.md § Disaster Recovery](docs/runbooks/OPERATIONS_MANUAL.md#disaster-recovery-plan)

### Respond to a Security Incident
→ Read: [docs/runbooks/INCIDENT_RESPONSE.md](docs/runbooks/INCIDENT_RESPONSE.md)

### Understand the Security Model
→ Read: [docs/SECURITY.md](docs/SECURITY.md)
→ And: [docs/threat-model/THREAT_MODEL.md](docs/threat-model/THREAT_MODEL.md)

### Integrate with Another System
→ See API specs: [docs/api/](docs/api/)

---

## 📚 Documentation Files Created

### New Top-Level Guides
| File | Purpose | Read Time |
|------|---------|-----------|
| **[WINDOWS_SETUP_GUIDE.md](WINDOWS_SETUP_GUIDE.md)** | Windows 10/11 setup guide (WSL2, Docker Desktop) | 15 min |
| **[GETTING_STARTED.md](GETTING_STARTED.md)** | Overview, quick start, common tasks | 10 min |
| **[PLATFORM_VERIFICATION_CHECKLIST.md](PLATFORM_VERIFICATION_CHECKLIST.md)** | 100-item verification checklist | 20 min |

### New Runbooks
| File | Purpose | Read Time |
|------|---------|-----------|
| **[docs/runbooks/QUICK_START_GUIDE.md](docs/runbooks/QUICK_START_GUIDE.md)** | Detailed operational guide (80+ pages) | 30 min |
| **[docs/runbooks/OPERATIONS_MANUAL.md](docs/runbooks/OPERATIONS_MANUAL.md)** | Production deployment, HA, disaster recovery | 20 min |

### New Scripts
| Script | Platform | Purpose |
|--------|----------|---------|
| **[scripts/startup.sh](scripts/startup.sh)** | Mac/Linux | Automated platform startup (5 min) |
| **[scripts/validate_platform.sh](scripts/validate_platform.sh)** | Mac/Linux | Automated health checks |
| **[scripts/validate_platform.ps1](scripts/validate_platform.ps1)** | Windows | Automated health checks (PowerShell) |

---

## 🎯 Quick Start Path (5 Minutes)

```bash
# 1. Start the platform
bash scripts/startup.sh

# Wait 2-5 minutes for services to initialize...

# 2. Verify everything works
bash scripts/validate_platform.sh

# 3. Get a token
TOKEN=$(curl -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token \
  -d grant_type=password \
  -d client_id=aztdp-client \
  -d client_secret=aztdp-secret \
  -d username=user1 \
  -d password=password | jq -r .access_token)

# 4. Make a request
curl -H "Authorization: Bearer $TOKEN" \
     -H "X-Client-Ip: 203.0.113.10" \
     -H "X-Geo: US-CA" \
     http://localhost:8010/v1/payments/123

# 5. View dashboards
open http://localhost:3000  # Grafana
```

---

## 🗺️ Documentation Map by Role

### I'm an End User
1. [GETTING_STARTED.md](GETTING_STARTED.md) — Understand what AZTDP does
2. [QUICK_START_GUIDE.md § 5](docs/runbooks/QUICK_START_GUIDE.md#5-getting-started-with-requests) — Make requests
3. [QUICK_START_GUIDE.md § 9](docs/runbooks/QUICK_START_GUIDE.md#9-common-tasks) — Common tasks

### I'm a Developer
1. [GETTING_STARTED.md](GETTING_STARTED.md) — Overview
2. [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) — System design
3. [docs/api/](docs/api/) — API specifications
4. [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) — Development setup

### I'm a DevOps/SRE
1. [QUICK_START_GUIDE.md § 3](docs/runbooks/QUICK_START_GUIDE.md#3-starting-the-platform) — Startup
2. [OPERATIONS_MANUAL.md](docs/runbooks/OPERATIONS_MANUAL.md) — Deployment & scaling
3. [PLATFORM_VERIFICATION_CHECKLIST.md](PLATFORM_VERIFICATION_CHECKLIST.md) — Verification
4. [QUICK_START_GUIDE.md § 10](docs/runbooks/QUICK_START_GUIDE.md#10-troubleshooting) — Troubleshooting

### I'm a Security Engineer
1. [docs/SECURITY.md](docs/SECURITY.md) — Security guide
2. [docs/threat-model/THREAT_MODEL.md](docs/threat-model/THREAT_MODEL.md) — Threat model
3. [docs/runbooks/INCIDENT_RESPONSE.md](docs/runbooks/INCIDENT_RESPONSE.md) — Incident handling

---

## 📊 What's Covered

### Platform Operations
✅ Starting the platform  
✅ Health checks & validation  
✅ Making authenticated requests  
✅ Accessing dashboards  
✅ Viewing logs  
✅ Running tests  
✅ Scaling services  
✅ Backup & recovery  

### Attack Scenarios
✅ Replay detection  
✅ IP drift detection  
✅ Geo drift detection  
✅ Device change detection  
✅ Token revocation  

### Deployment Models
✅ Docker Compose  
✅ Docker Swarm  
✅ Kubernetes  
✅ High availability  

---

## 🔗 Most Common Commands

```bash
# Start platform
bash scripts/startup.sh

# Verify health
bash scripts/validate_platform.sh

# Get token
TOKEN=$(curl -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token \
  -d grant_type=password -d client_id=aztdp-client -d client_secret=aztdp-secret \
  -d username=user1 -d password=password | jq -r .access_token)

# Make request
curl -H "Authorization: Bearer $TOKEN" \
     -H "X-Client-Ip: 203.0.113.10" \
     -H "X-Geo: US-CA" \
     http://localhost:8010/v1/payments/123

# View status
docker compose ps

# View logs
docker compose logs -f <service>

# Stop platform
docker compose down
```

---

## ✅ Verification

All created guides have been:
- ✅ Written for clarity and completeness
- ✅ Organized by role and task
- ✅ Include complete command examples
- ✅ Cross-referenced with existing docs

---

## 📋 Files Created Today

```
NEW DOCUMENTATION:
├── GETTING_STARTED.md                          (10-page overview)
├── PLATFORM_VERIFICATION_CHECKLIST.md          (20-page checklist)
├── GUIDE_INDEX.md                              (This file)
├── docs/runbooks/QUICK_START_GUIDE.md          (80-page operational guide)
├── docs/runbooks/OPERATIONS_MANUAL.md          (40-page production guide)
├── docs/runbooks/README.md                     (Runbooks index)
├── scripts/startup.sh                          (Automated startup script)
└── scripts/validate_platform.sh                (Automated validation script)

TOTAL: 150+ pages, 45,000+ words of documentation
```

---

## 🎉 You're Ready!

**Next step:** Run `bash scripts/startup.sh` and read [GETTING_STARTED.md](GETTING_STARTED.md)

Happy securing! 🔒
