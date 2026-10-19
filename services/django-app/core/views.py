import json
import logging

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

_IP_MAX_ATTEMPTS = 20
_IP_WINDOW_SECONDS = 60


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
    Body: {"challenge_id": "...", "code": "123456"}  (user_id optional; must match the challenge)

    This endpoint is on the middleware allowlist (no Bearer token required)
    because the client is in a challenged state and may not have a valid session.
    Authentication is via the challenge_id itself (unguessable UUID).
    """
    from django.conf import settings

    from .client_ip import parse_cidrs, resolve_client_ip
    from .stepup import get_challenge_user, get_store, verify_challenge

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": {"code": "invalid_body"}}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"error": {"code": "invalid_body"}}, status=400)

    challenge_id = body.get("challenge_id", "")
    code = body.get("code", "")
    body_user_id = body.get("user_id", "")

    if not challenge_id or not code:
        return JsonResponse(
            {"error": {"code": "missing_fields", "required": ["challenge_id", "code"]}},
            status=400,
        )

    client_ip, _ = resolve_client_ip(
        remote_addr=request.META.get("REMOTE_ADDR", ""),
        forwarded_for=request.META.get("HTTP_X_FORWARDED_FOR"),
        x_client_ip=request.META.get("HTTP_X_CLIENT_IP"),
        trusted_proxies=parse_cidrs(getattr(settings, "AZTDP_TRUSTED_PROXIES", "")),
    )

    try:
        store = get_store()
        ip_key = f"stepup:ip:{client_ip}"
        hits = store.incr(ip_key)
        if hits == 1:
            store.expire(ip_key, _IP_WINDOW_SECONDS)
        if hits > _IP_MAX_ATTEMPTS:
            return JsonResponse({"error": {"code": "rate_limited"}}, status=429)

        # The challenge's stored user is authoritative; never trust the body.
        stored_user = get_challenge_user(str(challenge_id))
        if not stored_user or (body_user_id and body_user_id != stored_user):
            return JsonResponse(
                {"error": {"code": "verification_failed", "message": "Invalid or expired challenge"}},
                status=401,
            )
        token = verify_challenge(str(challenge_id), str(code), stored_user)
    except Exception:  # store unavailable -> fail closed
        logging.getLogger("aztdp.stepup").exception("step-up store unavailable")
        return JsonResponse({"error": {"code": "stepup_unavailable"}}, status=503)

    if not token:
        return JsonResponse(
            {"error": {"code": "verification_failed", "message": "Invalid or expired challenge"}},
            status=401,
        )

    return JsonResponse(
        {
            "step_up_token": token,
            "expires_in_seconds": 300,
            "message": "Step-up verified. Include this token as X-Step-Up-Token header.",
        }
    )
