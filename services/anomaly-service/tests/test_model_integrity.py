import logging

import numpy as np
import pytest

from anomaly_service import config
from anomaly_service.feature_engineering import FEATURE_ORDER
from anomaly_service.model import AnomalyModel, start_hot_reload

N_FEATURES = len(FEATURE_ORDER)


@pytest.fixture
def fitted_model(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(config, "MODEL_HMAC_KEY", "k" * 32, raising=False)
    m = AnomalyModel()
    m.fit(np.random.RandomState(0).rand(200, N_FEATURES), "v1")
    return m


def test_tampered_model_is_rejected(fitted_model, caplog):
    p = fitted_model.save()
    p.write_bytes(p.read_bytes() + b"x")
    fresh = AnomalyModel()
    with caplog.at_level(logging.ERROR):
        assert fresh.load("v1") is False and not fresh.is_loaded
    assert "model_signature_invalid" in caplog.text


def test_unsigned_model_is_rejected(fitted_model):
    p = fitted_model.save()
    p.with_name(p.name + ".sig").unlink()
    assert AnomalyModel().load("v1") is False


def test_wrong_key_is_rejected(fitted_model, monkeypatch):
    fitted_model.save()
    monkeypatch.setattr(config, "MODEL_HMAC_KEY", "z" * 32)
    assert AnomalyModel().load("v1") is False


def test_valid_roundtrip(fitted_model):
    p = fitted_model.save()
    assert p.with_name(p.name + ".sig").exists()
    m = AnomalyModel()
    assert m.load("v1") and m.is_loaded


def test_joblib_not_called_on_unverified_file(fitted_model, monkeypatch):
    import joblib

    p = fitted_model.save()
    p.write_bytes(p.read_bytes() + b"x")

    def boom(*a, **k):
        raise AssertionError("joblib.load called on unverified data")

    monkeypatch.setattr(joblib, "load", boom)
    assert AnomalyModel().load("v1") is False


@pytest.mark.parametrize("bad", ["../../etc/passwd", "", None, "v1/../x", "1.0", "v1\n"])
def test_bad_version_rejected(fitted_model, bad):
    assert AnomalyModel().load(bad) is False


def test_save_rejects_bad_version(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    m = AnomalyModel()
    m.fit(np.random.RandomState(0).rand(50, N_FEATURES), "../evil")
    with pytest.raises(ValueError):
        m.save()


def test_save_leaves_no_temp_files(fitted_model, tmp_path):
    fitted_model.save()
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "isolation_forest_v1.pkl",
        "isolation_forest_v1.pkl.sig",
    ]


def test_resave_invalidates_stale_signature_window(fitted_model, tmp_path):
    """Overwriting a version: old sig must never validate new bytes."""
    fitted_model.save()
    fitted_model.fit(np.random.RandomState(1).rand(200, N_FEATURES), "v1")
    fitted_model.save()
    assert AnomalyModel().load("v1") is True


def test_require_hmac_key_raises_when_empty(monkeypatch):
    monkeypatch.setattr(config, "MODEL_HMAC_KEY", "")
    with pytest.raises(RuntimeError, match="AZTDP_MODEL_HMAC_KEY"):
        config.require_hmac_key()


def test_hot_reload_invalid_version_does_not_crash(fitted_model, caplog):
    class R:
        def get(self, key):
            return "../../etc/passwd"

    import threading

    done = threading.Event()
    m = AnomalyModel()
    with caplog.at_level(logging.ERROR):
        t = start_hot_reload(m, R(), interval=1)
        done.wait(0.5)
    assert t.is_alive() and not m.is_loaded
    assert "invalid model version" in caplog.text


def test_legacy_unsigned_model_falls_through_to_cold_start(tmp_path, monkeypatch):
    """An unsigned pre-upgrade artifact is ignored; cold start retrains + signs."""
    from anomaly_service.training import cold_start_train

    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(config, "COLD_START_SAMPLES", 300)
    legacy = tmp_path / "isolation_forest_v1.0.pkl"
    legacy.write_bytes(b"legacy unsigned pickle bytes")
    m = AnomalyModel()
    assert m.load("v1.0") is False
    cold_start_train(m, version="v1.0")
    assert AnomalyModel().load("v1.0") is True


def _sig_path(p):
    return p.with_name(p.name + ".sig")


@pytest.mark.parametrize(
    "garbage",
    [
        b"\xff\xfe\x80\x81binary",            # invalid UTF-8
        "café".encode() * 16,            # valid UTF-8, non-ASCII
        b"ab" * 31,                            # wrong length hex (62)
        b"ab" * 33,                            # wrong length hex (66)
        b"z" * 64,                             # right length, not hex
        b"",
    ],
)
def test_garbage_signature_returns_false_without_raising(fitted_model, garbage):
    p = fitted_model.save()
    _sig_path(p).write_bytes(garbage)
    fresh = AnomalyModel()
    assert fresh.load("v1") is False
    assert not fresh.is_loaded


def test_directory_at_model_path_returns_false(fitted_model, tmp_path):
    p = fitted_model.save()
    p.unlink()
    p.mkdir()
    assert AnomalyModel().load("v1") is False


def test_directory_at_sig_path_returns_false(fitted_model):
    p = fitted_model.save()
    s = _sig_path(p)
    s.unlink()
    s.mkdir()
    assert AnomalyModel().load("v1") is False


def test_overlong_version_rejected(fitted_model):
    assert AnomalyModel().load("v" + "a" * 299) is False


def test_correctly_signed_corrupt_bundle_returns_false(fitted_model, tmp_path):
    import hmac, hashlib

    p = fitted_model.save()
    data = b"not a joblib payload"
    p.write_bytes(data)
    _sig_path(p).write_text(hmac.new(config.MODEL_HMAC_KEY.encode(), data, hashlib.sha256).hexdigest())
    fresh = AnomalyModel()
    assert fresh.load("v1") is False
    assert not fresh.is_loaded


def test_startup_cold_starts_when_signature_is_garbage(tmp_path, monkeypatch):
    from anomaly_service import app as app_mod

    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(config, "COLD_START_SAMPLES", 300)
    monkeypatch.setattr(config, "REDIS_URL", "")
    monkeypatch.setattr(app_mod, "start_hot_reload", lambda *a, **k: None)
    monkeypatch.setattr(app_mod, "start_retrain_scheduler", lambda *a, **k: None)
    fresh = AnomalyModel()
    monkeypatch.setattr(app_mod, "model", fresh)
    (tmp_path / "isolation_forest_v1.0.pkl").write_bytes(b"junk")
    (tmp_path / "isolation_forest_v1.0.pkl.sig").write_bytes(b"\xff\xfe\x00garbage")
    app_mod._on_startup()
    assert fresh.is_loaded
    assert AnomalyModel().load("v1.0") is True
