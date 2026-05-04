import numpy as np

from anomaly_service.feature_engineering import FEATURE_ORDER, build_feature_vector, synthetic_baseline


def test_feature_order_is_eleven():
    assert len(FEATURE_ORDER) == 11


def test_build_vector_shape_and_interactions():
    payload = {
        "hour_of_day": 14,
        "day_of_week": 1,
        "endpoint_sensitivity": 4,
        "ip_changed": True,
        "geo_changed": True,
        "ua_changed": False,
        "request_rate_1m": 5.0,
        "time_since_last_request": 30.0,
    }
    X = build_feature_vector(payload)
    assert X.shape == (1, 11)
    assert X[0, 7] == 4 * 1   # sensitivity * geo_changed
    assert X[0, 8] == 4 * 1   # sensitivity * ip_changed
    assert X[0, 10] == 1      # simultaneous geo+ip change


def test_time_since_capped_at_3600():
    payload = {
        "hour_of_day": 0, "day_of_week": 0, "endpoint_sensitivity": 1,
        "ip_changed": False, "geo_changed": False, "ua_changed": False,
        "request_rate_1m": 0.0, "time_since_last_request": 9999.0,
    }
    X = build_feature_vector(payload)
    assert X[0, 9] == 3600.0


def test_synthetic_baseline_shape():
    X = synthetic_baseline(500, random_state=1)
    assert X.shape == (500, 11)
    assert X.dtype == np.float64
