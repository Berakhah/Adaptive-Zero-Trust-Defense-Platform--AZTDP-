import time

from gateway.revocation_store import InMemoryRevocationStore, RevocationStore


def test_in_memory_revoke_and_check():
    store = InMemoryRevocationStore(ttl_seconds=10)
    store.revoke("hash-1")
    assert store.is_revoked("hash-1") is True
    assert store.is_revoked("hash-other") is False


def test_in_memory_expiry():
    store = InMemoryRevocationStore(ttl_seconds=0)
    store.revoke("hash-1")
    time.sleep(0.01)
    assert store.is_revoked("hash-1") is False


def test_revocation_store_falls_back_to_memory_when_no_redis(monkeypatch):
    from gateway import config
    monkeypatch.setattr(config, "REDIS_URL", "")
    store = RevocationStore()
    store.revoke("abc")
    assert store.is_revoked("abc") is True
    assert store.is_revoked("") is False
