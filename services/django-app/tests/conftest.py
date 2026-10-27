import os
import sys
from pathlib import Path

import django

# Ensure the django-app package is on sys.path independent of the root conftest.
BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aztdp_django.settings")
os.environ.setdefault("AZTDP_DB_ENGINE", "django.db.backends.sqlite3")
os.environ.setdefault("AZTDP_DB_NAME", ":memory:")
# Settings fail closed outside DEBUG: force a valid >=32 char key and allowed hosts
# (scripts/run_tests.sh exports a short AZTDP_SECRET_KEY that would be rejected).
os.environ["AZTDP_SECRET_KEY"] = "test-only-secret-key-" + "x" * 32
os.environ["AZTDP_ALLOWED_HOSTS"] = "testserver,localhost"
# Step-up secrets are required (fail-closed) outside DEBUG; supply test values.
os.environ.setdefault("AZTDP_STEPUP_SIGNING_KEY", "test-signing-key")
os.environ.setdefault("AZTDP_TOTP_MASTER_SECRET", "test-master-secret")

django.setup()


import fakeredis  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _fake_stepup_store(monkeypatch):
    """Every test gets a fresh in-memory Redis for the step-up store."""
    from core import stepup

    shared = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(stepup, "get_store", lambda: shared)
    yield shared
