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

EVENTS_INGESTED = Counter(
    "aztdp_telemetry_events_ingested_total",
    "Number of telemetry events written to audit_events",
    labelnames=("event_type",),
)

INGEST_LATENCY = Histogram(
    "aztdp_telemetry_ingest_latency_seconds",
    "Time spent persisting an event",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

INGEST_ERRORS = Counter(
    "aztdp_telemetry_ingest_errors_total",
    "Errors writing to the database",
    labelnames=("event_type",),
)


def render_latest() -> bytes:
    """Prometheus exposition text, aggregated across workers when multiprocess."""
    if _MULTIPROC_DIR:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry)
    return generate_latest()
