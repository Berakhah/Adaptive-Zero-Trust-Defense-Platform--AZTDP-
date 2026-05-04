# Keycloak Setup for AZTDP

## Admin User (Local Access)
Local access is required to create the administrative user. Either open
http://localhost:8080/ and complete the admin user prompt, or set the
environment variables `KEYCLOAK_ADMIN` and `KEYCLOAK_ADMIN_PASSWORD` before
starting the server.

## 1) Create Realm
- Create realm: `aztdp`
- Set Login settings: enable brute force protection and set lockout thresholds.

## 2) Create Clients

### aztdp-api (resource server)
- Client ID: `aztdp-api`
- Client type: `confidential`
- Authorization: OFF
- Standard Flow: ON
- Direct Access Grants: OFF
- Service Accounts: OFF
- Valid Redirect URIs: set to your app hosts
- Web Origins: set to your app hosts

### aztdp-gateway (service client)
- Client ID: `aztdp-gateway`
- Client type: `confidential`
- Service Accounts: ON
- Direct Access Grants: OFF

### aztdp-risk-engine (service client)
- Client ID: `aztdp-risk-engine`
- Client type: `confidential`
- Service Accounts: ON
- Direct Access Grants: OFF

## 3) Roles
- Realm roles: `user`, `admin`, `risk_override`
- Assign `admin` to security operators, `user` to standard users.

## 4) Custom Token Claims
Create protocol mappers on client `aztdp-api`:

### risk_score
- Mapper Type: User Attribute
- User Attribute: `risk_score`
- Token Claim Name: `risk_score`
- Claim JSON Type: `double`
- Add to access token: ON

### session_trust
- Mapper Type: User Attribute
- User Attribute: `session_trust`
- Token Claim Name: `session_trust`
- Claim JSON Type: `double`
- Add to access token: ON

Set defaults per user:
- In Users > Attributes, set `risk_score=0.0`, `session_trust=1.0` for new users.

## 5) Token Settings
- Access token lifespan: 5m
- Refresh token lifespan: 30m
- SSO Session idle: 30m
- SSO Session max: 8h

## 6) JWKS and Issuer
- Issuer: `http://keycloak:8080/realms/aztdp`
- JWKS: `http://keycloak:8080/realms/aztdp/protocol/openid-connect/certs`

## 7) Admin API (Optional for session revocation)
- Create client `aztdp-admin` (confidential)
- Service Accounts: ON
- Assign `realm-management` roles:
  - `view-users`
  - `manage-users`
  - `view-realm`
  - `manage-realm`

## 8) Hardening Checklist
- Restrict admin console to internal network only.
- Enforce MFA for admin users.
- Set brute force detection and IP lockouts.
- Rotate client secrets on a schedule.
