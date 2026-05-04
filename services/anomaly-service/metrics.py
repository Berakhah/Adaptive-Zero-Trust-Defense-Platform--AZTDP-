from prometheus_client import Counter, Gauge, Histogram

ANOMALY_SCORES = Histogram(
    "aztdp_anomaly_scores_histogram",
    "Distribution of anomaly scores",
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

ANOMALY_FLAGGED = Counter(
    "aztdp_anomaly_flagged_total",
    "Number of requests flagged as anomalous (score > threshold)",
)

INFERENCE_LATENCY = Histogram(
    "aztdp_model_inference_latency_seconds",
    "Latency of single-request anomaly model inference",
    buckets=(0.0005, 0.001, 0.002, 0.005, 0.01, 0.025, 0.05, 0.1),
)

MODEL_VERSION = Gauge(
    "aztdp_model_version_info",
    "Loaded anomaly model version (1=loaded)",
    labelnames=("version",),
)

# ── Training evaluation metrics (P3.4) ──────────────────────────────────────

MODEL_ANOMALY_RATE = Gauge(
    "aztdp_model_training_anomaly_rate",
    "Fraction of training samples flagged as anomalous post-fit",
    labelnames=("version",),
)

MODEL_SCORE_P50 = Gauge(
    "aztdp_model_score_p50",
    "Median anomaly score on training set",
    labelnames=("version",),
)

MODEL_SCORE_P95 = Gauge(
    "aztdp_model_score_p95",
    "95th-percentile anomaly score on training set",
    labelnames=("version",),
)

MODEL_SCORE_P99 = Gauge(
    "aztdp_model_score_p99",
    "99th-percentile anomaly score on training set",
    labelnames=("version",),
)

MODEL_PRECISION = Gauge(
    "aztdp_model_holdout_precision",
    "Precision on 20% holdout set (anomalous label = score >= threshold)",
    labelnames=("version",),
)

MODEL_RECALL = Gauge(
    "aztdp_model_holdout_recall",
    "Recall on 20% holdout set (anomalous label = score >= threshold)",
    labelnames=("version",),
)

MODEL_TRAINING_SAMPLES = Gauge(
    "aztdp_model_training_samples_total",
    "Number of samples used for the most recent training run",
    labelnames=("version",),
)
