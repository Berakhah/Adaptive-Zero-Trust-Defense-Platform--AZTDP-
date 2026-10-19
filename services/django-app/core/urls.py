from django.conf import settings
from django.urls import path
from . import views

urlpatterns = [
    path("health", views.health, name="health"),
    path("metrics", views.metrics, name="metrics"),
    path("v1/payments/<str:payment_id>", views.payment_detail, name="payment_detail"),
    path("v1/admin/flags", views.admin_flags, name="admin_flags"),
    path("v1/auth/step-up/verify", views.step_up_verify, name="step_up_verify"),
]

if settings.DEBUG:
    # Demo UI: development only, never served in production.
    urlpatterns.insert(0, path("ui/", views.ui_home, name="ui_home"))
