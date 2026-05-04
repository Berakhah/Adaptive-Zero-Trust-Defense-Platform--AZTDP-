from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("AZTDP_SECRET_KEY", "change-me")
DEBUG = os.getenv("AZTDP_DEBUG", "false").lower() == "true"

_raw_hosts = os.getenv("AZTDP_ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(",") if h.strip()] or (["localhost", "127.0.0.1"] if DEBUG else [])

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.RiskAuthzMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "aztdp_django.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

WSGI_APPLICATION = "aztdp_django.wsgi.application"
ASGI_APPLICATION = "aztdp_django.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": os.getenv("AZTDP_DB_ENGINE", "django.db.backends.postgresql"),
        "NAME": os.getenv("AZTDP_DB_NAME", "aztdp"),
        "USER": os.getenv("AZTDP_DB_USER", "aztdp"),
        "PASSWORD": os.getenv("AZTDP_DB_PASSWORD", "aztdp"),
        "HOST": os.getenv("AZTDP_DB_HOST", "postgres"),
        "PORT": os.getenv("AZTDP_DB_PORT", "5432"),
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AZTDP = {
    "KEYCLOAK_ISSUER": os.getenv("AZTDP_OIDC_ISSUER", "http://keycloak:8080/realms/aztdp"),
    "KEYCLOAK_JWKS_URL": os.getenv(
        "AZTDP_JWKS_URL",
        "http://keycloak:8080/realms/aztdp/protocol/openid-connect/certs",
    ),
    "KEYCLOAK_AUDIENCE": os.getenv("AZTDP_AUDIENCE", "aztdp-api"),
    "RISK_ENGINE_URL": os.getenv("AZTDP_RISK_ENGINE_URL", "http://risk-engine:8080"),
    "POLICY_GATEWAY_URL": os.getenv("AZTDP_POLICY_GATEWAY_URL", "http://gateway:8080"),
    "TOKEN_REVOKE_URL": os.getenv(
        "AZTDP_TOKEN_REVOKE_URL", "http://gateway:8080/v1/tokens/revoke"
    ),
    "FAIL_OPEN": os.getenv("AZTDP_FAIL_OPEN", "false").lower() == "true",
    "TIMEOUT_CONNECT": float(os.getenv("AZTDP_TIMEOUT_CONNECT", "0.2")),
    "TIMEOUT_READ": float(os.getenv("AZTDP_TIMEOUT_READ", "0.8")),
    "INTERNAL_TOKEN": os.getenv("AZTDP_INTERNAL_TOKEN", ""),
}

AZTDP_ENDPOINT_SENSITIVITY = [
    {"method": "GET", "path_prefix": "/v1/payments", "sensitivity": 4},
    {"method": "POST", "path_prefix": "/v1/admin", "sensitivity": 5},
]

AZTDP_ALLOWLIST_PATHS = ["/health", "/metrics", "/v1/auth/step-up/verify", "/ui"]

# Trusted reverse-proxy CIDRs. Only requests originating from these networks
# are allowed to set X-Client-Ip / X-Forwarded-For / X-Geo. Empty by default
# (strict mode — REMOTE_ADDR wins always). In production set to your ingress
# CIDR (e.g. "10.0.0.0/8" for an internal LB).
AZTDP_TRUSTED_PROXIES = os.getenv("AZTDP_TRUSTED_PROXIES", "")

# ── Security hardening (P4.3) ────────────────────────────────────────────────
# These are no-ops when DEBUG=True so local dev is unaffected.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
