from contextlib import contextmanager
from datetime import datetime

import pytest
from fastapi.testclient import TestClient


class _Result:
    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _StubPool:
    def __init__(self):
        self.executed = []

    @contextmanager
    def connection(self):
        pool = self

        class _Conn:
            def execute(self, sql, params=None):
                pool.executed.append((sql, params))
                return _Result()

        yield _Conn()


@pytest.fixture
def stub_pool(monkeypatch):
    from forensics import app as app_module

    pool = _StubPool()
    monkeypatch.setattr(app_module, "get_pool", lambda: pool)
    return pool


@pytest.fixture
def client(stub_pool):
    from forensics import app as app_module

    return TestClient(app_module.app)


def test_invalid_since_returns_422(client, auth_headers):
    assert client.get("/v1/forensics/events?since=not-a-date", headers=auth_headers).status_code == 422


def test_invalid_until_returns_422(client, auth_headers):
    assert client.get("/v1/forensics/events?until=garbage", headers=auth_headers).status_code == 422


def test_limit_above_max_returns_422(client, auth_headers):
    assert client.get("/v1/forensics/events?limit=100000", headers=auth_headers).status_code == 422


def test_valid_since_is_passed_as_datetime(client, auth_headers, stub_pool):
    r = client.get("/v1/forensics/events?since=2026-01-01T00:00:00Z", headers=auth_headers)
    assert r.status_code == 200
    _, params = stub_pool.executed[-1]
    assert any(isinstance(p, datetime) for p in params)
