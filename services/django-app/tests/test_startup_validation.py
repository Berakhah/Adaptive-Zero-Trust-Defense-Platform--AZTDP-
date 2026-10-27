import pytest
from core import stepup
from django.apps import apps


def test_core_app_ready_imports_stepup():
    import inspect

    assert "stepup" in inspect.getsource(apps.get_app_config("core").ready)


def test_load_config_fails_closed_outside_debug(monkeypatch):
    monkeypatch.delenv("AZTDP_STEPUP_SIGNING_KEY", raising=False)
    monkeypatch.delenv("AZTDP_TOTP_MASTER_SECRET", raising=False)
    with pytest.raises(stepup.StepUpConfigError):
        stepup.load_config(debug=False)
