# AZTDP Data Flow Diagrams

## DFD Level 0 — System Context

```mermaid
C4Context
    title AZTDP System Context
    Person(client, "Client", "Browser, mobile app, or API consumer with a valid OIDC session")
    System(aztdp, "AZTDP", "Adaptive Zero-Trust Defense Platform — enforces per-request risk-based authorization")
    System_Ext(keycloak, "Keycloak", "OIDC Identity Provider — issues and validates JWTs")
    System_Ext(attacker, "Adversary", "Token replay, credential stuffer, privilege escalator")

    Rel(client, aztdp, "HTTPS API requests with Bearer JWT")
    Rel(attacker, aztdp, "Malicious HTTPS requests with valid or stolen JWTs")
    Rel(aztdp, keycloak, "JWKS fetch for JWT verification (cached)")
    Rel(keycloak, client, "Issues access + refresh tokens after authentication")
```

---

## DFD Level 1 — AZTDP Internal Data Flows

```mermaid
flowchart TD
    Client([Client / Attacker])

    subgraph AppLayer["App Services (Boundary 1)"]
        Django["Django App\n:8010"]
        Spring["Spring Boot App\n:8011"]
    end

    subgraph RiskLayer["Risk & Policy (Boundary 2/3)"]
        RiskEngine["Risk Engine\n:8001"]
        Gateway["Policy Gateway\n:8000"]
        OPA["OPA\n:8181"]
    end

    subgraph MLLayer["ML (Phase 7)"]
        AnomalyService["Anomaly Service\n:8002"]
    end

    subgraph Storage["Storage"]
        Redis[(Redis\n:6379)]
        Postgres[(PostgreSQL\n:5432)]
    end

    subgraph Observability["Observability (Phase 11)"]
        Telemetry["Telemetry Ingest\n:8003"]
        Forensics["Forensics\n:8004"]
        Prometheus["Prometheus\n:9090"]
        Grafana["Grafana\n:3000"]
    end

    Keycloak["Keycloak\n:8080"]

    Client -->|"Bearer JWT\nHTTPS"| Django
    Client -->|"Bearer JWT\nHTTPS"| Spring

    Django -->|"1. Verify JWT\n(JWKS cached)"| Keycloak
    Spring -->|"1. Verify JWT\n(JWKS cached)"| Keycloak

    Django -->|"2. POST /v1/risk/evaluate\n{ip, geo, ua_hash, jti_hash, endpoint}"| RiskEngine
    Spring -->|"2. POST /v1/risk/evaluate"| RiskEngine

    RiskEngine -->|"Read/Write token:last_seen:{hash}"| Redis
    RiskEngine -->|"3. POST /v1/anomaly/score\n(async, 150ms timeout)"| AnomalyService
    AnomalyService -->|"Read user:request_rate:{id}"| Redis

    Django -->|"4. POST /v1/policy/decision\n{risk_score, anomaly_score, roles, resource}"| Gateway
    Spring -->|"4. POST /v1/policy/decision"| Gateway

    Gateway -->|"Check revocation\n(in-memory + Redis Phase 6B)"| Redis
    Gateway -->|"POST /v1/data/aztdp/authz\n{input}"| OPA

    OPA -->|"decision:\nallow/deny/stepup/revoke"| Gateway
    Gateway -->|"decision response"| Django
    Gateway -->|"decision response"| Spring

    Django -->|"5. Enforce:\nallow → handler\ndeny → 403\nstepup → 401+challenge\nrevoke → revoke+403"| Client
    Spring -->|"5. Enforce"| Client

    Gateway -->|"Fire-and-forget\nPOST /v1/telemetry/event"| Telemetry
    RiskEngine -->|"Fire-and-forget telemetry"| Telemetry
    Telemetry -->|"Write audit_events\nrisk_evaluations\npolicy_decisions"| Postgres

    Forensics -->|"Query"| Postgres
    Prometheus -->|"Scrape /metrics"| RiskEngine
    Prometheus -->|"Scrape /metrics"| Gateway
    Prometheus -->|"Scrape /metrics"| AnomalyService
    Prometheus -->|"Scrape /metrics"| Telemetry
    Prometheus -->|"Scrape /actuator/prometheus"| Spring
    Grafana -->|"Query"| Prometheus
```

---

## Request Lifecycle — Normal (Authorized) Request

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant App as Django/Spring App
    participant KC as Keycloak JWKS
    participant RE as Risk Engine
    participant Redis
    participant AS as Anomaly Service
    participant GW as Policy Gateway
    participant OPA

    C->>App: GET /v1/payments/123\nAuthorization: Bearer <jwt>
    App->>KC: GET /.well-known/jwks.json (cached, 5min TTL)
    KC-->>App: {"keys": [...]}
    App->>App: Verify JWT signature (RS256)\nExtract: sub, jti, sid, roles
    App->>RE: POST /v1/risk/evaluate\n{ip, geo, ua_hash, jti_hash, endpoint}
    RE->>Redis: GET token:last_seen:{jti_hash}
    Redis-->>RE: {ip, ua, geo, ts} (last seen)
    RE->>RE: score_risk() → 0.15 (no drift)
    RE->>AS: POST /v1/anomaly/score (async, 150ms timeout)
    AS->>Redis: ZRANGEBYSCORE user:request_rate:{user_id}
    AS-->>RE: {anomaly_score: 0.12, is_anomalous: false}
    RE->>Redis: SET token:last_seen:{jti_hash} (update)
    RE-->>App: {risk_score: 0.15, trust_score: 0.85, anomaly_score: 0.12}
    App->>GW: POST /v1/policy/decision\n{subject, resource, context:{risk_score:0.15}}
    GW->>Redis: GET revocation:{jti_hash} → not found
    GW->>OPA: POST /v1/data/aztdp/authz\n{input: ...}
    OPA->>OPA: Evaluate: risk < 0.65, sensitivity=2 → allow
    OPA-->>GW: {decision: "allow", reason: {rule: "low_risk_allow"}}
    GW->>GW: log_decision() → stdout + telemetry
    GW-->>App: {decision: {decision: "allow"}}
    App->>App: Pass request to handler
    App-->>C: 200 OK {payment data}
```

---

## Request Lifecycle — Token Replay Attack (Blocked)

```mermaid
sequenceDiagram
    autonumber
    participant Attacker
    participant App as Django/Spring App
    participant KC as Keycloak JWKS
    participant RE as Risk Engine
    participant Redis
    participant GW as Policy Gateway

    Note over Attacker: Has stolen a valid JWT\nfrom victim at IP 203.0.113.10
    Attacker->>App: GET /v1/payments/123\nAuthorization: Bearer <stolen_jwt>\nX-Client-Ip: 198.51.100.55 (attacker IP)
    App->>KC: JWKS (cached) — JWT is valid (not expired)
    App->>RE: POST /v1/risk/evaluate\n{ip: "198.51.100.55", jti_hash: "<victim_jti>"}
    RE->>Redis: GET token:last_seen:{victim_jti}
    Redis-->>RE: {ip: "203.0.113.10", ts: <45 seconds ago>}
    RE->>RE: IP changed + within 60s window\n→ replay_detected = True\nrisk += 0.35 (IP drift)
    RE-->>App: HTTP 409 Conflict\n{detail: "replay_detected"}
    App-->>Attacker: HTTP 403 Forbidden\n{error: {code: "token_replay"}}
    Note over Attacker: Request blocked. JTI\nnot added to revocation yet\n(replay detection is stateless check)
```

---

## Request Lifecycle — High Risk / Step-Up Required

```mermaid
sequenceDiagram
    autonumber
    participant Client
    participant App as Django/Spring App
    participant RE as Risk Engine
    participant GW as Policy Gateway
    participant OPA

    Note over Client: Valid token but accessing from new geo
    Client->>App: POST /v1/payments/transfer\nX-Geo: GB-LDN (was US-CA)
    App->>RE: POST /v1/risk/evaluate\n{geo: "GB-LDN", endpoint.sensitivity: 4}
    RE->>RE: score_risk()\nbase 0.10 + geo_drift 0.20 + sensitivity 0.15 = 0.45\n(IP also changed: +0.35) = 0.80
    RE-->>App: {risk_score: 0.80, trust_score: 0.20}
    App->>GW: POST /v1/policy/decision\n{risk_score: 0.80, resource.sensitivity: 4}
    GW->>OPA: POST /v1/data/aztdp/authz\n{input: {context.risk_score: 0.80}}
    OPA->>OPA: risk >= 0.65 AND sensitivity >= 4\n→ decision = "stepup"
    OPA-->>GW: {decision: "stepup", reason: {rule: "high_risk_stepup"}}
    GW-->>App: {decision: {decision: "stepup"}}
    App-->>Client: HTTP 401\n{error: {code: "STEP_UP_REQUIRED",\n  details: {methods: ["otp","webauthn"],\n  expires_in_seconds: 300}}}
```

---

## Trust Boundary Map

```
═══════════════════════════════════════════════════════════════════
  EXTERNAL ZONE (untrusted)
  ┌─────────────────────────────────────┐
  │  Client Browser / API Consumer      │
  │  Adversary (same attack surface)    │
  └─────────────────────────────────────┘
                    │
                    │ HTTPS (TLS)
                    │
═══════════════ BOUNDARY 1 ════════════════════════════════════════
  APP ZONE (partially trusted — JWT-verified identity only)
  ┌─────────────────────────────────────┐
  │  Django App :8010                   │
  │  Spring Boot App :8011              │
  └─────────────────────────────────────┘
         │                   │
         │ HTTP (internal)    │ HTTP (internal)
         │                   │
═══════════════ BOUNDARY 2 ══════════╦═══ BOUNDARY 3 ═════════════
  RISK ZONE                          ║  POLICY ZONE
  ┌──────────────────────┐           ║  ┌──────────────────────┐
  │  Risk Engine :8001   │           ║  │  Policy Gateway :8000 │
  │  Anomaly Svc :8002   │           ║  │  OPA :8181            │
  └──────────────────────┘           ║  └──────────────────────┘
         │                           ║
         │ Redis protocol            ║
         ▼                           ║
  ┌──────────────────────┐           ║
  │  Redis :6379         │           ║
  │  (session state)     │ ──────────╝ (revocation check)
  └──────────────────────┘
═══════════════ BOUNDARY 4 ════════════════════════════════════════
  IDENTITY ZONE (trusted, external)
  ┌─────────────────────────────────────┐
  │  Keycloak :8080                     │
  │  JWKS endpoint (RS256 keys)         │
  └─────────────────────────────────────┘
═══════════════════════════════════════════════════════════════════
  PERSISTENCE ZONE
  ┌─────────────────────────────────────┐
  │  PostgreSQL :5432                   │
  │  (audit_events, risk_evaluations,   │
  │   policy_decisions, sessions)       │
  └─────────────────────────────────────┘
```
