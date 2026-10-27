import pytest

TEST_TOKEN = "test-internal-token"


@pytest.fixture(autouse=True)
def _internal_token(monkeypatch):
    monkeypatch.setenv("AZTDP_INTERNAL_TOKEN", TEST_TOKEN)


@pytest.fixture
def auth_headers():
    return {"X-Internal-Token": TEST_TOKEN}


class FakeRevocationDB:
    """In-memory stand-in for the token_revocations table (db protocol)."""

    def __init__(self):
        self.rows = []

    def insert_revocation(self, token_hash, expires_at, **_kwargs):
        if all(r[0] != token_hash for r in self.rows):  # ON CONFLICT DO NOTHING
            self.rows.append((token_hash, expires_at))

    def active(self):
        return list(self.rows)


class FailingRevocationDB(FakeRevocationDB):
    def insert_revocation(self, token_hash, expires_at, **_kwargs):
        raise RuntimeError("db down")


@pytest.fixture
def fake_redis():
    import fakeredis

    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def fake_db():
    return FakeRevocationDB()


@pytest.fixture
def failing_db():
    return FailingRevocationDB()
