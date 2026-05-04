from risk_engine.storage import InMemoryStore


def test_set_and_get_roundtrip():
    store = InMemoryStore(ttl_seconds=10)
    store.set("k", {"ip": "1.1.1.1"})
    assert store.get("k") == {"ip": "1.1.1.1"}


def test_missing_returns_none():
    store = InMemoryStore(ttl_seconds=10)
    assert store.get("none") is None
