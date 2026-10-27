import threading
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from gateway.revocation_store import RevocationPersistError, RevocationStore

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
    # grace=0 reproduces the brief's original max(1, exp - now) formula (case d).
    monkeypatch.setattr("gateway.config.REVOCATION_EXP_GRACE_SECONDS", 0)
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
    monkeypatch.setattr("gateway.config.REVOCATION_EXP_GRACE_SECONDS", 300)
    monkeypatch.setattr("gateway.revocation_store.time.time", lambda: 1_000_000.0)
    s = RevocationStore(redis=fake_redis, db=fake_db)
    s.revoke("h1", expires_at=999_000)  # exp + grace already in the past
    assert fake_redis.ttl("revoked:token:h1") == 1


# --- Clock-skew grace (fix round 1) -----------------------------------------
# Relying parties accept a token for a while after `exp` (Spring's
# JwtTimestampValidator: 60 s clock skew, plus host drift). The revocation must
# outlive exp by AZTDP_REVOCATION_EXP_GRACE_SECONDS on every path.

@pytest.fixture
def grace_300(monkeypatch):
    monkeypatch.setattr("gateway.config.REVOCATION_EXP_GRACE_SECONDS", 300)
    monkeypatch.setattr("gateway.revocation_store.time.time", lambda: 1_000_000.0)


def test_grace_revoke_with_exp_recently_past_stays_revoked(fake_redis, fake_db, grace_300):
    """(a) exp passed 30 s ago (< grace): TTL must be > 1 and the token revoked."""
    s = RevocationStore(redis=fake_redis, db=fake_db)
    s.revoke("h1", expires_at=999_970)
    assert s.is_revoked("h1")
    assert fake_redis.ttl("revoked:token:h1") == 270


def test_grace_ttl_for_future_exp(fake_redis, fake_db, grace_300):
    """(b) TTL = exp - now + grace."""
    s = RevocationStore(redis=fake_redis, db=fake_db)
    s.revoke("h1", expires_at=1_000_120)
    assert fake_redis.ttl("revoked:token:h1") == 420


def test_grace_resync_restores_within_grace_and_skips_beyond(fake_redis, fake_db, grace_300):
    """(c) resync: exp passed 100 s ago -> restored with TTL 200; exp+grace passed -> skipped."""
    fake_db.rows = [("recent", 999_900), ("stale", 999_600), ("live", 1_000_300)]
    s = RevocationStore(redis=fake_redis, db=fake_db)
    s.resync()
    assert fake_redis.ttl("revoked:token:recent") == 200
    assert not fake_redis.exists("revoked:token:stale")
    assert fake_redis.ttl("revoked:token:live") == 600


def test_grace_cold_start_restores_within_grace(fake_redis, fake_db, grace_300):
    """(c) cold start uses the same rule."""
    fake_db.rows = [("recent", 999_900), ("stale", 999_000)]
    s = RevocationStore(redis=fake_redis, db=fake_db)
    s.cold_start_recovery()
    assert s.is_revoked("recent")
    assert not s.is_revoked("stale")


def test_grace_zero_matches_original_formula(fake_redis, fake_db, monkeypatch):
    """(d) grace=0: TTL = max(1, exp - now); resync skips rows past exp."""
    monkeypatch.setattr("gateway.config.REVOCATION_EXP_GRACE_SECONDS", 0)
    monkeypatch.setattr("gateway.revocation_store.time.time", lambda: 1_000_000.0)
    s = RevocationStore(redis=fake_redis, db=fake_db)
    s.revoke("future", expires_at=1_000_120)
    s.revoke("past", expires_at=999_970)
    assert fake_redis.ttl("revoked:token:future") == 120
    assert fake_redis.ttl("revoked:token:past") == 1
    fake_redis.flushall()
    fake_db.rows = [("recent", 999_900), ("live", 1_000_300)]
    s.resync()
    assert not fake_redis.exists("revoked:token:recent")
    assert fake_redis.ttl("revoked:token:live") == 300


def test_no_exp_path_keeps_default_ttl(fake_redis, fake_db, monkeypatch):
    monkeypatch.setattr("gateway.config.REVOCATION_EXP_GRACE_SECONDS", 300)
    monkeypatch.setattr("gateway.config.REVOCATION_TTL_SECONDS", 3600)
    s = RevocationStore(redis=fake_redis, db=fake_db)
    s.revoke("h1")
    assert 3590 <= fake_redis.ttl("revoked:token:h1") <= 3600


@pytest.mark.parametrize("raw,expected", [("300", 300), ("0", 0), ("-5", 0), ("junk", 300), ("", 300)])
def test_grace_config_parsing(raw, expected):
    from gateway.config import _parse_grace

    assert _parse_grace(raw) == expected


def test_postgres_active_applies_grace_index_friendly():
    from gateway.revocation_store import PostgresRevocationDB

    cur = MagicMock()
    cur.fetchall.return_value = [("h1", 1_700_000_000)]
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = cur
    with patch("psycopg.connect", return_value=conn):
        rows = PostgresRevocationDB(
            "postgresql://x@y/z", default_ttl_seconds=3600, exp_grace_seconds=300
        ).active()
    assert rows == [("h1", 1_700_000_000)]
    sql, params = cur.execute.call_args.args
    norm = " ".join(sql.split())
    # Sargable on expires_at / revoked_at (no COALESCE in the predicate).
    assert "WHERE expires_at > now() - make_interval(secs => %(grace)s)" in norm
    assert "OR (expires_at IS NULL AND revoked_at > now() - make_interval(secs => %(ttl)s))" in norm
    assert params == {"grace": 300, "ttl": 3600}


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
    monkeypatch.setattr("gateway.config.REVOCATION_EXP_GRACE_SECONDS", 0)
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


def test_revoke_endpoint_uses_expires_at(app_with_store, fake_redis, fake_db, auth_headers, monkeypatch):
    import time

    monkeypatch.setattr("gateway.config.REVOCATION_EXP_GRACE_SECONDS", 300)
    exp = int(time.time()) + 120
    client = app_with_store(RevocationStore(redis=fake_redis, db=fake_db))
    r = client.post(
        "/v1/tokens/revoke",
        json={"token_jti_hash": "h1", "reason": "policy", "source": "policy", "expires_at": exp},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert fake_db.rows == [("h1", exp)]
    assert 400 <= fake_redis.ttl("revoked:token:h1") <= 420  # exp - now + grace


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
