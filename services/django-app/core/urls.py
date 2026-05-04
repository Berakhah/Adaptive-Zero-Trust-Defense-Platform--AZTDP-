from django.urls import path
from . import views

urlpatterns = [
    path("ui/", views.ui_home, name="ui_home"),
    path("health", views.health, name="health"),
    path("metrics", views.metrics, name="metrics"),
    path("v1/payments/<str:payment_id>", views.payment_detail, name="payment_detail"),
    path("v1/admin/flags", views.admin_flags, name="admin_flags"),
    path("v1/auth/step-up/verify", views.step_up_verify, name="step_up_verify"),
]
