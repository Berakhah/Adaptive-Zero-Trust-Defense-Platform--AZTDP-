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

RISK_SCORES = Histogram(
    "aztdp_risk_scores_histogram",
    "Distribution of risk scores",
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

REPLAY_DETECTED = Counter(
    "aztdp_replay_detected_total",
    "Replay events detected",
)

EVAL_LATENCY = Histogram(
    "aztdp_risk_eval_latency_seconds",
    "Risk evaluation latency end-to-end",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
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
