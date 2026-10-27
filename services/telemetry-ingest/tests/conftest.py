from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

TEST_TOKEN = "test-internal-token"


@pytest.fixture(autouse=True)
def _internal_token(monkeypatch):
    monkeypatch.setenv("AZTDP_INTERNAL_TOKEN", TEST_TOKEN)


@pytest.fixture
def auth_headers():
    return {"X-Internal-Token": TEST_TOKEN}


class StubPool:
    """Records executed SQL; raises on the next execute when fail_next is set."""

    def __init__(self):
        self.executed = []
        self.fail_next = False

    @contextmanager
    def connection(self):
        yield _StubConn(self)


class _StubConn:
    def __init__(self, pool):
        self._pool = pool

    @contextmanager
    def cursor(self):
        yield _StubCursor(self._pool)


class _StubCursor:
    def __init__(self, pool):
        self._pool = pool

    def execute(self, sql, params=None):
        if self._pool.fail_next:
            self._pool.fail_next = False
            raise RuntimeError("db down")
        self._pool.executed.append((sql, params))


@pytest.fixture
def stub_pool(monkeypatch):
    from telemetry_ingest import app as app_module

    pool = StubPool()
    monkeypatch.setattr(app_module, "get_pool", lambda: pool)
    return pool


@pytest.fixture
def client(stub_pool):
    from telemetry_ingest import app as app_module

    return TestClient(app_module.app)
