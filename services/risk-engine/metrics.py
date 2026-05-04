from prometheus_client import Counter, Histogram

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
