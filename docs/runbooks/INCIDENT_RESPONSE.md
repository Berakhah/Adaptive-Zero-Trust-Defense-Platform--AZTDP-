# Incident Response Runbook

How to investigate suspected attacks against AZTDP. All queries run against the forensics service (`http://localhost:8004`) or directly against PostgreSQL.

---

## 1. Token replay

**Symptom:** spike in `aztdp_replay_detected_total` Prometheus counter, or user reports unexpected 403 with body `{"error": {"code": "token_replay"}}`.

### Step 1 — Find the affected token + sessions

```sql
SELECT token_jti_hash, COUNT(*) AS replay_count, MIN(occurred_at) AS first, MAX(occurred_at) AS last
FROM audit_events
WHERE event_type = 'risk_eval'
  AND payload->'reasons' @> '[{"code": "IP_GEO_DRIFT"}]'
  AND occurred_at >= now() - interval '1 hour'
GROUP BY token_jti_hash
ORDER BY replay_count DESC;
```

### Step 2 — Get the full session timeline

```bash
curl http://localhost:8004/v1/forensics/replay/<session_id> | jq
```

Look at the `timeline[].delta_ms` to see request cadence. Replay attacks typically show two requests within < 1 s from different IPs.

### Step 3 — Force-revoke the token

```bash
curl -X POST http://localhost:8000/v1/tokens/revoke \
  -H "Content-Type: application/json" \
  -d '{"token_jti_hash": "<hash>", "reason": "incident_response", "source": "manual"}'
```

---

## 2. Geographic drift / impossible travel

**Symptom:** alert from the Attack Detection dashboard, or session showing rapid geo changes.

```sql
SELECT session_id, user_id, ip_first, geo_first, ip_last, geo_last,
       last_seen_at - started_at AS duration
FROM sessions
WHERE geo_first != geo_last
  AND last_seen_at - started_at < interval '5 minutes'
  AND started_at >= now() - interval '24 hours'
ORDER BY started_at DESC;
```

If `duration` is short and `geo_first` ≠ `geo_last`, it's likely a stolen token. Revoke as in Step 3 above.

---

## 3. Anomaly burst (request flood)

**Symptom:** spike in `aztdp_anomaly_flagged_total`, or scores clustering near 1.0 in the Risk Scores dashboard.

```sql
SELECT user_id, COUNT(*) AS request_count, MAX(anomaly_score) AS max_anom
FROM risk_evaluations
WHERE anomaly_score >= 0.7
  AND evaluated_at >= now() - interval '15 minutes'
GROUP BY user_id
ORDER BY request_count DESC;
```

Cross-check with `request_rate_1m` from the Redis sliding window (`user:request_rate:<user_id>`).

---

## 4. Privilege escalation attempt

**Symptom:** `aztdp_policy_decisions_total{decision="deny"}` spike, particularly on `/v1/admin/*` paths.

```sql
SELECT user_id, endpoint_path, COUNT(*) AS attempts
FROM policy_decisions
WHERE decision = 'deny'
  AND endpoint_path LIKE '/v1/admin/%'
  AND decided_at >= now() - interval '1 hour'
GROUP BY user_id, endpoint_path
ORDER BY attempts DESC;
```

Investigate any user with > 3 attempts in 5 min.

---

## 5. Single-incident reconstruction

For a specific request that was denied, get the full ±5 s window:

```bash
curl http://localhost:8004/v1/forensics/incidents/<request_id> | jq
```

Returns the policy decision, risk evaluation, and every other audit event in the surrounding window — useful for understanding what context the policy engine had.

---

## 6. Verifying the system itself is healthy

```bash
# Check decision rate
curl -s http://localhost:9090/api/v1/query?query=sum\(rate\(aztdp_policy_decisions_total\[1m\]\)\)

# Check replay detection is firing
curl -s http://localhost:9090/api/v1/query?query=increase\(aztdp_replay_detected_total\[1h\]\)

# Verify all services healthy
for url in http://localhost:8000 http://localhost:8001 http://localhost:8002 \
           http://localhost:8003 http://localhost:8004 http://localhost:8010; do
  echo "$url/health: $(curl -sf $url/health | jq -c)"
done
```

---

## Common false positives

| Pattern                                    | Likely cause                                                                |
|--------------------------------------------|-----------------------------------------------------------------------------|
| User 's IP changes every few minutes      | Mobile network handoff (cellular ↔ Wi-Fi). Lengthen `AZTDP_REPLAY_WINDOW_SECONDS` |
| User-Agent hash changes mid-session        | Browser auto-update or App version bump. Acceptable if low frequency        |
| Geo changes between adjacent regions       | VPN, DNS-based geo lookups disagreeing. Investigate before action           |
| High anomaly score on a brand-new account  | Cold-start: model has no baseline. Will normalise after ~50 requests        |

---

## Escalation

If the queries above show signs of a real attack and you cannot contain it via revocation, escalate to:

1. **Security on-call** — page via your usual channel
2. **Disable the affected user account in Keycloak** (last resort — kills all their sessions)
3. **Tighten OPA policy temporarily** — push a rule that denies on the suspect's user_id or endpoint
