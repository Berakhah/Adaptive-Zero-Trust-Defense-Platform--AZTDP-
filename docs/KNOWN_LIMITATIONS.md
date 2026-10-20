# Known Limitations

What AZTDP does not do, or does with a stated trade-off. Each item says whether it is **accepted** (a product decision), **open** (needs an owner decision) or **measured** (a number from [PERFORMANCE_BASELINE.md](PERFORMANCE_BASELINE.md)).

## Security behavior

| Limitation | Status | Detail |
|---|---|---|
| **Anomaly scoring fails open** | open | If the anomaly service errors or exceeds the risk-engine's timeout (`ANOMALY_TIMEOUT` in `services/risk-engine/anomaly_client.py`, 150 ms), the request is still scored, but without the ML signal, and no error is returned. Every fallback is counted in `aztdp_anomaly_calls_total{outcome}`, logged, and alerted on (`AnomalyScoringDegraded`, >5% of calls for 5 min). Whether high-sensitivity endpoints should fail closed instead is an owner decision. |
| **Replay check is not atomic** | accepted | The risk-engine's read-then-write of a token's last-seen state is not atomic. Two concurrent requests on one token can both pass the replay check. Revisit if it matters in practice. |
| **IP change inside the replay window is a replay** | accepted | A token whose client IP changes within `AZTDP_REPLAY_WINDOW_SECONDS` (60 s) is denied (409 at the risk-engine, 403 to the client). A legitimate mobile client switching networks is denied. |
| **Replay window is 60 s, not the token lifetime** | accepted | An attacker who waits past the window avoids the replay flag, but IP and geo drift still raise the risk score. |
| **Step-up TOTP is self-hosted** | open | Step-up works (Redis-backed challenges, attempt limit, per-user secret, bound tokens) but there is no enrollment UI and no WebAuthn. Whether to keep it or delegate step-up to Keycloak (`acr_values`) is an owner decision. |
| **Client IP and geo come from headers** | accepted | `X-Client-Ip` and `X-Geo` are trusted only when the request arrives from the pinned nginx address (`172.28.0.10`), and nginx overwrites them. Anything that can reach the apps without going through nginx can spoof them. Keep the apps unpublished. |

## Performance (measured, not met)

Both provisional SLOs (p99 < 250 ms, errors < 0.1%) are missed in every run; the target request rate is undefined, so the SLOs are provisional. See [PERFORMANCE_BASELINE.md](PERFORMANCE_BASELINE.md). Numbers are from a shared development host, not a reference host.

| Limitation | Status | Detail |
|---|---|---|
| **Anomaly scoring is the throughput ceiling** | measured | One scoring call takes about 35 ms and the service is deliberately single-worker, so it tops out near 29 req/s. |
| **Django concurrency** | measured | Four sync workers cap concurrency; `/health` queued behind real requests and took 6.7 s at 200 users. |
| **Fail-closed denials under overload** | measured | 403s appear under load, probably risk or policy call timeouts. The denial reasons were not captured, so this is inferred. |

## Operations

| Limitation | Status | Detail |
|---|---|---|
| **Single region, single node** | accepted | Docker Compose only (owner decision). No replication for Redis or PostgreSQL, no automatic failover. |
| **Redis is not backed up** | accepted | Redis holds short-lived state (replay, rate limits, step-up). Revocations are durable in PostgreSQL and resynced to Redis. See [BACKUP_RESTORE.md](runbooks/BACKUP_RESTORE.md). |
| **Self-signed TLS by default** | open | `infra/nginx/gen-certs.sh` produces a self-signed certificate. Replace it with a CA-issued one before go-live ([GO_LIVE_CHECKLIST.md](GO_LIVE_CHECKLIST.md)). |
| **Alert receiver is a webhook** | accepted | Alertmanager posts to the URL in `ALERT_WEBHOOK_URL`. Nothing verifies that the receiver is wired to a pager until you test it. |

## Not in scope

Kubernetes and Helm manifests are not maintained (Compose-only decision). PCI and GDPR are out of scope; the compliance target is SOC 2 Type II.
