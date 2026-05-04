from prometheus_client import Counter, Histogram

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
