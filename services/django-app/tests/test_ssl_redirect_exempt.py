"""Production SSL redirect: only /health and /metrics are exempt (probes speak plain HTTP)."""
import importlib

import pytest
from django.test import Client

PROD_ENV = {
    "AZTDP_DEBUG": "false",
    "AZTDP_SECRET_KEY": "k" * 50,
    "AZTDP_ALLOWED_HOSTS": "testserver",
}


@pytest.fixture
def prod_client(monkeypatch, settings):
    for k, v in PROD_ENV.items():
        monkeypatch.setenv(k, v)
    import aztdp_django.settings as s

    prod = importlib.reload(s)
    try:
        # Apply the prod-profile values through pytest-django so they are undone
        # after the test; getattr keeps a missing exemption a clean assertion failure.
        settings.SECURE_SSL_REDIRECT = prod.SECURE_SSL_REDIRECT
        settings.SECURE_REDIRECT_EXEMPT = getattr(prod, "SECURE_REDIRECT_EXEMPT", [])
        settings.ALLOWED_HOSTS = prod.ALLOWED_HOSTS
        assert prod.SECURE_SSL_REDIRECT is True
        yield Client()
    finally:
        monkeypatch.undo()
        importlib.reload(s)


@pytest.mark.parametrize("path", ["/health", "/metrics"])
def test_probe_paths_not_redirected(prod_client, path):
    resp = prod_client.get(path)
    assert resp.status_code not in (301, 302), resp.get("Location")
    assert resp.status_code == 200


@pytest.mark.parametrize("path", ["/v1/payments/x", "/healthz", "/metrics/extra", "/"])
def test_other_paths_redirect_to_https(prod_client, path):
    resp = prod_client.get(path)
    assert resp.status_code == 301
    assert resp["Location"].startswith("https://")
