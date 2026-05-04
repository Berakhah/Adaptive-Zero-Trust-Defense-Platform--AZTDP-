# Attack Simulation Runbook

## Overview
These scripts simulate real attack patterns against AZTDP services. Use a non-production environment.

## Environment Variables
- `AZTDP_BASE_URL`: App base URL (default: http://localhost:8000)
- `AZTDP_ACCESS_TOKEN`: Pre-issued access token for replay and privilege tests
- `AZTDP_USERNAME` / `AZTDP_PASSWORD`: Credentials for password grant
- `AZTDP_CLIENT_ID`: Keycloak client ID (default: aztdp-api)
- `AZTDP_CLIENT_SECRET`: Keycloak client secret (optional)
- `AZTDP_KEYCLOAK_TOKEN_URL`: Token endpoint
- `AZTDP_CREDENTIAL_FILE`: File with `user:pass` per line
- `AZTDP_PASSWORD_LIST`: Comma-separated list for brute force
- `AZTDP_REQUEST_DELAY_MS`: Sleep between attempts (default: 100ms)

## Scripts

### Token Replay
```
python services/attack-sim/token_replay.py
```
Expected:
- First request: 200 or 403 depending on policy
- Replay request: 403 with error code `token_replay`

### Credential Stuffing
```
python services/attack-sim/credential_stuffing.py
```
Expected:
- Invalid credentials: 400/401 responses from Keycloak
- After repeated attempts: account lock or rate limiting if Keycloak brute force protection is enabled

### Brute Force
```
python services/attack-sim/brute_force.py
```
Expected:
- Repeated failures with 400/401
- Eventual lockout if brute force protection is enabled

### Privilege Escalation
```
python services/attack-sim/privilege_escalation.py
```
Expected:
- 403 with `policy_denied` when non-admin token hits `/v1/admin/*`
- If admin role exists, still subject to risk/step-up decisions
