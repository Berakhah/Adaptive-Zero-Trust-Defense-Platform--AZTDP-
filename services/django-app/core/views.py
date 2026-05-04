import json

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


def health(_request):
    return JsonResponse({"status": "ok"})


def metrics(_request):
    return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)


def payment_detail(request, payment_id: str):
    context = getattr(request, "aztdp_context", {})
    return JsonResponse(
        {
            "payment_id": payment_id,
            "subject": context.get("subject"),
            "risk": context.get("risk"),
        }
    )


def admin_flags(request):
    context = getattr(request, "aztdp_context", {})
    return JsonResponse(
        {
            "feature_flags": ["zero_trust_enforced", "adaptive_risk"],
            "subject": context.get("subject"),
            "risk": context.get("risk"),
        }
    )


def ui_home(request):
    return render(request, "core/ui.html")


@csrf_exempt
@require_POST
def step_up_verify(request):
    """Verify a step-up TOTP challenge and return a step_up_token.

    POST /v1/auth/step-up/verify
    Body: {"challenge_id": "...", "code": "123456", "user_id": "..."}

    This endpoint is on the middleware allowlist (no Bearer token required)
    because the client is in a challenged state and may not have a valid session.
    Authentication is via the challenge_id itself (unguessable UUID).
    """
    from .stepup import verify_challenge

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": {"code": "invalid_body"}}, status=400)

    challenge_id = body.get("challenge_id", "")
    code = body.get("code", "")
    user_id = body.get("user_id", "")

    if not challenge_id or not code or not user_id:
        return JsonResponse(
            {"error": {"code": "missing_fields", "required": ["challenge_id", "code", "user_id"]}},
            status=400,
        )

    token = verify_challenge(challenge_id, code, user_id)
    if not token:
        return JsonResponse(
            {"error": {"code": "verification_failed", "message": "Invalid or expired challenge"}},
            status=401,
        )

    return JsonResponse(
        {
            "step_up_token": token,
            "expires_in_seconds": 600,
            "message": "Step-up verified. Include this token as X-Step-Up-Token header.",
        }
    )
