# AZTDP Platform Validation Script (PowerShell - Windows)
# Run with: powershell -ExecutionPolicy Bypass -File scripts/validate_platform.ps1

param(
    [switch]$Verbose = $false
)

# Colors
$Green = "Green"
$Red = "Red"
$Yellow = "Yellow"
$Blue = "Cyan"

$passed = 0
$failed = 0
$skipped = 0

function Write-Header {
    param([string]$message)
    Write-Host ""
    Write-Host "═════════════════════════════════════════════════════" -ForegroundColor $Blue
    Write-Host $message -ForegroundColor $Blue
    Write-Host "═════════════════════════════════════════════════════" -ForegroundColor $Blue
    Write-Host ""
}

function Write-Test {
    param([string]$message)
    Write-Host -NoNewline "  $message ... "
}

function Write-Pass {
    Write-Host "✓ PASS" -ForegroundColor $Green
    $script:passed++
}

function Write-Fail {
    param([string]$reason)
    Write-Host "✗ FAIL" -ForegroundColor $Red
    Write-Host "    $reason" -ForegroundColor $Red
    $script:failed++
}

function Write-Skip {
    param([string]$reason)
    Write-Host "⊘ SKIP" -ForegroundColor $Yellow
    Write-Host "    $reason" -ForegroundColor $Yellow
    $script:skipped++
}

# 1. PREREQUISITES
Write-Header "1. CHECKING PREREQUISITES"

Write-Test "Docker installed"
if (Get-Command docker -ErrorAction SilentlyContinue) {
    Write-Pass
} else {
    Write-Fail "Docker not found. Install Docker Desktop from https://www.docker.com/products/docker-desktop"
    exit 1
}

Write-Test "Docker Compose installed"
if (Get-Command docker -ErrorAction SilentlyContinue) {
    $composeVersion = docker compose version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Pass
    } else {
        Write-Fail "Docker Compose not found"
        exit 1
    }
} else {
    Write-Fail "Docker Compose not found"
    exit 1
}

Write-Test "curl installed"
if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
    Write-Pass
} else {
    Write-Skip "curl.exe not found (optional)"
}

Write-Test "jq installed"
if (Get-Command jq -ErrorAction SilentlyContinue) {
    Write-Pass
} else {
    Write-Skip "jq not found (optional, for JSON parsing)"
}

# 2. DOCKER SERVICES
Write-Header "2. CHECKING DOCKER SERVICES"

Write-Test "All containers running"
$running = @(docker compose ps -q 2>$null).Count
if ($running -ge 10) {
    Write-Pass
} else {
    Write-Fail "Expected at least 10 containers, found $running. Run: docker compose up -d --build"
}

# Check individual services
$services = @("gateway", "risk-engine", "anomaly-service", "telemetry-ingest", "forensics",
              "django-app", "keycloak", "opa", "postgres", "redis")

foreach ($service in $services) {
    Write-Test "Service '$service' is running"
    $status = docker compose ps $service 2>&1 | Select-String "Up"
    if ($status) {
        Write-Pass
    } else {
        Write-Fail "Service not running. Check: docker compose logs $service"
    }
}

# 3. HEALTH ENDPOINTS
Write-Header "3. CHECKING SERVICE HEALTH ENDPOINTS"

function Test-Health {
    param([string]$service, [int]$port)

    Write-Test "Health check: $service (port $port)"

    try {
        $response = Invoke-WebRequest -Uri "http://localhost:$port/health" `
                                     -TimeoutSec 5 `
                                     -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            Write-Pass
            return $true
        }
    } catch {
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:$port/health/ready" `
                                         -TimeoutSec 5 `
                                         -ErrorAction Stop
            if ($response.StatusCode -eq 200) {
                Write-Pass
                return $true
            }
        } catch {
            Write-Fail "Health endpoint not responding at http://localhost:$port/health"
            return $false
        }
    }
}

Test-Health "gateway" 8000
Test-Health "risk-engine" 8001
Test-Health "anomaly-service" 8002
Test-Health "telemetry-ingest" 8003
Test-Health "forensics" 8004
Test-Health "django-app" 8010
Test-Health "keycloak" 8080
Test-Health "opa" 8181

# 4. DATABASE CONNECTIVITY
Write-Header "4. CHECKING DATABASE CONNECTIVITY"

Write-Test "PostgreSQL connection"
try {
    $pgTest = docker compose exec postgres psql -U aztdp -d aztdp -c "SELECT 1;" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Pass
    } else {
        Write-Fail "Cannot connect to PostgreSQL"
    }
} catch {
    Write-Fail "Cannot connect to PostgreSQL: $_"
}

Write-Test "PostgreSQL schema initialized"
try {
    $tables = docker compose exec postgres psql -U aztdp -d aztdp -c "\dt" 2>&1 | Select-String "risk_evaluations"
    if ($tables) {
        Write-Pass
    } else {
        Write-Fail "Database schema not initialized"
    }
} catch {
    Write-Fail "Cannot check database schema"
}

Write-Test "Redis connection"
try {
    $redisTest = docker compose exec redis redis-cli ping 2>&1
    if ($LASTEXITCODE -eq 0 -and $redisTest -like "*PONG*") {
        Write-Pass
    } else {
        Write-Fail "Cannot connect to Redis"
    }
} catch {
    Write-Fail "Cannot connect to Redis: $_"
}

# 5. AUTHENTICATION
Write-Header "5. CHECKING AUTHENTICATION"

Write-Test "Token request succeeds"
try {
    $tokenResponse = curl.exe -s -X POST http://localhost:8080/realms/aztdp/protocol/openid-connect/token `
        -d grant_type=password `
        -d client_id=aztdp-client `
        -d client_secret=aztdp-secret `
        -d username=user1 `
        -d password=password 2>&1

    if ($tokenResponse -like '*access_token*' -and $tokenResponse.Length -gt 100) {
        Write-Pass
        $env:TOKEN = $tokenResponse
    } else {
        Write-Fail "Token request failed or returned invalid response"
    }
} catch {
    Write-Fail "Token request failed: $_"
}

# 6. POLICY ENGINE
Write-Header "6. CHECKING POLICY ENGINE"

Write-Test "OPA policy decision works"
try {
    $decision = curl.exe -s -X POST http://localhost:8181/v1/data/authz/decision `
        -H "Content-Type: application/json" `
        -d '{
            "user": "user1",
            "ip": "203.0.113.10",
            "geo": "US-CA",
            "request_id": "test-'$(Get-Date -UFormat %s)'"
        }' 2>&1

    if ($decision -like '*result*' -or $decision -like '*decision*') {
        Write-Pass
    } else {
        Write-Fail "OPA policy decision query failed"
    }
} catch {
    Write-Fail "OPA policy decision query failed: $_"
}

# 7. MONITORING
Write-Header "7. CHECKING MONITORING STACK"

Write-Test "Prometheus metrics endpoint"
try {
    $response = Invoke-WebRequest -Uri "http://localhost:9090/api/v1/query?query=up" `
                                 -TimeoutSec 5 `
                                 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        Write-Pass
    }
} catch {
    Write-Fail "Prometheus not accessible"
}

Write-Test "Grafana dashboard"
try {
    $response = Invoke-WebRequest -Uri "http://localhost:3000/api/health" `
                                 -TimeoutSec 5 `
                                 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        Write-Pass
    }
} catch {
    Write-Fail "Grafana not accessible"
}

# SUMMARY
Write-Header "VALIDATION SUMMARY"
Write-Host "  ✓ Passed:  $passed" -ForegroundColor $Green
Write-Host "  ✗ Failed:  $failed" -ForegroundColor $Red
Write-Host "  ⊘ Skipped: $skipped" -ForegroundColor $Yellow

if ($failed -eq 0) {
    Write-Host ""
    Write-Host "✓ All validations passed!" -ForegroundColor $Green
    Write-Host ""
    exit 0
} else {
    Write-Host ""
    Write-Host "✗ Some validations failed. See above for details." -ForegroundColor $Red
    Write-Host ""
    exit 1
}
