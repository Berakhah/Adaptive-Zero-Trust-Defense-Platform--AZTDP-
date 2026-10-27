import pytest

from forensics import app as forensics_app


def test_startup_refuses_without_internal_token(monkeypatch):
    monkeypatch.delenv("AZTDP_INTERNAL_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="AZTDP_INTERNAL_TOKEN"):
        forensics_app._on_startup()
