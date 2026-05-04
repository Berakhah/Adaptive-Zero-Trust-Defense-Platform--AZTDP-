# AZTDP Sequence Diagrams

## SD-1: Service Startup and Dependency Order

```mermaid
sequenceDiagram
    participant DC as docker compose
    participant PG as PostgreSQL
    participant RD as Redis
    participant KC as Keycloak
    participant OPA
    participant GW as Gateway
    participant RE as Risk Engine
    participant AS as Anomaly Service
    participant TI as Telemetry Ingest
    participant FS as Forensics
    participant DJ as Django App
    participant SP as Spring App

    DC->>PG: start (waits pg_isready)
    DC->>RD: start (waits redis-cli ping)
    DC->>KC: start (waits /health/ready)
    Note over PG,KC: Phase 1: Storage + Identity
    DC->>OPA: start (waits /health)
    DC->>GW: start (depends: redis, keycloak, opa)
    DC->>RE: start (depends: redis, keycloak)
    Note over OPA,RE: Phase 2: Risk + Policy
    DC->>AS: start (depends: redis, risk-engine)
    DC->>TI: start (depends: postgres, gateway, risk-engine)
    Note over AS,TI: Phase 3: ML + Telemetry
    DC->>FS: start (depends: postgres, telemetry-ingest)
    DC->>DJ: start (depends: all above)
    DC->>SP: start (depends: all above)
    Note over FS,SP: Phase 4: Business Services
```

---

## SD-2: Normal Authorized Request (Full Stack)

```mermaid
sequenceDiagram
    autonumber
    actor C as Client
    participant DJ as Django App
    participant KC as Keycloak JWKS
    participant RE as Risk Engine
    participant RD as Redis
    participant AS as Anomaly Service
    participant GW as Gateway
    participant OPA
    participant TI as Telemetry Ingest

    C->>DJ: GET /v1/payments/123\nAuthorization: Bearer <jwt>
    
    Note over DJ: Step 1: JWT Verification
    DJ->>KC: GET /realms/aztdp/protocol/openid-connect/certs\n(cached, 5min TTL — usually skipped)
    KC-->>DJ: JWKS (RS256 keys)
    DJ->>DJ: PyJWT.decode(token, key, algorithms=["RS256"])\nVerify iss, aud, exp\nExtract: sub, jti, sid, realm_access.roles

    Note over DJ,RE: Step 2: Risk Evaluation
    DJ->>RE: POST /v1/risk/evaluate\n{request_id, session_id, user_id,\n token_jti_hash, ip, geo, user_agent_hash,\n endpoint: {service, method, path, sensitivity}}
    RE->>RD: GET token:last_seen:{jti_hash}
    RD-->>RE: {"ip":"203.0.113.10","ua":"abc","geo":"US-CA","ts":1720000000}
    RE->>RE: score_risk(): ip matches, ua matches, geo matches\nrisk = 0.10 (base only)\ntrust = 0.90
    RE->>AS: POST /v1/anomaly/score (async, 150ms timeout)
    AS->>RD: ZRANGEBYSCORE user:request_rate:{user_id} [now-60, now]
    RD-->>AS: count=3
    AS->>AS: extract_features(): hour=14, rate=3, no drift → benign
    AS->>AS: model.score([...]) → 0.08
    AS-->>RE: {anomaly_score: 0.08, is_anomalous: false}
    RE->>RD: SETEX token:last_seen:{jti_hash} 1800 {...updated...}
    RE-->>DJ: {risk_score: 0.10, trust_score: 0.90,\n anomaly_score: 0.08, reasons: []}

    Note over DJ,GW: Step 3: Policy Decision
    DJ->>GW: POST /v1/policy/decision\n{input: {request_id, subject:{user_id, roles:["user"],\n session_trust:0.90},\n resource:{path:"/v1/payments/123", sensitivity:4},\n context:{risk_score:0.10, anomaly_score:0.08,\n token_jti_hash, is_token_revoked:false}}}
    GW->>RD: GET revocation:{jti_hash} → nil (not revoked)
    GW->>OPA: POST /v1/data/aztdp/authz/decision\n{input: {...}}
    OPA->>OPA: Evaluate authz.rego:\nrisk_score=0.10 < 0.65, sensitivity=4\n→ low_risk_allow fires? No: sensitivity=4 >= 4\ncheck: risk >= 0.65 → false\ncheck: allow for lower sensitivity → path sensitivity is 4\ndefault → allow (risk < 0.65, not admin path, not revoked)
    OPA-->>GW: {result: {decision:"allow", reason:{rule:"low_risk_allow"}}}
    GW->>GW: log_decision() → stdout JSON
    GW->>TI: POST /v1/telemetry/event (fire-and-forget, 100ms)
    GW-->>DJ: {decision: {decision:"allow", reason:{rule:"low_risk_allow"}}}

    Note over DJ,C: Step 4: Enforcement
    DJ->>DJ: action="allow" → pass to handler
    DJ-->>C: 200 OK\n{"payment_id":"123","amount":1500,...,\n "aztdp":{"risk_score":0.10,"decision":"allow"}}
```

---

## SD-3: Token Replay Attack — Blocked (Hard Deny)

```mermaid
sequenceDiagram
    autonumber
    actor AT as Attacker
    participant DJ as Django App
    participant RE as Risk Engine
    participant RD as Redis

    Note over AT: Has stolen victim's JWT (valid, not expired)\nAttacker IP: 198.51.100.55\nVictim was at: 203.0.113.10, 45s ago

    AT->>DJ: GET /v1/payments/123\nAuthorization: Bearer <stolen_jwt>\nX-Client-Ip: 198.51.100.55

    DJ->>DJ: JWT verify passes (token is valid)
    DJ->>RE: POST /v1/risk/evaluate\n{ip: "198.51.100.55",\n jti_hash: "<victim_jti_hash>", ...}

    RE->>RD: GET token:last_seen:{victim_jti_hash}
    RD-->>RE: {ip:"203.0.113.10", ts:1720000000}\n(45 seconds ago)

    RE->>RE: ip changed AND (now - ts) < 60s\n→ replay_detected = True

    RE-->>DJ: HTTP 409 Conflict\n{detail: "replay_detected"}

    DJ->>DJ: RiskClientError(code="replay_detected")\nignores fail_open setting for replay

    DJ-->>AT: HTTP 403 Forbidden\n{error: {code: "token_replay"}}

    Note over AT,RD: Token NOT added to revocation store.\nRisk engine state unchanged.\nNext request from victim still works normally.
```

---

## SD-4: High-Risk Request — Step-Up Authentication Required

```mermaid
sequenceDiagram
    autonumber
    actor C as Legitimate User (traveling)
    participant DJ as Django App
    participant RE as Risk Engine
    participant GW as Gateway
    participant OPA

    Note over C: User normally in US-CA\nNow traveling, connected from GB-LDN with new IP

    C->>DJ: POST /v1/payments/transfer\nX-Client-Ip: 51.68.100.20\nX-Geo: GB-LDN

    DJ->>DJ: JWT verify passes
    DJ->>RE: POST /v1/risk/evaluate\n{ip:"51.68.100.20", geo:"GB-LDN",\n endpoint.sensitivity:4}

    RE->>RE: score_risk():\nbase=0.10\n+ sensitivity=0.15 (sensitivity>=4)\n+ ip_drift=0.35 (IP changed)\n+ geo_drift=0.20 (geo changed)\n= 0.80 (capped at 1.0)

    RE-->>DJ: {risk_score:0.80, trust_score:0.20,\n reasons:[IP_GEO_DRIFT, HIGH_SENSITIVITY, GEO_DRIFT]}

    DJ->>GW: POST /v1/policy/decision\n{context:{risk_score:0.80},\n resource:{sensitivity:4, path:"/v1/payments/transfer"}}

    GW->>OPA: POST /v1/data/aztdp/authz/decision
    OPA->>OPA: risk_score=0.80 >= 0.65 AND sensitivity=4 >= 4\n→ high_risk_stepup fires\ndecision = "stepup"
    OPA-->>GW: {result:{decision:"stepup",\n reason:{rule:"high_risk_stepup"}}}

    GW-->>DJ: {decision:{decision:"stepup"}}

    DJ->>DJ: action="stepup" → _stepup(reason)
    DJ-->>C: HTTP 401 Unauthorized\n{error:{code:"STEP_UP_REQUIRED",\n details:{challenge_id:"uuid",\n methods:["otp","webauthn"],\n expires_in_seconds:300}}}

    Note over C: User completes MFA challenge\n(outside AZTDP scope — handled by client/Keycloak)\nNew token issued with elevated session_trust claim
```

---

## SD-5: Privilege Escalation Attempt — Blocked

```mermaid
sequenceDiagram
    autonumber
    actor AT as Attacker (valid user role)
    participant SP as Spring Boot App
    participant RE as Risk Engine
    participant GW as Gateway
    participant OPA

    AT->>SP: GET /v1/admin/users\nAuthorization: Bearer <user_role_jwt>

    SP->>SP: JWT verify passes\nExtract roles: ["user"] (no "admin")

    SP->>RE: POST /v1/risk/evaluate\n{endpoint:{path:"/v1/admin/users", sensitivity:5}}
    RE-->>SP: {risk_score:0.25, trust_score:0.75}\n(base + sensitivity weight only, no drift)

    SP->>GW: POST /v1/policy/decision\n{subject:{roles:["user"]},\n resource:{path:"/v1/admin/users", sensitivity:5}}

    GW->>OPA: POST /v1/data/aztdp/authz/decision
    OPA->>OPA: path starts with /v1/admin\n"admin" NOT in input.subject.roles\n→ admin_required fires\ndecision = "deny"
    OPA-->>GW: {result:{decision:"deny",\n reason:{rule:"admin_required"}}}

    GW-->>SP: {decision:{decision:"deny"}}
    SP-->>AT: HTTP 403 Forbidden\n{error:{code:"policy_denied",\n timestamp:"2026-05-03T..."}}
```

---

## SD-6: Token Revocation Flow

```mermaid
sequenceDiagram
    autonumber
    participant Policy as OPA Decision
    participant DJ as Django App
    participant GW as Gateway
    participant RD as Redis
    participant TI as Telemetry Ingest

    Note over Policy,DJ: OPA returns decision="revoke"\n(e.g., very_high_risk: score >= 0.90)

    Policy-->>DJ: {decision:"revoke", reason:{rule:"very_high_risk"}}

    DJ->>GW: POST /v1/tokens/revoke\n{token_jti_hash:"abc123",\n reason:"very_high_risk",\n source:"policy"}

    GW->>RD: SETEX revocation:abc123 3600 "1"\n(Phase 6B — currently in-memory only)
    GW->>TI: POST /v1/telemetry/event\n{event_type:"token_revocation", payload:{...}}\n(fire-and-forget)
    GW-->>DJ: {status:"revoked"}

    DJ-->>Client: HTTP 403 Forbidden\n{error:{code:"token_revoked"}}

    Note over RD: Subsequent requests with same token_jti_hash:\nGateway checks revocation BEFORE OPA call\n→ immediately returns decision="revoke"\nNo OPA call needed
```

---

## SD-7: Fail-Open Scenario (Risk Engine Unavailable)

```mermaid
sequenceDiagram
    autonumber
    actor C as Client
    participant DJ as Django App
    participant RE as Risk Engine (DOWN)

    Note over RE: Risk Engine is restarting\nor over timeout budget

    C->>DJ: GET /v1/payments/123\nAuthorization: Bearer <valid_jwt>

    DJ->>DJ: JWT verify passes
    DJ->>RE: POST /v1/risk/evaluate\n(connect_timeout=0.2s, read_timeout=0.8s)

    RE-->>DJ: ConnectionError (after 0.2s timeout)

    DJ->>DJ: RiskClientError raised\ncode != "replay_detected"\nCheck: fail_open setting

    alt AZTDP_FAIL_OPEN=true (dev)
        DJ->>DJ: Skip risk + policy evaluation
        DJ->>DJ: Pass directly to handler
        DJ-->>C: 200 OK (handler response)
        Note over DJ: Decision logged as "fail_open_bypass"
    else AZTDP_FAIL_OPEN=false (production default)
        DJ-->>C: 403 Forbidden\n{error:{code:"risk_unavailable"}}
    end
```

---

## SD-8: Forensics — Incident Reconstruction

```mermaid
sequenceDiagram
    autonumber
    actor Analyst as Security Analyst
    participant FS as Forensics Service
    participant PG as PostgreSQL

    Note over Analyst: Investigating suspicious session\n"session_abc123" flagged in alerts

    Analyst->>FS: GET /v1/forensics/replay/session_abc123

    FS->>PG: SELECT * FROM sessions\nWHERE session_id='session_abc123'
    PG-->>FS: {user_id:"user-42", started_at:"...",\n ip_first:"203.0.113.10",\n geo_first:"US-CA", risk_max:0.87}

    FS->>PG: SELECT * FROM audit_events\nWHERE session_id='session_abc123'\nORDER BY occurred_at ASC
    PG-->>FS: 12 events (risk_evals, policy_decisions, anomaly_scores)

    FS->>FS: Compute delta_ms between consecutive events\nGroup by event_type

    FS-->>Analyst: {session:{...}, events:[\n  {event_type:"risk_eval", delta_ms:0,\n   payload:{risk_score:0.10}},\n  {event_type:"policy_decision", delta_ms:45,\n   payload:{decision:"allow"}},\n  ...\n  {event_type:"policy_decision", delta_ms:12300,\n   payload:{decision:"deny",\n   reason:{rule:"very_high_risk"}}}\n]}

    Analyst->>FS: GET /v1/forensics/incidents/{request_id_of_deny}

    FS->>PG: SELECT * FROM policy_decisions\nWHERE request_id='{id}'
    PG-->>FS: {decision:"deny", risk_score:0.91, decided_at:"..."}

    FS->>PG: SELECT * FROM audit_events\nWHERE session_id='session_abc123'\nAND occurred_at BETWEEN (decided_at - 5s) AND (decided_at + 5s)
    PG-->>FS: 4 related events (2 risk_evals, 1 anomaly, 1 policy)

    FS-->>Analyst: {incident:{...deny decision...},\n context:[...4 related events...]}

    Note over Analyst: Full attack timeline visible:\nwhat changed, when, with what risk scores
```
