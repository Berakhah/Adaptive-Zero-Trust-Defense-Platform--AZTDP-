from prometheus_client import Counter, Histogram

QUERY_COUNT = Counter(
    "aztdp_forensics_queries_total",
    "Forensics queries served",
    labelnames=("endpoint",),
)

QUERY_LATENCY = Histogram(
    "aztdp_forensics_query_latency_seconds",
    "Forensics query latency",
    labelnames=("endpoint",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)
