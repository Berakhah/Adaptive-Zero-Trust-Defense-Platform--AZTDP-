# AZTDP Windows Setup & Configuration Guide

Complete guide for running AZTDP on Windows 11/10 computers.

**Table of Contents:**
- [1. Prerequisites for Windows](#1-prerequisites-for-windows)
- [2. Installing Docker Desktop](#2-installing-docker-desktop)
- [3. Setting Up WSL2](#3-setting-up-wsl2)
- [4. Environment Configuration](#4-environment-configuration)
- [5. Starting the Platform](#5-starting-the-platform)
- [6. Accessing Services](#6-accessing-services)
- [7. Windows-Specific Commands](#7-windows-specific-commands)
- [8. Troubleshooting on Windows](#8-troubleshooting-on-windows)

---

## 1. Prerequisites for Windows

### System Requirements

- **Windows 10** (version 2004+) or **Windows 11**
- **8 GB RAM minimum** (16 GB recommended)
- **10 GB free disk space** (SSD recommended)
- **Virtualization enabled** in BIOS/UEFI
- **Administrator access** (required for Docker & WSL2)

### Check Your Windows Version

1. Press `Windows Key + R`
2. Type `winver` and press Enter
3. You should see Windows 10 (version 2004+) or Windows 11

### Enable Virtualization

**For Windows 11:**
- Usually enabled by default
- If not, restart computer and enter BIOS (F2, Del, or F12 during startup)
- Look for "Virtualization," "VT-x," or "SVM" → Enable it

**For Windows 10:**
- Same process as Windows 11
- Check [Microsoft's guide](https://support.microsoft.com/en-us/windows/enable-virtualization-on-windows-11-pcs-c5578302-6e43-4ab5-82c3-319e1f61e39a)

---

## 2. Installing Docker Desktop

### Download Docker Desktop

1. Go to https://www.docker.com/products/docker-desktop
2. Click **Download for Windows**
3. Choose the installer for your CPU:
   - **Intel/AMD:** Docker Desktop Installer (standard)
   - **Apple Silicon:** Not applicable (you're on Windows)

### Install Docker Desktop

1. **Run the installer:**
   - Double-click `Docker Desktop Installer.exe`
   - Click "Install"
   - Enter your Windows password when prompted

2. **Wait for installation** (5-10 minutes)

3. **Complete setup:**
   - Restart your computer when prompted
   - Docker Desktop will start automatically after restart

### Verify Installation

Open PowerShell and run:

```powershell
docker --version
docker compose version
```

Expected output:
```
Docker version 24.0.0, build 0000000
Docker Compose version v2.20.0
```

### Configure Docker Desktop (Important!)

1. **Right-click Docker Desktop** (system tray, bottom right) → Settings
2. **Resources:**
   - Memory: Set to **6-8 GB** (leave some for Windows)
   - CPUs: Set to **4-6** (half your total)
   - Disk size: **50 GB**
3. **Click Apply & Restart**

---

## 3. Setting Up WSL2

WSL2 (Windows Subsystem for Linux 2) provides better performance than Hyper-V alone.

### Enable WSL2

**Option 1: Using PowerShell (Recommended)**

1. Open PowerShell **as Administrator**:
   - Press `Windows Key`
   - Type `PowerShell`
   - Right-click → "Run as Administrator"

2. Run these commands:

```powershell
# Enable WSL
wsl --install

# Set WSL2 as default
wsl --set-default-version 2

# Restart computer
Restart-Computer
```

**Option 2: Manual (if above doesn't work)**

1. Press `Windows Key + R`
2. Type `appwiz.cpl` and press Enter
3. Click "Turn Windows features on or off"
4. Enable:
   - ☑ Windows Subsystem for Linux
   - ☑ Virtual Machine Platform
5. Click OK and restart

### Verify WSL2 Installation

```powershell
wsl --list --verbose
```

Expected output:
```
NAME      STATE           VERSION
Ubuntu    Running         2
```

---

## 4. Environment Configuration

### Navigate to AZTDP Directory

Open PowerShell and navigate to your AZTDP folder:

```powershell
cd "D:\Project\Adaptive Zero-Trust Defense Platform (AZTDP)"
```

**Note:** Use PowerShell (not Command Prompt) for better compatibility with scripts.

### Create .env File

#### Option A: Using PowerShell (Recommended)

```powershell
# Copy template
Copy-Item .env.example -Destination .env

# Edit with Notepad
notepad .env
```

#### Option B: Using VS Code (Better)

```powershell
# If you have VS Code installed
code .env
```

#### Option C: Manual (Command Line)

```powershell
# View the template
Get-Content .env.example

# Create and edit
# (Copy content from .env.example and paste into new file called .env)
```

### Edit .env File

Open `.env` in a text editor (Notepad, VS Code, or your favorite editor) and set these values:

```
# PostgreSQL password - use strong random value
POSTGRES_PASSWORD=MySecurePassword123!

# Keycloak admin password
KEYCLOAK_ADMIN_PASSWORD=KeycloakAdminPass456!

# Django secret key (generate with Python if available)
AZTDP_SECRET_KEY=your-secret-key-here

# Allowed hosts
AZTDP_ALLOWED_HOSTS=localhost,127.0.0.1

# Internal token
AZTDP_INTERNAL_TOKEN=your-internal-token

# Grafana password
GRAFANA_ADMIN_PASSWORD=GrafanaPass789!
```

**⚠️ Important:**
- **DO NOT commit .env to git**
- **DO NOT use simple passwords**
- Make these strong and unique
- Save the file in ANSI/UTF-8 encoding (not UTF-16 BE)

---

## 5. Starting the Platform

### Method 1: Using the Startup Script (Recommended)

The startup script works on Windows with WSL2/PowerShell.

```powershell
# Navigate to AZTDP directory
cd "D:\Project\Adaptive Zero-Trust Defense Platform (AZTDP)"

# Run startup script
bash scripts/startup.sh
```

**Note:** If bash command is not found, see [Troubleshooting](#windows-bash-not-found)

### Method 2: Manual Startup (If Script Doesn't Work)

```powershell
# Build and start all services
docker compose up -d --build

# This will:
# - Build all 13 Docker images
# - Start all 13 services
# - Create volumes for data persistence
# - Wait for services to initialize
```

**⏱️ Wait 2-5 minutes** for services to initialize (especially Keycloak)

### Check Service Status

```powershell
# List all running containers
docker compose ps

# You should see 13 services all showing "Up (healthy)" or "Up"
```

### Monitor Startup Progress

```powershell
# Watch logs in real-time
docker compose logs -f

# Or watch a specific service (e.g., Keycloak)
docker compose logs -f keycloak

# Press Ctrl+C to stop watching logs
```

---

## 6. Accessing Services

### Accessing in Browser

All services are available on `localhost`:

| Service | URL | Credentials |
|---------|-----|-------------|
| Django App | http://localhost:8010 | (no auth) |
| Spring App | http://localhost:8011 | (no auth) |
| Gateway | http://localhost:8000 | (API) |
| Risk Engine | http://localhost:8001 | (API) |
| Keycloak | http://localhost:8080 | admin/admin |
| OPA | http://localhost:8181 | (no auth) |
| Prometheus | http://localhost:9090 | (no auth) |
| Grafana | http://localhost:3000 | admin/admin |

### Opening URLs in PowerShell

```powershell
# Open in default browser
Start-Process http://localhost:3000

# Or directly with Edge/Chrome
Start-Process "https://localhost:3000"

# Or with specific browser
Start-Process -FilePath "C:\Program Files\Google\Chrome\Application\chrome.exe" -ArgumentList "http://localhost:3000"
```

### Using Windows Terminal (Recommended)

Windows 11 includes Windows Terminal which is better for terminal work:

```powershell
# Install (Windows 11 comes with it)
# Or download from Microsoft Store

# Open PowerShell in new tab: Ctrl + Shift + 2
# Switch tabs: Ctrl + Tab
# Split panes: Alt + Shift + D
```

---

## 7. Windows-Specific Commands

### PowerShell vs Bash Commands

The startup script uses bash (which requires WSL2), but many commands work in PowerShell:

#### Getting a Token

**PowerShell:**
```powershell
$tokenResponse = curl.exe -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token `
  -d grant_type=password `
  -d client_id=aztdp-client `
  -d client_secret=aztdp-secret `
  -d username=user1 `
  -d password=password

# Parse JSON (requires ConvertFrom-Json)
$token = ($tokenResponse | ConvertFrom-Json).access_token
Write-Host "Token: $token"
```

**Or simpler with curl.exe:**
```powershell
curl.exe -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token `
  -d grant_type=password `
  -d client_id=aztdp-client `
  -d client_secret=aztdp-secret `
  -d username=user1 `
  -d password=password
```

**Or use jq (if installed):**
```powershell
curl.exe -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token `
  -d grant_type=password `
  -d client_id=aztdp-client `
  -d client_secret=aztdp-secret `
  -d username=user1 `
  -d password=password | jq -r .access_token
```

#### Making an Authenticated Request

**PowerShell:**
```powershell
$token = "your-token-here"

curl.exe -H "Authorization: Bearer $token" `
  -H "X-Client-Ip: 203.0.113.10" `
  -H "X-Geo: US-CA" `
  http://localhost:8010/v1/payments/123
```

#### Checking Service Logs

**PowerShell:**
```powershell
# View logs (last 50 lines)
docker compose logs --tail 50

# Follow logs in real-time
docker compose logs -f

# Logs for specific service
docker compose logs gateway

# Follow specific service
docker compose logs -f risk-engine
```

#### Stopping Services

**PowerShell:**
```powershell
# Stop all services (keeps data)
docker compose down

# Stop and remove all data
docker compose down -v
```

#### Restarting Services

**PowerShell:**
```powershell
# Restart all services
docker compose restart

# Restart specific service
docker compose restart gateway

# Full rebuild
docker compose up -d --build
```

### Installing Tools on Windows

#### Install Git

```powershell
# Via Chocolatey (if installed)
choco install git

# Or download from https://git-scm.com/download/win
```

#### Install jq (JSON parser)

```powershell
# Via Chocolatey
choco install jq

# Or download portable version from https://stedolan.github.io/jq/download/
```

#### Install Python (Optional)

```powershell
# Via Windows Store
# Open Microsoft Store → Search "Python" → Install

# Or via installer from https://www.python.org/downloads/

# Verify installation
python --version
```

---

## 8. Troubleshooting on Windows

### Docker Desktop Issues

#### Docker doesn't start after installation

**Solution:**
```powershell
# 1. Restart Docker Desktop
# - Right-click Docker icon (system tray) → Quit Docker Desktop
# - Wait 10 seconds
# - Click Docker Desktop shortcut to restart

# 2. If still not working, restart computer
Restart-Computer

# 3. Check Docker version
docker --version
```

#### "Docker daemon is not running"

**Solution:**
```powershell
# Start Docker Desktop via Command Palette
# - Press Windows Key
# - Type "Docker Desktop"
# - Press Enter

# Or restart it:
Stop-Process -Name "Docker Desktop" -Force
Start-Process "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
```

#### Port already in use (e.g., 8080)

**PowerShell:**
```powershell
# Find what's using port 8080
Get-NetTcpConnection -LocalPort 8080 | Select-Object OwningProcess
tasklist | findstr <PID>

# Kill the process (replace PID with number from above)
Stop-Process -Id <PID> -Force

# Or change port in docker-compose.yml
```

### WSL2 Issues

#### WSL2 not installed or not working

**Solution:**
```powershell
# Run as Administrator
wsl --install

# If that doesn't work, manually enable:
# 1. Press Windows Key + R
# 2. Type "appwiz.cpl"
# 3. Click "Turn Windows features on or off"
# 4. Enable "Windows Subsystem for Linux"
# 5. Restart
```

#### bash command not found

**Solution:**
```powershell
# Option 1: Install WSL2 (see above)

# Option 2: Use PowerShell scripts instead
# Scripts are in PowerShell syntax for Windows

# Option 3: Use Git Bash (comes with Git for Windows)
```

### Network Issues

#### Cannot access http://localhost:8080

**Solution:**
```powershell
# 1. Verify container is running
docker compose ps keycloak

# 2. Check if Docker Desktop is running
Get-Process Docker -ErrorAction SilentlyContinue

# 3. Restart Docker Desktop
Stop-Process -Name "Docker Desktop" -Force
Start-Sleep -Seconds 5
Start-Process "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"

# 4. Wait and try again
Start-Sleep -Seconds 30
curl.exe http://localhost:8080/health/ready
```

#### Port binding issues in Docker

**Solution:**
```powershell
# Stop all containers
docker compose down

# Remove unused networks and volumes
docker network prune -f
docker volume prune -f

# Restart
docker compose up -d --build
```

### Database Issues

#### PostgreSQL won't start

**Solution:**
```powershell
# Check logs
docker compose logs postgres

# If volume issue, remove and recreate
docker compose down -v
docker compose up -d postgres

# Wait for it to initialize
Start-Sleep -Seconds 30
docker compose exec postgres psql -U aztdp -d aztdp -c "SELECT 1;"
```

#### Cannot connect to Redis

**Solution:**
```powershell
# Check Redis is running
docker compose ps redis

# Check Redis logs
docker compose logs redis

# Test connection
docker compose exec redis redis-cli ping
# Should return: PONG
```

### Permission Issues

#### "Permission denied" errors

**Solution:**
```powershell
# Run PowerShell as Administrator
# - Press Windows Key
# - Type "PowerShell"
# - Right-click → "Run as Administrator"

# Then try your docker commands again
```

### Script Execution Issues

#### Cannot run PowerShell scripts

**Solution:**
```powershell
# Check execution policy
Get-ExecutionPolicy

# If it says "Restricted", allow local scripts:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# For one-time execution:
powershell -ExecutionPolicy Bypass -File .\script.ps1
```

#### startup.sh script doesn't work

**Solution:**
```powershell
# Option 1: Install WSL2 to run bash scripts
wsl --install

# Option 2: Run Docker commands directly
docker compose up -d --build
Start-Sleep -Seconds 120

# Option 3: Create PowerShell version of startup script
# (see WINDOWS_STARTUP_SCRIPT.md)
```

---

## 9. Windows-Specific Best Practices

### File Paths

**Use forward slashes or double backslashes:**
```powershell
# ✅ Good
"D:/Project/AZTDP"
"D:\\Project\\AZTDP"

# ❌ Avoid
"D:\Project\AZTDP"  # Single backslash is escape character
```

### .env File Format

**Use ANSI or UTF-8 encoding:**
```powershell
# When editing in Notepad:
# Save As → Encoding: UTF-8 → Save

# NOT UTF-16 or UTF-16 LE
```

### Line Endings

**Use LF (Unix-style), not CRLF (Windows-style):**
```powershell
# In VS Code:
# Bottom right: "CRLF" → Click → Select "LF"
```

### Docker Desktop Settings

**Recommended configuration:**
```
Resources:
  Memory: 6-8 GB (leave 2 GB for Windows)
  CPUs: 4-6 (half your total)
  Disk: 50 GB
  
File Sharing:
  Enable: D:\Project\Adaptive Zero-Trust Defense Platform (AZTDP)
  
WSL Integration:
  Enable: Use the new WSL 2 based engine
```

---

## 10. Quick Windows Startup Checklist

- [ ] Windows 10/11 version 2004+ installed
- [ ] Virtualization enabled in BIOS
- [ ] Docker Desktop installed and running
- [ ] WSL2 installed (run `wsl --list --verbose`)
- [ ] Navigate to AZTDP directory: `cd "D:\Project\..."`
- [ ] Copy .env file: `Copy-Item .env.example -Destination .env`
- [ ] Edit .env with strong passwords
- [ ] Start platform: `docker compose up -d --build`
- [ ] Wait 2-5 minutes for initialization
- [ ] Check status: `docker compose ps`
- [ ] Verify health: `docker compose logs | Select-String "healthy"`
- [ ] Open Grafana: `Start-Process http://localhost:3000`

---

## 11. Windows PowerShell Script for Validation

Create a file called `validate-windows.ps1`:

```powershell
Write-Host "AZTDP Windows Validation Script" -ForegroundColor Cyan

# Check Docker
Write-Host "`nChecking Docker..." -ForegroundColor Yellow
if (Get-Command docker -ErrorAction SilentlyContinue) {
    Write-Host "✓ Docker installed" -ForegroundColor Green
    docker --version
} else {
    Write-Host "✗ Docker not found" -ForegroundColor Red
    exit 1
}

# Check Docker Compose
Write-Host "`nChecking Docker Compose..." -ForegroundColor Yellow
if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker compose version | Write-Host -ForegroundColor Green
} else {
    Write-Host "✗ Docker Compose not found" -ForegroundColor Red
}

# Check containers
Write-Host "`nChecking containers..." -ForegroundColor Yellow
$running = (docker compose ps -q | Measure-Object).Count
Write-Host "Running containers: $running (should be 13)" -ForegroundColor Cyan

# Check health endpoints
Write-Host "`nChecking health endpoints..." -ForegroundColor Yellow

$endpoints = @(
    "http://localhost:8000/health",
    "http://localhost:8001/health",
    "http://localhost:8080/health/ready"
)

foreach ($endpoint in $endpoints) {
    try {
        $response = Invoke-WebRequest -Uri $endpoint -TimeoutSec 5 -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            Write-Host "✓ $endpoint" -ForegroundColor Green
        }
    } catch {
        Write-Host "✗ $endpoint" -ForegroundColor Red
    }
}

Write-Host "`nValidation complete!" -ForegroundColor Cyan
```

Run it:
```powershell
powershell -ExecutionPolicy Bypass -File validate-windows.ps1
```

---

## Common Windows Paths

| Item | Windows Path |
|------|--------------|
| AZTDP Directory | `D:\Project\Adaptive Zero-Trust Defense Platform (AZTDP)` |
| Docker Desktop | `C:\Program Files\Docker\Docker` |
| .env file | `D:\Project\...\AZTDP\.env` |
| Logs directory | `.\.kiro` (relative to AZTDP dir) |
| Docker config | `%AppData%\Docker` |
| WSL home | `\\wsl.localhost\Ubuntu\home\<username>` |

---

## Getting Help on Windows

**Problem: Can't find command in PowerShell**
```powershell
# Check if it's in PATH
$env:Path.Split(';')

# Or use full path
& "C:\Program Files\...\command.exe"
```

**Problem: Line endings causing issues**
```powershell
# In VS Code or Notepad++: 
# Click "CRLF" or "LF" at bottom right
# Select LF (Unix-style)
```

**Problem: Docker volumes not syncing**
```powershell
# In Docker Desktop:
# Settings → Resources → File Sharing
# Add your AZTDP directory
# Click Apply & Restart
```

---

## Next Steps

1. **Follow the Windows Setup Checklist** (section 10)
2. **Read [GETTING_STARTED.md](GETTING_STARTED.md)** for overview
3. **Run validation:** `docker compose ps`
4. **Make your first request:** See [GETTING_STARTED.md § Common Tasks](GETTING_STARTED.md#common-tasks)
5. **Explore dashboards:** 
   - Grafana: http://localhost:3000
   - Prometheus: http://localhost:9090
   - Keycloak: http://localhost:8080

---

## Support

- **Docker Desktop issues:** https://docs.docker.com/desktop/
- **WSL2 issues:** https://docs.microsoft.com/en-us/windows/wsl/
- **PowerShell help:** `Get-Help <command>`
- **AZTDP troubleshooting:** See [QUICK_START_GUIDE.md § 10. Troubleshooting](docs/runbooks/QUICK_START_GUIDE.md#10-troubleshooting)

Happy securing on Windows! 🔒
