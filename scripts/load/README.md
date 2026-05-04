# AZTDP Load Testing

## Quick start

```bash
pip install locust==2.29.0
locust -f scripts/load/locustfile.py \
       --host http://localhost:8010 \
       --users 100 --spawn-rate 10 --run-time 5m \
       --headless --html report.html
```

## SLOs (validated by the script's `_print_slo_report` listener)

| Metric                  | Target          |
|-------------------------|-----------------|
| p95 response time       | < 200 ms        |
| Replay detection rate   | > 99 %          |
| False positive rate     | < 0.1 %         |
| Throughput @ 100 conc.  | > 200 RPS       |

Replay detection rate and FPR are computed from Prometheus counters
(`aztdp_replay_detected_total`, `aztdp_policy_decisions_total`) over the run window.

## User mix

- `NormalUser` (weight=80): stable IP/UA/geo, light request load — represents legitimate traffic.
- `AttackUser` (weight=20): rotates through token replay, geo drift, and privilege escalation patterns.
