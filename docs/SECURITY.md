# AZTDP Security Policy

## Reporting a vulnerability

If you discover a security vulnerability in this codebase, **please do not open a public GitHub issue**. Instead, email the maintainer with:

1. A short description of the issue
2. Reproduction steps or proof-of-concept
3. The component affected (gateway, risk engine, anomaly service, etc.)
4. Your assessment of impact (confidentiality, integrity, availability)

You should expect an acknowledgement within 72 hours.

## Supported versions

This project is a reference architecture. Only the `main` branch is patched.

| Version | Supported |
|---------|-----------|
| main    | ✅        |
| < 0.1.0 | ❌        |

---

## Threat model summary

The full STRIDE analysis lives in `docs/threat-model/THREAT_MODEL.md`. Eight tracked gaps (G-1 … G-8), summarised:

| ID  | Gap                                                        | Status                                |
|-----|------------------------------------------------------------|---------------------------------------|
| G-1 | `X-Client-Ip` / `X-Geo` headers user-controllable          | Documented; mitigated by upstream LB  |
| G-2 | 60 s replay window leaves >60 s reuse undetected           | Accepted (caught by drift scoring)    |
| G-3 | Anomaly service fails open                                 | Accepted (per ADR-6)                  |
| G-4 | OPA bundle has no signature verification                   | Open                                  |
| G-5 | No mTLS between internal services                          | Open (deploy in mesh: Istio/Linkerd)  |
| G-6 | Keycloak realm import has dev secrets                      | Replace before production             |
| G-7 | Telemetry pipeline writes are best-effort, not transactional | Accepted (audit, not authorization)  |
| G-8 | No rate limiting at the gateway tier                       | Open                                  |

---

## Production hardening checklist

Before running this in production:

- [ ] Replace **all** dev passwords (Keycloak admin, PostgreSQL, Grafana, client secrets)
- [ ] Enable mTLS between internal services (service mesh)
- [ ] Front the stack with a verified reverse proxy that strips client-controlled `X-Client-Ip` / `X-Geo` headers and re-emits trustworthy versions
- [ ] Set `AZTDP_FAIL_OPEN=false` everywhere (it's the default — verify)
- [ ] Enable Keycloak realm export to private storage (do not commit `aztdp-realm.json` with prod secrets)
- [ ] Review OPA policy for your endpoint sensitivity map
- [ ] Configure PostgreSQL backups + point-in-time recovery
- [ ] Configure Redis persistence (currently disabled for dev speed)
- [ ] Set Prometheus retention and alerting rules
- [ ] Add WAF / rate limiter at the edge
- [ ] Rotate JWT signing keys via Keycloak's key rotation feature

---

## Cryptographic notes

- JWT validation: **RS256 only**. Other algorithms rejected.
- JWKS cache: 5 min. Key rotation should overlap by ≥10 min.
- Token JTI is hashed (SHA-256) before leaving the app process. Raw JTIs never appear in logs, Redis, or PostgreSQL.
- Revocation TTL: 1 h (configurable via `AZTDP_REVOCATION_TTL_SECONDS`).
- Replay detection window: 60 s (configurable via `AZTDP_REPLAY_WINDOW_SECONDS`).

---

## Audit logging

All policy decisions, risk evaluations, and revocations are persisted to `audit_events` (PostgreSQL) via the telemetry-ingest service. Decision logs are also written to stdout as JSON for collection by log aggregators.

The forensics service exposes:

- `GET /v1/forensics/events` — filterable event search
- `GET /v1/forensics/replay/{session_id}` — full session timeline
- `GET /v1/forensics/incidents/{request_id}` — single-incident detail with ±5 s context

Sample queries are in `docs/runbooks/INCIDENT_RESPONSE.md`.
