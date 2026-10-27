from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # Import for its side effect: step-up key validation runs at import time,
        # so a missing signing key / TOTP master secret fails the boot, not the
        # first step-up request.
        from . import stepup  # noqa: F401
