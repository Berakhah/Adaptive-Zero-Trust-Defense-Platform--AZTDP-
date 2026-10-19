import pytest

TEST_TOKEN = "test-internal-token"


@pytest.fixture(autouse=True)
def _internal_token(monkeypatch):
    monkeypatch.setenv("AZTDP_INTERNAL_TOKEN", TEST_TOKEN)


@pytest.fixture
def auth_headers():
    return {"X-Internal-Token": TEST_TOKEN}
