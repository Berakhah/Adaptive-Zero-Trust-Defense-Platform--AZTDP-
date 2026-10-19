import threading
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from gateway.revocation_store import RevocationStore, RevocationPersistError


# --- Brief-mandated tests -------------------------------------------------

def test_revoke_persists_to_db_before_returning(fake_redis, fake_db):
    s = RevocationStore(redis=fake_redis, db=fake_db)
    s.revoke("h1", expires_at=None)
    assert [r[0] for r in fake_db.rows] == ["h1"]
    assert fake_redis.exists("revoked:token:h1")


def test_db_failure_fails_closed(fake_redis, failing_db):
    s = RevocationStore(redis=fake_redis, db=failing_db)
    with pytest.raises(RevocationPersistError):
        s.revoke("h1")


def test_ttl_follows_token_exp(fake_redis, fake_db, monkeypatch):
    monkeypatch.setattr("gateway.revocation_store.time.time", lambda: 1_000_000.0)
    s = RevocationStore(redis=fake_redis, db=fake_db)
    s.revoke("h1", expires_at=1_000_120)
    assert 100 <= fake_redis.ttl("revoked:token:h1") <= 120


def test_resync_restores_after_redis_flush(fake_redis, fake_db):
    fake_db.rows = [("h9", None)]
    s = RevocationStore(redis=fake_redis, db=fake_db)
    s.cold_start_recovery()
    assert s.is_revoked("h9")


# --- Additional coverage ---------------------------------------------------

def test_db_failure_does_not_write_cache(fake_redis, failing_db):
    """DB is written first: a failed persist must not leave a cache-only revocation."""
    s = RevocationStore(redis=fake_redis, db=failing_db)
    with pytest.raises(RevocationPersistError):
        s.revoke("h1")
    assert not fake_redis.exists("revoked:token:h1")


def test_expired_token_gets_minimum_ttl(fake_redis, fake_db, monkeypatch):
    monkeypatch.setattr("gateway.revocation_store.time.time", lambda: 1_000_000.0)
    s = RevocationStore(redis=fake_redis, db=fake_db)
    s.revoke("h1", expires_at=999_000)  # exp already in the past
    assert fake_redis.ttl("revoked:token:h1") == 1


def test_revoke_passes_expiry_to_db(fake_redis, fake_db):
    s = RevocationStore(redis=fake_redis, db=fake_db)
    s.revoke("h1", expires_at=4_102_444_800)
    assert fake_db.rows == [("h1", 4_102_444_800)]


def test_resync_after_flush_without_gateway_restart(fake_redis, fake_db):
    """Redis restart (flush) mid-life: one resync pass restores the revocation."""
    s = RevocationStore(redis=fake_redis, db=fake_db)
    s.revoke("h1")
    fake_redis.flushall()
    assert not s.is_revoked("h1")
    s.resync()
    assert s.is_revoked("h1")


def test_resync_skips_rows_already_expired(fake_redis, fake_db, monkeypatch):
    monkeypatch.setattr("gateway.revocation_store.time.time", lambda: 1_000_000.0)
    fake_db.rows = [("old", 999_999), ("live", 1_000_300)]
    s = RevocationStore(redis=fake_redis, db=fake_db)
    s.resync()
    assert not fake_redis.exists("revoked:token:old")
    assert 0 < fake_redis.ttl("revoked:token:live") <= 300


def test_resync_db_error_is_non_fatal(fake_redis):
    db = MagicMock()
    db.active.side_effect = RuntimeError("db down")
    s = RevocationStore(redis=fake_redis, db=db)
    s.resync()  # must not raise


def test_periodic_resync_thread_starts_and_stops(fake_redis, fake_db):
    s = RevocationStore(redis=fake_redis, db=fake_db)
    s.revoke("h1")
    fake_redis.flushall()
    t = s.start_periodic_resync(interval_seconds=0.01)
    try:
        assert t.daemon is True
        for _ in range(200):
            if s.is_revoked("h1"):
                break
            threading.Event().wait(0.01)
        assert s.is_revoked("h1")
    finally:
        s.stop_periodic_resync(timeout=2)
    assert not t.is_alive()


def test_start_periodic_resync_is_idempotent(fake_redis, fake_db):
    s = RevocationStore(redis=fake_redis, db=fake_db)
    t1 = s.start_periodic_resync(interval_seconds=60)
    t2 = s.start_periodic_resync(interval_seconds=60)
    try:
        assert t1 is t2
    finally:
        s.stop_periodic_resync(timeout=2)
    assert not t1.is_alive()


def test_postgres_db_insert_uses_on_conflict_and_to_timestamp():
    from gateway.revocation_store import PostgresRevocationDB

    cur = MagicMock()
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = cur
    with patch("psycopg.connect", return_value=conn) as connect:
        PostgresRevocationDB("postgresql://x@y/z", connect_timeout=3).insert_revocation(
            "h1", 1_700_000_000, reason="policy", source="policy"
        )
    assert connect.call_args.kwargs.get("connect_timeout") == 3
    sql, params = cur.execute.call_args.args
    assert "INSERT INTO token_revocations" in sql
    assert "ON CONFLICT (token_jti_hash) DO NOTHING" in sql
    assert "to_timestamp" in sql
    assert params == ("h1", "policy", "policy", 1_700_000_000)


# --- HTTP endpoint ----------------------------------------------------------

@pytest.fixture
def app_with_store(monkeypatch):
    from gateway import app as app_module

    def _install(store):
        monkeypatch.setattr(app_module, "revocations", store)
        return TestClient(app_module.app)

    return _install


def test_revoke_endpoint_returns_503_when_not_persisted(app_with_store, fake_redis, failing_db, auth_headers):
    client = app_with_store(RevocationStore(redis=fake_redis, db=failing_db))
    r = client.post(
        "/v1/tokens/revoke",
        json={"token_jti_hash": "h1", "reason": "policy", "source": "policy"},
        headers=auth_headers,
    )
    assert r.status_code == 503
    assert r.json()["detail"] == "revocation_not_persisted"


def test_revoke_endpoint_uses_expires_at(app_with_store, fake_redis, fake_db, auth_headers):
    import time

    exp = int(time.time()) + 120
    client = app_with_store(RevocationStore(redis=fake_redis, db=fake_db))
    r = client.post(
        "/v1/tokens/revoke",
        json={"token_jti_hash": "h1", "reason": "policy", "source": "policy", "expires_at": exp},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert fake_db.rows == [("h1", exp)]
    assert 100 <= fake_redis.ttl("revoked:token:h1") <= 120


def test_revoke_endpoint_rejects_unknown_source(app_with_store, fake_redis, fake_db, auth_headers):
    """token_revocations.source has a CHECK constraint; reject bad values with 422, not a DB 503."""
    client = app_with_store(RevocationStore(redis=fake_redis, db=fake_db))
    r = client.post(
        "/v1/tokens/revoke",
        json={"token_jti_hash": "h1", "reason": "policy", "source": "bogus"},
        headers=auth_headers,
    )
    assert r.status_code == 422
    assert fake_db.rows == []


def test_app_lifecycle_starts_and_stops_resync_thread(monkeypatch, fake_redis, fake_db):
    from gateway import app as app_module

    store = RevocationStore(redis=fake_redis, db=fake_db)
    monkeypatch.setattr(app_module, "revocations", store)
    with TestClient(app_module.app):
        t = store._resync_thread
        assert t is not None and t.is_alive() and t.daemon
    assert not t.is_alive()
