import os

REDIS_URL = os.getenv("AZTDP_REDIS_URL", "")
DB_URL = os.getenv("AZTDP_DB_URL", "")

MODEL_DIR = os.getenv("AZTDP_MODEL_DIR", "/app/models")
# HMAC key that signs/verifies model artifacts. Read at call time by model.py;
# the service refuses to start without it (require_hmac_key, called at startup).
MODEL_HMAC_KEY = os.getenv("AZTDP_MODEL_HMAC_KEY", "")
MODEL_HMAC_MIN_LENGTH = 32
MODEL_VERSION_KEY = os.getenv("AZTDP_MODEL_VERSION_KEY", "anomaly:model:version")

ANOMALY_THRESHOLD = float(os.getenv("AZTDP_ANOMALY_THRESHOLD", "0.7"))
RELOAD_INTERVAL_SECONDS = int(os.getenv("AZTDP_MODEL_RELOAD_INTERVAL", "60"))

REQUEST_RATE_WINDOW_SECONDS = int(os.getenv("AZTDP_REQUEST_RATE_WINDOW", "60"))
REQUEST_RATE_KEY_PREFIX = "user:request_rate:"
TOKEN_LAST_SEEN_KEY_PREFIX = "token:last_seen:"

COLD_START_SAMPLES = int(os.getenv("AZTDP_COLD_START_SAMPLES", "10000"))
N_ESTIMATORS = int(os.getenv("AZTDP_N_ESTIMATORS", "100"))
CONTAMINATION = float(os.getenv("AZTDP_CONTAMINATION", "0.05"))
RANDOM_STATE = int(os.getenv("AZTDP_RANDOM_STATE", "42"))


def require_hmac_key() -> str:
    """Fail closed: return the model-signing key or raise if missing/weak."""
    key = MODEL_HMAC_KEY
    if not key:
        raise RuntimeError(
            "AZTDP_MODEL_HMAC_KEY is required: the anomaly service will not "
            "load or write unsigned model artifacts"
        )
    if len(key) < MODEL_HMAC_MIN_LENGTH:
        raise RuntimeError(
            f"AZTDP_MODEL_HMAC_KEY must be at least {MODEL_HMAC_MIN_LENGTH} characters"
        )
    return key
