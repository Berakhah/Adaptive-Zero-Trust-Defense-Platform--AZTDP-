import json
import time
from typing import Any, Dict, Optional

import numpy as np

from . import config

FEATURE_ORDER = [
    "hour_of_day",
    "day_of_week",
    "endpoint_sensitivity",
    "ip_changed",
    "geo_changed",
    "ua_changed",
    "request_rate_1m",
    "sensitivity_x_geo_change",
    "sensitivity_x_ip_change",
    "time_since_last_request",
    "simultaneous_geo_ip_change",
]


def build_feature_vector(payload: Dict[str, Any], redis_client=None) -> np.ndarray:
    """Convert the API payload (plus Redis state) into the 11-feature vector."""
    sensitivity = int(payload.get("endpoint_sensitivity", 1))
    ip_changed = 1 if payload.get("ip_changed") else 0
    geo_changed = 1 if payload.get("geo_changed") else 0
    ua_changed = 1 if payload.get("ua_changed") else 0

    request_rate = float(payload.get("request_rate_1m") or 0.0)
    time_since = float(payload.get("time_since_last_request") or 0.0)

    user_id = payload.get("user_id")
    token_hash = payload.get("token_jti_hash")

    if redis_client is not None:
        if user_id and (payload.get("request_rate_1m") is None):
            request_rate = _compute_request_rate(redis_client, user_id)
        if token_hash and (payload.get("time_since_last_request") is None):
            time_since = _compute_time_since(redis_client, token_hash)

    time_since = min(time_since, 3600.0)

    features = [
        int(payload.get("hour_of_day", 0)),
        int(payload.get("day_of_week", 0)),
        sensitivity,
        ip_changed,
        geo_changed,
        ua_changed,
        request_rate,
        sensitivity * geo_changed,
        sensitivity * ip_changed,
        time_since,
        1 if (ip_changed and geo_changed) else 0,
    ]
    return np.asarray(features, dtype=float).reshape(1, -1)


def record_request(redis_client, user_id: str) -> None:
    """Push the current timestamp into the user's sliding-window sorted set."""
    if redis_client is None or not user_id:
        return
    now = time.time()
    key = f"{config.REQUEST_RATE_KEY_PREFIX}{user_id}"
    try:
        pipe = redis_client.pipeline()
        pipe.zadd(key, {str(now): now})
        pipe.zremrangebyscore(key, 0, now - config.REQUEST_RATE_WINDOW_SECONDS)
        pipe.expire(key, config.REQUEST_RATE_WINDOW_SECONDS * 2)
        pipe.execute()
    except Exception:
        return


def _compute_request_rate(redis_client, user_id: str) -> float:
    key = f"{config.REQUEST_RATE_KEY_PREFIX}{user_id}"
    try:
        now = time.time()
        cutoff = now - config.REQUEST_RATE_WINDOW_SECONDS
        return float(redis_client.zcount(key, cutoff, now))
    except Exception:
        return 0.0


def _compute_time_since(redis_client, token_hash: str) -> float:
    key = f"{config.TOKEN_LAST_SEEN_KEY_PREFIX}{token_hash}"
    try:
        raw = redis_client.get(key)
        if not raw:
            return 0.0
        data = json.loads(raw)
        last_ts = float(data.get("ts") or 0)
        if last_ts <= 0:
            return 0.0
        return max(0.0, time.time() - last_ts)
    except Exception:
        return 0.0


def synthetic_baseline(n: int, random_state: Optional[int] = None) -> np.ndarray:
    """Generate a synthetic baseline of normal request feature vectors."""
    rng = np.random.default_rng(random_state)
    hour = rng.normal(13, 3, n).clip(0, 23).astype(int)
    dow = rng.integers(0, 5, n)
    sens = rng.choice([1, 2, 3, 4, 5], size=n, p=[0.2, 0.5, 0.15, 0.1, 0.05])
    ip_changed = rng.choice([0, 1], size=n, p=[0.95, 0.05])
    geo_changed = rng.choice([0, 1], size=n, p=[0.97, 0.03])
    ua_changed = rng.choice([0, 1], size=n, p=[0.98, 0.02])
    rate = rng.exponential(2.0, n).clip(0, 30)
    sens_geo = sens * geo_changed
    sens_ip = sens * ip_changed
    time_since = rng.exponential(120.0, n).clip(0, 3600)
    simul = ((ip_changed == 1) & (geo_changed == 1)).astype(int)
    return np.column_stack(
        [hour, dow, sens, ip_changed, geo_changed, ua_changed, rate, sens_geo, sens_ip, time_since, simul]
    ).astype(float)
