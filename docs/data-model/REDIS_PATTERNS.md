# AZTDP Redis Key Patterns

Redis is used for two distinct concerns: **session state** (token tracking for risk scoring) and **operational caching** (revocation, anomaly model version, request rate windows). These are kept on the same Redis instance in development with logical separation via key prefixes. In production they should be on separate Redis databases or instances to allow independent eviction policies.

---

## Connection Configuration

| Setting | Value | Notes |
|---|---|---|
| URL env var | `AZTDP_REDIS_URL` | Format: `redis://[password@]host:port/db` |
| Default (dev) | `redis://redis:6379/0` | No auth in dev |
| Max memory | 256 MB | `maxmemory 256mb` in `infra/redis/redis.conf` |
| Eviction policy | `allkeys-lru` | Safe for cache-only workloads; stale session state expires naturally |
| Persistence | `save 900 1` + `save 300 10` | RDB snapshots; not AOF — data is reconstructable from app state |

---

## Key Catalog

### 1. `token:last_seen:{token_jti_hash}`

| Property | Value |
|---|---|
| **Writer** | `services/risk-engine/storage.py` (`ReplayStore.set_last_seen`) |
| **Reader** | `services/risk-engine/storage.py` (`ReplayStore.get_last_seen`) |
| **Reader (Phase 7)** | `services/anomaly-service/feature_engineering.py` (read-only) |
| **Type** | String (JSON-encoded) |
| **TTL** | `AZTDP_TOKEN_TTL_SECONDS` (default: 1800s = 30 min) |
| **Key count** | One per active JWT; bounded by concurrent active sessions |

**Value schema:**
```json
{
  "ip":  "203.0.113.10",
  "ua":  "sha256hex_of_user_agent_string",
  "geo": "US-CA",
  "ts":  1720000000.123
}
```

**Purpose:** Enables per-token behavioral drift detection. On each request, the risk engine compares the current `{ip, ua, geo}` against the stored values. Differences add to the risk score. `ts` is a Unix timestamp used to determine if the IP change happened within the replay window (60 seconds).

**Operational notes:**
- The key is set *after* scoring, not before — the first request from any token always has no history (`last_seen=None`) and receives only the base risk score.
- TTL matches the access token lifetime so expired tokens naturally purge their state.
- The anomaly service reads this key (Phase 7) but never writes to it. This avoids write-write contention.

**Replay window interaction:**
```
Request A: ip=10.0.0.1, ts=T
SET token:last_seen:{hash} = {ip:10.0.0.1, ts:T}  TTL=1800s

Request B (45s later): ip=10.0.0.2
GET token:last_seen:{hash} → {ip:10.0.0.1, ts:T}
(now - T) = 45s < 60s → replay_detected=True → HTTP 409

Request C (90s after A): ip=10.0.0.2
GET token:last_seen:{hash} → {ip:10.0.0.1, ts:T}
(now - T) = 90s >= 60s → not replay, but ip_drift fires (+0.35)
```

---

### 2. `revocation:{token_jti_hash}` *(Phase 6B)*

| Property | Value |
|---|---|
| **Writer** | `services/gateway/revocation_store.py` (`RevocationStore.revoke`) |
| **Reader** | `services/gateway/revocation_store.py` (`RevocationStore.is_revoked`) |
| **Type** | String (`"1"`) |
| **TTL** | 3600s (1 hour) — configurable, should exceed max access token lifetime |
| **Key count** | One per revoked token; sparse — most sessions are never revoked |

**Value:** A fixed string `"1"` (the key's existence signals revocation; the value is unused).

**Purpose:** Fast O(1) revocation check before OPA is called. The gateway checks this key on every `POST /v1/policy/decision` request. If it exists, the gateway short-circuits and returns `decision=revoke` without calling OPA.

**Current state (Phase 6A baseline):** `RevocationStore` is in-memory only (`services/gateway/revocation_store.py`). Phase 6B replaces it with a Redis-backed implementation mirroring `services/risk-engine/storage.py`:

```python
# Phase 6B implementation pattern (mirrors risk-engine ReplayStore)
if self._redis:
    self._redis.setex(f"revocation:{token_hash}", self.ttl_seconds, "1")
else:
    self._memory[token_hash] = time.time() + self.ttl_seconds
```

**Failure mode:** If Redis is unavailable when checking revocation, the gateway falls back to in-memory (which may be empty after restart). With `FAIL_OPEN=false`, this is acceptable — a worst-case miss means a revoked token might be treated as valid until Redis recovers, which is the same as the current baseline. The token_revocations PostgreSQL table is the authoritative durable record; a recovery job could reload Redis from it (future work).

---

### 3. `user:request_rate:{user_id}` *(Phase 7)*

| Property | Value |
|---|---|
| **Writer** | `services/anomaly-service/feature_engineering.py` |
| **Reader** | `services/anomaly-service/feature_engineering.py` |
| **Type** | Sorted Set (score = Unix timestamp, member = request UUID) |
| **TTL** | 120s (applied via `EXPIRE` on each write) |
| **Key count** | One per active user; auto-expires 120s after last request |

**Purpose:** Sliding window request rate calculation for anomaly feature extraction. The anomaly service uses `ZRANGEBYSCORE` to count requests in the last 60 seconds, then `ZADD` to record the current request, then `EXPIRE 120` to keep the window fresh.

**Operations per request:**
```
ZREMRANGEBYSCORE user:request_rate:{user_id} -inf (now - 60)   # prune old
ZRANGEBYSCORE    user:request_rate:{user_id} (now - 60) +inf    # count
ZADD             user:request_rate:{user_id} {now} {request_id} # record
EXPIRE           user:request_rate:{user_id} 120                # slide window
```

**Why Sorted Set over Counter:** A plain INCR counter with a 60-second expiry would require resetting at arbitrary boundaries, making the sliding window inaccurate. The sorted set approach gives an exact sliding window at the cost of ~50 bytes per entry. With a 60-second window and a maximum of ~10 requests/min for normal users, the set stays small (<10 members per key).

**Max request rate observable:** Bounded by Sorted Set size. At 1000 RPS per user (anomaly flood scenario), the set holds 60,000 entries — about 3MB per key. The anomaly flood detector should fire long before this becomes a concern.

---

### 4. `anomaly:model:version` *(Phase 7)*

| Property | Value |
|---|---|
| **Writer** | `services/anomaly-service/training.py` (after each training run) |
| **Reader** | `services/anomaly-service/model.py` (background thread, every 60s) |
| **Type** | String |
| **TTL** | None (permanent) |
| **Key count** | 1 (singleton) |

**Value example:** `"v1.0"` or `"v1.2"`

**Purpose:** Hot model reload signal. When the training script finishes, it atomically updates this key. The anomaly service's background thread polls every 60 seconds; if the version changed, it reloads the model from disk (`/app/models/isolation_forest_v{version}.pkl`) without restarting the process.

**Atomicity:** `SET anomaly:model:version {new_version}` is atomic in Redis. The model file is written to disk before this key is updated — so readers always see a consistent (version, file) pair. This is a write-once-per-training-run key, so race conditions are not a concern.

---

### 5. `anomaly:features:{user_id}` *(Phase 7, reserved)*

| Property | Value |
|---|---|
| **Writer** | `services/anomaly-service/feature_engineering.py` (planned) |
| **Reader** | `services/anomaly-service/feature_engineering.py` (planned) |
| **Type** | String (JSON-encoded rolling feature window) |
| **TTL** | 3600s |
| **Key count** | One per active user |

**Purpose:** Rolling feature window for online learning and per-user baseline tracking. The anomaly service can store the last N feature vectors for a user to detect drift in their own behavior patterns over time (not just absolute deviation from the population model). This key is reserved for Phase 7 implementation; the exact schema is TBD based on the feature engineering approach chosen.

**Planned value schema:**
```json
{
  "samples": [
    [14, 1, 2, 0, 0, 0, 3.0, 0.0, 0.0, 120.0, 0],
    [15, 1, 2, 0, 0, 0, 2.0, 0.0, 0.0, 95.0, 0]
  ],
  "updated_at": 1720000000.0
}
```
Each inner array is a 11-element feature vector in the canonical feature order.

---

## Key Namespace Summary

```
token:last_seen:{sha256_jti_hash}     ← risk-engine writes; risk-engine + anomaly reads
revocation:{sha256_jti_hash}          ← gateway writes; gateway reads         [Phase 6B]
user:request_rate:{user_id}           ← anomaly writes + reads                [Phase 7]
anomaly:model:version                 ← training writes; anomaly service reads [Phase 7]
anomaly:features:{user_id}            ← anomaly writes + reads                [Phase 7]
```

---

## TTL Reference

| Key Pattern | TTL | Rationale |
|---|---|---|
| `token:last_seen:*` | 1800s | Matches Keycloak access token lifetime; auto-purges expired token state |
| `revocation:*` | 3600s | 2× access token lifetime; ensures revocations outlive any valid token |
| `user:request_rate:*` | 120s | Sliding window is 60s; 120s TTL gives a full window of head-room |
| `anomaly:model:version` | none | Permanent; version number must survive Redis restarts |
| `anomaly:features:*` | 3600s | Long enough to capture a typical work session's baseline |

---

## Memory Sizing

Assumptions for production capacity planning:
- 10,000 concurrent active sessions
- Average 5 revocations per hour
- 5,000 active users generating request rates

| Key type | Count | Size per key | Total |
|---|---|---|---|
| `token:last_seen:*` | 10,000 | ~200 bytes | ~2 MB |
| `revocation:*` | 50 (5/hr × 1hr TTL) | ~80 bytes | ~4 KB |
| `user:request_rate:*` | 5,000 | ~500 bytes (10 members × 50 bytes) | ~2.5 MB |
| `anomaly:*` | 5,001 | ~300 bytes avg | ~1.5 MB |
| **Total** | | | **~6 MB** |

Well within the 256 MB `maxmemory` limit. `allkeys-lru` eviction means Redis will evict the least-recently-used keys if memory pressure occurs — this is safe because all AZTDP keys can be reconstructed from the next request.

---

## Development vs. Production Notes

| Concern | Dev (docker-compose) | Production |
|---|---|---|
| Auth | None (`requirepass ""`) | Set `requirepass` or use ACLs |
| Persistence | RDB snapshots (`save 900 1`) | AOF for revocation durability, or skip persistence (reconstructable) |
| Separate databases | All in db 0 | Consider db 0 for session state, db 1 for revocation, db 2 for anomaly |
| TLS | None | TLS between services in K8s (use `rediss://` URL scheme) |
| Replication | Single node | Redis Sentinel or Redis Cluster for HA |
