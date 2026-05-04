# AZTDP Threat Model

## 1. System Overview

AZTDP is a zero-trust defense platform that enforces per-request authorization decisions for two backend services (Django, Spring Boot) using a shared risk scoring engine and OPA-based policy engine. Every request carrying a JWT is evaluated for behavioral risk before any business logic executes.

**Security objective:** Detect and prevent misuse of valid, unexpired authentication tokens by adversaries who have either stolen a session token, obtained credentials, or are attempting privilege escalation — without degrading legitimate user experience below acceptable latency thresholds.

---

## 2. Threat Actors

| Actor | Capability | Motivation |
|---|---|---|
| **Credential thief** | Stole a valid JWT (phishing, XSS, traffic interception) | Access payment data, exfiltrate PII |
| **Credential stuffer** | Has a list of leaked username:password pairs | Account takeover at scale |
| **Brute forcer** | Automated password enumeration | Account access |
| **Insider threat** | Valid low-privilege account | Privilege escalation, data exfiltration |
| **Session hijacker** | Intercepted a valid session from a different IP/device | Impersonate a legitimate user |
| **Replay attacker** | Captured a valid JWT from a legitimate session | Reuse token from a different location |
| **Nation-state / advanced persistent threat** | May compromise service-to-service channels | Long-term data access, exfiltration |

---

## 3. System Boundary

The AZTDP enforcement boundary encompasses:

- External clients (browsers, mobile apps, API consumers) reaching Django or Spring Boot app services
- All inter-service communication within the `aztdp` Docker network
- Keycloak as the identity provider (OIDC issuer)
- OPA as the policy decision point
- Redis for session state and token tracking
- PostgreSQL for durable audit storage

**Out of scope:** Network perimeter (firewall rules, DDoS mitigation), Keycloak internals, database-level access controls, end-user device security.

---

## 4. Trust Boundaries

```
[EXTERNAL]
    Client (Browser / API Consumer)
        |
        | HTTPS (TLS terminated at app)
        |
[BOUNDARY 1: Internet → App Services]
        |
    Django App (8010) / Spring Boot App (8011)
        |
        | HTTP (plain, internal network only)
        |
[BOUNDARY 2: App → Risk Engine]
        |
    Risk Engine (8001) ←──────── Redis (6379)
        |
        | HTTP (plain, internal)
        |
[BOUNDARY 3: App → Policy Gateway]
        |
    Gateway (8000) → OPA (8181)
        |
        | HTTP (plain, internal)
        |
[BOUNDARY 4: Gateway → Keycloak JWKS]
        |
    Keycloak (8080)
        └── JWKS endpoint (cached by app services)
```

---

## 5. STRIDE Analysis

### Boundary 1: External Client → App Services (Django / Spring Boot)

| Threat | Class | Description | Existing Mitigation | Residual Risk | Gap |
|---|---|---|---|---|---|
| Token spoofing | S | Attacker presents a self-signed or forged JWT | RS256 JWKS verification in both middleware and `RiskEnforcementFilter` | Low | None; JWKS is cached with TTL, but cache poisoning from internal network is possible if no integrity check |
| Token replay from stolen session | S | Attacker replays a valid stolen token from a different IP/UA/geo | Risk engine detects IP drift (0.35 weight), geo drift (0.2), UA drift (0.2) within 60s replay window | Medium | Replay window is only 60s; tokens live 5 minutes. A patient attacker waiting >60s can replay without triggering the replay flag |
| Credential stuffing | S | Attacker tries many credential pairs | Keycloak brute-force protection (5 failures → 15min lockout) | Medium | Lockout is per-account; distributed stuffing across many accounts is not rate-limited at the app layer |
| Request tampering | T | Attacker modifies JWT claims in transit | RS256 signature covers all claims | Low | None |
| Repudiation of actions | R | Attacker denies having made a request | Decision log to stdout (no persistence) | High | **No durable audit trail.** Fixed in Phase 11 (telemetry-ingest → PostgreSQL) |
| Info disclosure of risk signals | I | Attacker learns risk scoring behavior from error responses | Risk score is not exposed in 403 responses | Low | The `stepup` response exposes `challenge_id` — minimal info leakage |
| DoS via expensive requests | D | Attacker floods endpoints to exhaust risk engine capacity | 200ms connect / 800ms read timeouts on all clients | Medium | No rate limiting at app layer; risk engine has no queue depth protection |
| Privilege escalation | E | Non-admin JWT claims admin role access | OPA `admin_required` rule checks `realm_access.roles` | Low | Roles are pulled from JWT only; if Keycloak role assignment is compromised, this fails. No secondary RBAC check |

### Boundary 2: App Services → Risk Engine

| Threat | Class | Description | Existing Mitigation | Residual Risk | Gap |
|---|---|---|---|---|---|
| Risk engine spoofing | S | Attacker runs a fake risk engine and intercepts requests | No mTLS; relies on internal network isolation | High | **No service-to-service authentication.** Mitigated by private Docker network; production gap for Kubernetes deployments |
| Request body tampering | T | Internal attacker modifies risk request payload | No request signing | High | **No integrity check on inter-service calls.** Acceptable in dev; production gap |
| Risk engine DoS | D | Attacker floods risk engine, causing fail-open responses | Fail-open is configurable (default varies); timeouts enforced | Medium | Fail-open mode in production could be exploited: if attacker can exhaust risk engine, all requests pass |
| Risk score manipulation | T | Attacker sends crafted headers (`X-Client-Ip`, `X-Geo`) to control risk inputs | App services read `X-Client-Ip` header without validation | High | **`X-Client-Ip` and `X-Geo` headers are user-controllable.** An attacker can set `X-Client-Ip: 127.0.0.1` and `X-Geo: US-CA` to suppress IP/geo drift signals. Fix: only trust these headers from a verified upstream proxy (reverse proxy whitelist) |

### Boundary 3: App Services → Policy Gateway → OPA

| Threat | Class | Description | Existing Mitigation | Residual Risk | Gap |
|---|---|---|---|---|---|
| Policy gateway spoofing | S | Attacker replaces policy gateway with a compliant-always service | No mTLS | High | Same as Boundary 2 |
| OPA policy tampering | T | Attacker modifies `authz.rego` on disk | OPA bundle integrity (not yet configured) | Medium | OPA policy files have no signing. An attacker with filesystem access can modify policy |
| Revocation store bypass | T | Attacker directly calls OPA, bypassing gateway revocation check | Revocation check happens in gateway before OPA call | Low | None for this path |
| Revocation store data loss | I | Gateway restart clears in-memory revocation store | In-memory only (no Redis backing currently) | High | **Revocations are ephemeral.** Fixed in Phase 6B (Redis backing for revocation store) |

### Boundary 4: Gateway → Keycloak JWKS

| Threat | Class | Description | Existing Mitigation | Residual Risk | Gap |
|---|---|---|---|---|---|
| JWKS cache poisoning | T | Attacker poisons the JWKS cache in the app process | JWKS fetched over HTTP (no TLS in dev); cached in memory | High | In production, JWKS endpoint must be HTTPS-only |
| Keycloak unavailability | D | Keycloak goes down; JWKS cache expires; all requests fail | JWKS is cached in memory for token TTL duration (5m) | Low | Cache TTL alignment with token TTL is correct |
| Algorithm confusion attack | E | Attacker switches JWT algorithm to `none` or `HS256` | `JwtVerifier` explicitly requires RS256; `RiskEnforcementFilter` uses Spring's OIDC validation | Low | None |

---

## 6. Attack Scenario Catalog

### AS-1: Token Replay Attack
**Scenario:** Attacker captures a valid JWT (via XSS or network sniff) and replays it from a different IP within 60 seconds.
**Expected AZTDP response:** Risk engine detects IP drift (Δ=0.35) + possible geo drift (Δ=0.2), combined risk ≥ 0.65. If sensitivity ≥ 4, OPA triggers `stepup`. If replay window active (same JTI used twice within 60s with different IP), `replay_detected=True` → hard 403.
**Simulated by:** `services/attack-sim/token_replay.py`
**Coverage gap:** Replay window is 60s. Stolen tokens are valid for 5 minutes. Attacker can wait 61s to avoid detection; drift signals (IP, geo) still fire but result in `stepup` rather than outright block for low-sensitivity endpoints.

### AS-2: Credential Stuffing
**Scenario:** Attacker has 10,000 username:password pairs from a prior breach and tries them against Keycloak.
**Expected AZTDP response:** Keycloak brute-force protection locks accounts after 5 failures. Individual accounts beyond 5 attempts return 401 from Keycloak.
**Simulated by:** `services/attack-sim/credential_stuffing.py`
**Coverage gap:** Per-account lockout only. Distributed stuffing across thousands of accounts is not detected at AZTDP layer. Anomaly service (Phase 7) will detect unusual request rates but only after token issuance.

### AS-3: Privilege Escalation
**Scenario:** Attacker with a valid `user` role JWT attempts access to `/v1/admin/*` endpoints.
**Expected AZTDP response:** OPA `admin_required` rule denies: `input.subject.roles` does not contain `admin` → decision=deny.
**Simulated by:** `services/attack-sim/privilege_escalation.py`
**Coverage gap:** None at OPA layer. Gap: if attacker can manipulate `realm_access.roles` claim (requires Keycloak compromise), OPA would allow.

### AS-4: Geo Drift / Session Hijack
**Scenario:** Attacker steals a session token and uses it from a different country.
**Expected AZTDP response:** Risk engine detects geo drift (Δ=0.2) + IP drift (Δ=0.35). For high-sensitivity endpoints (sensitivity ≥ 4), combined risk ≥ 0.65 → `stepup`. For low-sensitivity, risk 0.55 → `allow` (below threshold). 
**Simulated by:** `services/attack-sim/geo_drift_attack.py` (Phase 8)
**Coverage gap:** Low-sensitivity endpoints remain accessible even with full geo+IP drift (risk=0.65 base+drift, threshold is 0.65 for stepup, only at sensitivity ≥ 4).

### AS-5: Brute Force Authentication
**Scenario:** Attacker attempts to guess a single user's password.
**Expected AZTDP response:** Keycloak brute-force protection (failureFactor=5, lockout=15min).
**Simulated by:** `services/attack-sim/brute_force.py`
**Coverage gap:** None at AZTDP layer; this is a Keycloak-layer defense.

### AS-6: Anomaly Flood
**Scenario:** Attacker sends 100 requests per minute for the same user from rotating IPs/geos to extract data at scale.
**Expected AZTDP response (after Phase 7):** Anomaly service detects elevated `request_rate_1m`. Isolation Forest flags as anomalous (score > 0.7). Anomaly score feeds into combined risk → deny/stepup.
**Simulated by:** `services/attack-sim/anomaly_flood.py` (Phase 8)
**Coverage gap until Phase 7:** Anomaly score is always 0.0; flood is not detected beyond per-request drift signals.

---

## 7. Mitigations Summary

| Gap ID | Description | Fix Phase |
|---|---|---|
| G-1 | `X-Client-Ip`/`X-Geo` headers are user-controllable | Architectural note: trust only from verified reverse proxy. Mark in docs. |
| G-2 | No inter-service authentication (mTLS) | Out of scope for Phase 1 MVP; documented for production hardening |
| G-3 | Revocation store ephemeral (lost on gateway restart) | Phase 6B: Redis backing |
| G-4 | No durable audit trail | Phase 11: telemetry-ingest → PostgreSQL |
| G-5 | Replay window only 60s (tokens live 5min) | Partially mitigated by drift scoring. Full fix: reduce access token TTL to 2min |
| G-6 | Fail-open on risk engine unavailability can be exploited | Config discipline: `FAIL_OPEN=false` in production |
| G-7 | Anomaly flood not detected until Phase 7 | Phase 7: Isolation Forest anomaly service |
| G-8 | OPA policy files have no signing | Future: OPA bundle signing with `opa build --signing-key` |

---

## 8. Compliance Considerations

| Control | Standard | AZTDP Implementation |
|---|---|---|
| Audit logging | SOC 2 CC7.2, ISO 27001 A.12.4 | Phase 11 audit_events table |
| Session management | OWASP ASVS 3.3 | Token TTL + revocation store |
| Least privilege | NIST SP 800-207 | OPA admin_required rule |
| Anomaly detection | NIST CSF DE.AE | Phase 7 Isolation Forest |
| Incident response | SOC 2 CC7.3 | Phase 11 forensics service |
