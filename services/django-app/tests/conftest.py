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
os.environ.setdefault("AZTDP_SECRET_KEY", "test-secret")

django.setup()
