"""Production profile: settings must fail closed when DEBUG is off."""
import importlib

import pytest
from django.core.exceptions import ImproperlyConfigured

GOOD_KEY = "k" * 50
GOOD_ENV = {
    "AZTDP_DEBUG": "false",
    "AZTDP_SECRET_KEY": GOOD_KEY,
    "AZTDP_ALLOWED_HOSTS": "aztdp.example.com",
}


def _reload(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import aztdp_django.settings as s

    return importlib.reload(s)


@pytest.fixture(autouse=True)
def _restore_settings_module(monkeypatch):
    """Reloading mutates the module; put it back for later tests."""
    yield
    monkeypatch.undo()
    import aztdp_django.settings as s

    importlib.reload(s)


@pytest.mark.parametrize("bad", ["", "change-me", "ci-secret", "test-secret", "short", "x" * 31])
def test_prod_rejects_weak_secret(monkeypatch, bad):
    with pytest.raises(ImproperlyConfigured):
        _reload(monkeypatch, **{**GOOD_ENV, "AZTDP_SECRET_KEY": bad})


def test_prod_requires_allowed_hosts(monkeypatch):
    with pytest.raises(ImproperlyConfigured):
        _reload(monkeypatch, **{**GOOD_ENV, "AZTDP_ALLOWED_HOSTS": ""})


def test_prod_accepts_valid_config(monkeypatch):
    s = _reload(monkeypatch, **GOOD_ENV)
    assert s.DEBUG is False
    assert s.SECRET_KEY == GOOD_KEY
    assert s.ALLOWED_HOSTS == ["aztdp.example.com"]
    assert s.SESSION_COOKIE_HTTPONLY and s.CSRF_COOKIE_HTTPONLY
    assert s.SECURE_REFERRER_POLICY == "same-origin"
    assert "/ui" not in s.AZTDP_ALLOWLIST_PATHS


def test_debug_allows_dev_defaults(monkeypatch):
    monkeypatch.delenv("AZTDP_SECRET_KEY", raising=False)
    monkeypatch.delenv("AZTDP_ALLOWED_HOSTS", raising=False)
    s = _reload(monkeypatch, AZTDP_DEBUG="true")
    assert s.SECRET_KEY == "dev-insecure-key"
    assert "/ui" in s.AZTDP_ALLOWLIST_PATHS


def test_demo_ui_route_only_in_debug(monkeypatch, settings):
    import core.urls as u

    settings.DEBUG = False
    importlib.reload(u)
    assert not any(str(p.pattern) == "ui/" for p in u.urlpatterns)
    settings.DEBUG = True
    importlib.reload(u)
    assert any(str(p.pattern) == "ui/" for p in u.urlpatterns)
    settings.DEBUG = False
    importlib.reload(u)
