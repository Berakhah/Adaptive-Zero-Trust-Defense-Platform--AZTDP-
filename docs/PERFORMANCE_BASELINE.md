# Performance baseline

Measured 2026-10-20 with `scripts/load/locustfile.py` against the compose stack
(base file + `docker-compose.dev.yml`, dev Keycloak realm), through nginx -> Django ->
risk-engine -> anomaly-service + gateway -> OPA. See `scripts/load/README.md` for how to run it.

## SLOs (PROVISIONAL - owner has not agreed these numbers)

| Objective | Target |
|---|---|
| End-to-end p99 latency | < 250 ms at the target request rate |
| Error rate | < 0.1 % |

The plan requires agreeing these with the owner before anything gates on them. The
**target request rate is not defined yet**, and the SLO is meaningless without it.
`AZTDP_ENFORCE_SLO=1` makes the load test exit non-zero when they are missed; leave it
off in CI until the numbers are signed off.

## Test conditions (read before trusting the numbers)

- Host: Docker Desktop on Windows 11, VM with 22 CPUs / ~8 GB RAM. **Other, unrelated
  compose stacks were running on the same Docker host**, so absolute numbers are indicative
  and not a reference-host result.
- Load generator: one locust container on the compose network (it warned about >90 % CPU
  in the saturated runs, so treat the saturated figures as a lower bound on capacity).
- Run length is **3 minutes, not the plan's 5**: access tokens live 5 minutes and the
  token pre-fetch takes ~45-50 s, so a 5-minute run would fail on expired tokens.
- Mix: 90 % `NormalUser` (0.5-2 s think time, authenticated reads), 10 % `AttackUser`
  (0.1-0.5 s think time). 200 users therefore offer roughly 200 req/s.
- Limits in effect: the ones in `docker-compose.yml` (Django 1.5 CPU / 512 MB; risk-engine,
  gateway 1 CPU / 384 MB; anomaly-service 1 CPU / 768 MB, pinned to 1 worker).

## Results

| Run | Config | Users | Throughput | p50 | p95 | p99 | Error rate |
|---|---|---|---|---|---|---|---|
| A. Offered load near capacity | committed compose (Django: 4 sync gunicorn workers) | 15 | 14.0 req/s | 110 ms | 270 ms | 820 ms | 0.12 % (2 x 403) |
| B. Overload | committed compose | 200 | 23.2 req/s | 6,800 ms | 8,000 ms | 11,000 ms | 0.41 % (14 x 403, 4 x 401) |
| C. Overload, experiment | Django `GUNICORN_CMD_ARGS="--worker-class gthread --threads 8"` | 200 | 59.7 req/s | 1,600 ms | 5,700 ms | 9,100 ms | 2.9 % (320 x 403) |

**Neither provisional SLO is met in any run.** Run A is the closest and misses both
(p99 820 ms, 0.12 % errors). Run C is an experiment only; it is not committed.

### Resource usage (run B)

No container was close to its CPU limit. Peak memory stayed well inside the limits
(Keycloak ~470 MiB of 1 GiB, Django ~160 MiB of 512 MiB, gateway/risk-engine/forensics
~120-135 MiB of 256-384 MiB, anomaly-service ~110 MiB of 768 MiB). Every service averaged
under 4 % CPU. The system is latency-bound by waiting, not compute-bound.

## Where the time goes

Unloaded, one authenticated `GET /v1/payments/1` costs ~75-100 ms end to end, against ~3-5 ms
for any service's `/health`. Measured per hop, sequentially, from inside the network:

| Hop | Measured |
|---|---|
| gateway `/v1/policy/decision` (-> OPA) | ~8 ms p50 |
| risk-engine `/v1/risk/evaluate` | ~157 ms p50 (p95 184 ms) |
| anomaly-service `/v1/anomaly/score`, sequential | ~35 ms p50 (p95 66 ms) |
| anomaly-service, 16 concurrent callers | ~29 req/s total, p50 489 ms, p95 816 ms |

Findings:

1. **anomaly-service is the throughput ceiling.** One scoring call takes ~35 ms and the
   service is deliberately single-worker (in-process model and scheduler), so it tops out
   at ~29 req/s. Above that, queueing pushes calls past the risk-engine's 150 ms timeout.
2. **Overload silently drops the ML signal.** `services/risk-engine/anomaly_client.py`
   returns `None` on any error (fail-open), so under load requests are scored without the
   anomaly component and nothing surfaces it as a user-visible error. That is a security
   degradation that only shows up in a metric/log, not in the error rate. This needs a
   decision (fail closed for sensitive routes? alert on anomaly-timeout rate?).
3. **Django's 4 sync workers cap concurrency.** Each worker blocks for the whole
   risk + policy round trip, so 4 workers sustain only ~40-50 req/s at 75-100 ms per request,
   and `/health` queues behind them (run B: `/health` p50 6.7 s). Threaded workers (run C)
   raised throughput 2.6x, but the system then fails closed on the next limit (see below).
4. **Fail-closed denials appear under overload.** With `AZTDP_FAIL_OPEN=false`, risk or
   policy calls that exceed their read timeout (0.8 s) become 403s for legitimate users:
   0.12 % at 14 req/s, 2.9 % at 60 req/s. This is the correct failure direction, but it
   is what the error-rate SLO will measure.
5. Connection pooling is **already in place** (`requests.Session` in the policy, risk and
   revocation clients), so the plan's "add Session pooling" suggestion does not apply.

The 403 attribution in finding 4 is inferred from the timeouts and the fail-closed
configuration; the individual denial reasons were not captured in these runs.

## Timeouts (decision needed)

`docker-compose.yml` sets `AZTDP_TIMEOUT_CONNECT=1.0` for django-app; the code default is
`0.2` (`settings.py`). Docker-bridge connects are sub-millisecond, and with 4 sync workers a
1.0 s connect timeout lets one dead dependency hold a worker for a second per request.
**Recommendation: use the code default of 0.2 s** and drop the compose override. Not
changed here because it has not been load-tested and it affects fail-closed behaviour.

## Recommended follow-ups (none applied)

- Agree the target request rate and the SLO numbers with the owner.
- Scale or restructure anomaly scoring (batch/vectorise, run scoring out of the request
  path, or multiple replicas with a shared model) - this is the real ceiling.
- Move Django to threaded or async workers once the above is addressed, and re-measure.
- Surface anomaly-timeout rate as a metric with an alert (finding 2).
- Re-run on the reference host with nothing else running, then set `AZTDP_ENFORCE_SLO=1`
  in CI.

## Incidental fixes made while measuring

- `infra/prometheus/prometheus.yml`: `rule_files` matched `*.yml`, so Prometheus tried to load
  the promtool test file `aztdp.rules.test.yml` as a rule group and crash-looped.
  Now `*.rules.yml` (`scripts/check_prometheus.sh` passes).
- `docker-compose.yml`: the nginx healthcheck never passed (`localhost` resolved to `::1`,
  nginx listens on IPv4 only, and port 80 only redirects to https). It now checks for the
  301 on `127.0.0.1`.
- anomaly-service cold start (10,000 synthetic samples) took 4-9 minutes on this host and
  the service is unhealthy until it finishes; the first start of a stack is slow.
