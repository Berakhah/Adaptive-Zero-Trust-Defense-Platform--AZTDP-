import tempfile
from pathlib import Path

import numpy as np
import pytest

from anomaly_service import config
from anomaly_service.feature_engineering import synthetic_baseline
from anomaly_service.model import AnomalyModel


@pytest.fixture
def trained_model(monkeypatch):
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(config, "MODEL_DIR", tmp)
    model = AnomalyModel()
    X = synthetic_baseline(2000, random_state=42)
    model.fit(X, version="v-test")
    model.save()
    return model, Path(tmp)


def test_model_score_in_unit_range(trained_model):
    model, _ = trained_model
    X = synthetic_baseline(10, random_state=7)
    for row in X:
        score, conf = model.score(row.reshape(1, -1))
        assert 0.0 <= score <= 1.0
        assert 0.0 <= conf <= 1.0


def test_model_save_load_roundtrip(trained_model, monkeypatch):
    _, tmp = trained_model
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp))
    fresh = AnomalyModel()
    assert fresh.load("v-test") is True
    assert fresh.is_loaded
    assert fresh.version == "v-test"


def test_outliers_score_higher(trained_model):
    model, _ = trained_model
    normal = np.array([[14, 2, 2, 0, 0, 0, 1.0, 0, 0, 30.0, 0]])
    extreme = np.array([[3, 6, 5, 1, 1, 1, 50.0, 5, 5, 0.5, 1]])
    s_normal, _ = model.score(normal)
    s_extreme, _ = model.score(extreme)
    assert s_extreme >= s_normal
