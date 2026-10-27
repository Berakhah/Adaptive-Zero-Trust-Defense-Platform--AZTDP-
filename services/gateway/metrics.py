import os

# Multi-worker uvicorn: when PROMETHEUS_MULTIPROC_DIR is set, every worker writes
# its metrics there and /metrics aggregates them. The directory must exist before
# the first metric is created (tmpfs starts empty on every container start).
_MULTIPROC_DIR = os.getenv("PROMETHEUS_MULTIPROC_DIR")
if _MULTIPROC_DIR:
    os.makedirs(_MULTIPROC_DIR, exist_ok=True)

from prometheus_client import (  # noqa: E402
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)

POLICY_DECISIONS = Counter(
    "aztdp_policy_decisions_total",
    "Policy decisions emitted by the gateway",
    labelnames=("decision",),
)

OPA_LATENCY = Histogram(
    "aztdp_opa_request_latency_seconds",
    "Latency of calls to OPA",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

REVOCATIONS = Counter(
    "aztdp_token_revocations_total",
    "Tokens revoked through the gateway",
)

TELEMETRY_DROPPED = Counter(
    "aztdp_telemetry_dropped_total",
    "Audit telemetry events dropped after retries were exhausted",
    labelnames=("service", "reason"),
)

TELEMETRY_RETRIES = Counter(
    "aztdp_telemetry_retry_total",
    "Audit telemetry delivery retries",
    labelnames=("service",),
)


def render_latest() -> bytes:
    """Prometheus exposition text, aggregated across workers when multiprocess."""
    if _MULTIPROC_DIR:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry)
    return generate_latest()
