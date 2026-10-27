# AZTDP Load Testing

The load test drives the real request path: Keycloak-issued JWT -> nginx ingress ->
Django authz middleware -> risk-engine + gateway (OPA). It must run **inside the
compose network** (the production profile publishes nothing but ingress, and the
trusted-proxy rules mean external clients cannot assert IP/geo anyway).

## Run (dev stack, no extra host ports)

```bash
# 1. bring the stack up under a throwaway project name. If the ingress host ports
#    clash with something on your machine, add an override file containing
#    `services: { nginx: { ports: !reset [] } }` as a second -f.
docker compose -p aztdp_load --env-file .env.dev -f docker-compose.yml \
  up -d --build postgres db-migrate redis keycloak opa gateway risk-engine \
        anomaly-service telemetry-ingest django-migrate django-app nginx

# 2. run locust in a container attached to the compose network
. ./.env.dev   # for KEYCLOAK_CLIENT_SECRET (dev-only value)
docker run --rm --network aztdp_load_aztdp -v "$PWD/scripts/load:/mnt:ro" \
  -e AZTDP_CLIENT_SECRET="$KEYCLOAK_CLIENT_SECRET" \
  python:3.12-slim sh -c 'pip install -q locust==2.29.0 && \
  locust -f /mnt/locustfile.py --headless -u 200 -r 20 -t 5m --host https://nginx'
```

Note: the base file uses the production Keycloak command (no dev realm). To get the seeded
dev users and password grant, also pass `-f docker-compose.dev.yml` (it re-publishes
ports on loopback; reset them in the override file if they clash).

Environment knobs are documented at the top of `locustfile.py`
(`AZTDP_CLIENT_SECRET` is mandatory; there is deliberately no default).
Set `AZTDP_ENFORCE_SLO=1` to make the run exit non-zero when the SLOs are missed.

## SLOs

Defined (provisionally) in [`docs/PERFORMANCE_BASELINE.md`](../../docs/PERFORMANCE_BASELINE.md):
end-to-end p99 < 250 ms and error rate < 0.1 %, measured on the reference host.

## User mix

- `NormalUser` (weight 90): own login per user, stable user agent, authenticated reads of
  `/v1/payments/[id]` plus a small share of `/health`. Anything but 200 is a failure.
- `AttackUser` (weight 10): user-agent drift on a single token (any non-5xx verdict is fine)
  and a non-admin POST to a sensitivity-5 route (must be 403; an allowed request is reported
  as a failure).

IP/geo drift and token replay are not simulated: nginx overwrites `X-Client-Ip`/`X-Geo`,
Django honours them only from the pinned proxy address, and the risk engine's replay rule
needs a changing client IP.
