from prometheus_client import Counter, Histogram

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
