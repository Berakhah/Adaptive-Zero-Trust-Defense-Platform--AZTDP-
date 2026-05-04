# Windows Setup - Complete Summary

Comprehensive Windows 10/11 support has been added to AZTDP documentation.

---

## 📦 What's New for Windows Users

### 1. **WINDOWS_SETUP_GUIDE.md** (30 KB)
Complete Windows-specific setup guide covering:
- Prerequisites for Windows 10/11
- Docker Desktop installation & configuration
- WSL2 setup (recommended)
- Environment configuration for Windows
- Starting the platform
- Windows-specific commands (PowerShell)
- Troubleshooting Windows issues
- Windows best practices

**Location:** [WINDOWS_SETUP_GUIDE.md](WINDOWS_SETUP_GUIDE.md)

### 2. **scripts/validate_platform.ps1** (PowerShell)
Windows-native validation script (no bash required)

**Run:**
```powershell
powershell -ExecutionPolicy Bypass -File scripts/validate_platform.ps1
```

### 3. Updated Guides
- [GETTING_STARTED.md](GETTING_STARTED.md) — Now links to Windows guide
- [GUIDE_INDEX.md](GUIDE_INDEX.md) — Windows section added

---

## 🚀 Windows Quick Start (5 Minutes)

```powershell
# 1. Install Docker Desktop (from https://www.docker.com/products/docker-desktop)
# 2. Enable WSL2 (Run as Administrator):
wsl --install

# 3. Restart computer, then:
cd "D:\Project\Adaptive Zero-Trust Defense Platform (AZTDP)"

# 4. Create .env file:
Copy-Item .env.example -Destination .env
notepad .env  # Set strong passwords

# 5. Start platform:
docker compose up -d --build

# 6. Wait 2-5 minutes, then validate:
powershell -ExecutionPolicy Bypass -File scripts/validate_platform.ps1

# 7. Open Grafana:
Start-Process http://localhost:3000
```

---

## 📋 What's Covered

### Prerequisites
- ✅ Windows version check (10/11 v2004+)
- ✅ System requirements (8GB RAM, 10GB disk)
- ✅ Virtualization enable in BIOS
- ✅ Administrator access

### Installation
- ✅ Docker Desktop for Windows
- ✅ WSL2 setup (automatic and manual)
- ✅ File encoding (UTF-8)
- ✅ Line endings (LF vs CRLF)

### Configuration
- ✅ Environment file (.env) setup
- ✅ Strong password generation
- ✅ Docker Desktop resource allocation
- ✅ WSL2 integration

### Operations
- ✅ PowerShell commands (native Windows shell)
- ✅ Service startup and status
- ✅ Log viewing
- ✅ Dashboard access
- ✅ Request examples in PowerShell

### Troubleshooting (10+ scenarios)
- ✅ Docker won't start
- ✅ WSL2 issues
- ✅ Network problems
- ✅ Port conflicts
- ✅ Database issues
- ✅ Redis connectivity
- ✅ Permission errors
- ✅ Script execution issues
- ✅ Docker volume syncing
- ✅ And more...

---

## 🔧 Key Windows Commands

### Navigation
```powershell
cd "D:\Project\Adaptive Zero-Trust Defense Platform (AZTDP)"
```

### Setup
```powershell
Copy-Item .env.example -Destination .env
notepad .env
```

### Startup
```powershell
docker compose up -d --build
docker compose ps
docker compose logs -f
```

### Get Token
```powershell
$token = curl.exe -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token `
  -d grant_type=password -d client_id=aztdp-client -d client_secret=aztdp-secret `
  -d username=user1 -d password=password | jq -r .access_token
```

### Make Request
```powershell
curl.exe -H "Authorization: Bearer $token" `
  -H "X-Client-Ip: 203.0.113.10" `
  -H "X-Geo: US-CA" `
  http://localhost:8010/v1/payments/123
```

### Validate
```powershell
powershell -ExecutionPolicy Bypass -File scripts/validate_platform.ps1
```

### Dashboard
```powershell
Start-Process http://localhost:3000   # Grafana
Start-Process http://localhost:8080   # Keycloak
Start-Process http://localhost:9090   # Prometheus
```

### Stop
```powershell
docker compose down
docker compose down -v  # Full reset
```

---

## 📖 Documentation Structure

```
AZTDP/
├── WINDOWS_SETUP_GUIDE.md         ← START HERE FOR WINDOWS
├── GETTING_STARTED.md             (Now with Windows link)
├── GUIDE_INDEX.md                 (Updated with Windows section)
├── PLATFORM_VERIFICATION_CHECKLIST.md
├── scripts/
│   ├── startup.sh                (Mac/Linux)
│   ├── validate_platform.sh       (Mac/Linux)
│   └── validate_platform.ps1      ← NEW! Windows PowerShell
├── docs/runbooks/
│   ├── QUICK_START_GUIDE.md       (Detailed guide)
│   ├── OPERATIONS_MANUAL.md       (Production)
│   └── README.md
└── ...
```

---

## ✅ Features for Windows Users

| Feature | Details |
|---------|---------|
| **PowerShell Support** | Native Windows shell, no bash required |
| **Docker Desktop** | Full setup guide with resource config |
| **WSL2 Setup** | Automatic and manual options |
| **Validation Script** | `validate_platform.ps1` for Windows |
| **Command Examples** | PowerShell syntax throughout |
| **Troubleshooting** | 10+ Windows-specific scenarios |
| **File Path Handling** | Backslash vs forward slash guidance |
| **Encoding Help** | UTF-8 vs UTF-16 LE guidance |
| **Tool Installation** | Git, jq, Python setup on Windows |
| **Port Conflict** | Resolution steps for Windows |

---

## 🎯 Next Steps

### For Windows Users

1. **Read:** [WINDOWS_SETUP_GUIDE.md](WINDOWS_SETUP_GUIDE.md)
2. **Install:** Docker Desktop & enable WSL2
3. **Setup:** Create .env file with strong passwords
4. **Start:** `docker compose up -d --build`
5. **Validate:** `powershell -ExecutionPolicy Bypass -File scripts/validate_platform.ps1`
6. **Explore:** Open Grafana at http://localhost:3000

### For Mac/Linux Users

1. **Read:** [GETTING_STARTED.md](GETTING_STARTED.md)
2. **Run:** `bash scripts/startup.sh`
3. **Validate:** `bash scripts/validate_platform.sh`
4. **Continue:** Same as Windows users from step 5

---

## 📊 Total Documentation

- **Top-level guides:** 4 files (160+ KB)
- **Operational guides:** 3 files (37 KB)
- **Scripts:** 3 files (bash + PowerShell)
- **Total pages:** 160+
- **Total words:** 50,000+

**Windows-specific additions:**
- 1 comprehensive setup guide (30 KB)
- 1 PowerShell validation script (6 KB)
- Updates to main guides (cross-references)

---

## 🆘 Support

**Windows Setup Issues?**
→ See [WINDOWS_SETUP_GUIDE.md § 8. Troubleshooting on Windows](WINDOWS_SETUP_GUIDE.md#8-troubleshooting-on-windows)

**Docker Issues?**
→ See [WINDOWS_SETUP_GUIDE.md § Docker Desktop Issues](WINDOWS_SETUP_GUIDE.md#docker-desktop-issues)

**PowerShell Help?**
→ See [WINDOWS_SETUP_GUIDE.md § 11. Windows PowerShell Script](WINDOWS_SETUP_GUIDE.md#11-windows-powershell-script-for-validation)

**General Help?**
→ See [QUICK_START_GUIDE.md § 10. Troubleshooting](docs/runbooks/QUICK_START_GUIDE.md#10-troubleshooting)

---

## ✨ Key Differences (Windows vs Mac/Linux)

| Task | Windows | Mac/Linux |
|------|---------|-----------|
| **Shell** | PowerShell (native) | bash (native) |
| **Startup Script** | `validate_platform.ps1` | `startup.sh` |
| **Validation** | PowerShell script | bash script |
| **File Paths** | `D:\Project\...` or `D:/Project/...` | `/path/to/aztdp` |
| **Encoding** | UTF-8 (not UTF-16) | UTF-8 |
| **Line Endings** | LF (not CRLF) | LF |
| **Docker** | Docker Desktop (GUI) | Docker Desktop or CLI |
| **Terminal** | Windows Terminal (recommended) | Terminal (built-in) |

---

All Windows users should start with [WINDOWS_SETUP_GUIDE.md](WINDOWS_SETUP_GUIDE.md).

Happy securing on Windows! 🔒
