import pytest
from anomaly_service import config

TEST_HMAC_KEY = "test-model-hmac-key-" + "k" * 24


@pytest.fixture(autouse=True)
def _model_hmac_key(monkeypatch):
    monkeypatch.setattr(config, "MODEL_HMAC_KEY", TEST_HMAC_KEY, raising=False)
