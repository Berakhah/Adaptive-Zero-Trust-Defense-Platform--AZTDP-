import hashlib
import uuid
from typing import Any, Dict

from django.conf import settings
from django.http import JsonResponse

from .client_ip import parse_cidrs, resolve_client_ip, resolve_geo
from .jwt import JwtVerificationError, JwtVerifier
from .policy_client import PolicyClient, PolicyClientError
from .risk_client import RiskClient, RiskClientError
from .revocation_client import TokenRevocationClient, RevocationClientError


class RiskAuthzMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        cfg = settings.AZTDP
        self.fail_open = cfg["FAIL_OPEN"]
        self.verifier = JwtVerifier(
            issuer=cfg["KEYCLOAK_ISSUER"],
            audience=cfg["KEYCLOAK_AUDIENCE"],
            jwks_url=cfg["KEYCLOAK_JWKS_URL"],
            timeout=cfg["TIMEOUT_CONNECT"],
        )
        internal_token = cfg.get("INTERNAL_TOKEN", "")
        self.risk_client = RiskClient(
            base_url=cfg["RISK_ENGINE_URL"],
            timeout_connect=cfg["TIMEOUT_CONNECT"],
            timeout_read=cfg["TIMEOUT_READ"],
            internal_token=internal_token,
        )
        self.policy_client = PolicyClient(
            base_url=cfg["POLICY_GATEWAY_URL"],
            timeout_connect=cfg["TIMEOUT_CONNECT"],
            timeout_read=cfg["TIMEOUT_READ"],
            internal_token=internal_token,
        )
        self.revocation_client = TokenRevocationClient(
            revoke_url=cfg["TOKEN_REVOKE_URL"],
            timeout_connect=cfg["TIMEOUT_CONNECT"],
            timeout_read=cfg["TIMEOUT_READ"],
            internal_token=internal_token,
        )
        self.trusted_proxies = parse_cidrs(getattr(settings, "AZTDP_TRUSTED_PROXIES", ""))

    def __call__(self, request):
        if self._is_allowlisted(request.path):
            return self.get_response(request)

        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            return self._unauthorized("missing_token")

        token = auth_header.split(" ", 1)[1].strip()
        try:
            claims = self.verifier.verify(token)
        except JwtVerificationError:
            return self._unauthorized("invalid_token")

        request_id = request.META.get("HTTP_X_REQUEST_ID", str(uuid.uuid4()))
        session_id = claims.get("sid") or claims.get("session_state")
        subject_id = claims.get("sub")
        jti = claims.get("jti", "")
        token_jti_hash = self._sha256(jti) if jti else ""
        user_agent_hash = self._sha256(request.META.get("HTTP_USER_AGENT", ""))
        remote_addr = request.META.get("REMOTE_ADDR", "")
        client_ip, _was_forwarded = resolve_client_ip(
            remote_addr=remote_addr,
            forwarded_for=request.META.get("HTTP_X_FORWARDED_FOR"),
            x_client_ip=request.META.get("HTTP_X_CLIENT_IP"),
            trusted_proxies=self.trusted_proxies,
        )
        geo = resolve_geo(
            x_geo=request.META.get("HTTP_X_GEO"),
            remote_addr=remote_addr,
            trusted_proxies=self.trusted_proxies,
        )
        sensitivity = self._endpoint_sensitivity(request.path, request.method)

        risk_payload = {
            "request_id": request_id,
            "session_id": session_id,
            "user_id": subject_id,
            "token_jti_hash": token_jti_hash,
            "ip": client_ip,
            "geo": geo,
            "user_agent_hash": user_agent_hash,
            "endpoint": {
                "service": "django-app",
                "method": request.method,
                "path": request.path,
                "sensitivity": sensitivity,
            },
            "timestamp": self._now_iso(),
        }

        try:
            risk_result = self.risk_client.evaluate(risk_payload)
        except RiskClientError as exc:
            if exc.code == "replay_detected":
                return self._deny("token_replay")
            if self.fail_open:
                return self.get_response(request)
            return self._deny("risk_unavailable")

        policy_input = {
            "input": {
                "request_id": request_id,
                "subject": {
                    "user_id": subject_id,
                    "roles": claims.get("roles", claims.get("realm_access", {}).get("roles", [])),
                    "session_trust": risk_result.get("trust_score"),
                },
                "resource": {
                    "service": "django-app",
                    "method": request.method,
                    "path": request.path,
                    "sensitivity": sensitivity,
                },
                "context": {
                    "risk_score": risk_result.get("risk_score"),
                    "ip": client_ip,
                    "geo": geo,
                    "token_jti_hash": token_jti_hash,
                    "anomaly_score": risk_result.get("anomaly_score", 0.0),
                },
            }
        }

        try:
            decision = self.policy_client.decide(policy_input)
        except PolicyClientError:
            if self.fail_open:
                return self.get_response(request)
            return self._deny("policy_unavailable")

        decision_data = decision.get("decision") or decision.get("result") or {}
        if isinstance(decision_data, dict):
            action = decision_data.get("decision", "deny")
            reason = decision_data.get("reason", {})
        else:
            action = decision.get("decision", "deny")
            reason = decision.get("reason", {})

        request.aztdp_context = {
            "subject": subject_id,
            "risk": risk_result,
            "decision": action,
            "reason": reason,
        }

        if action == "allow":
            return self.get_response(request)
        if action == "stepup":
            # If client already completed step-up, honor the token
            step_up_header = request.META.get("HTTP_X_STEP_UP_TOKEN", "")
            if step_up_header:
                from .stepup import verify_step_up_token
                if verify_step_up_token(step_up_header, subject_id):
                    return self.get_response(request)
            return self._stepup(reason, subject_id)
        if action == "revoke":
            self._revoke(token_jti_hash, "policy")
            return self._deny("token_revoked")
        return self._deny("policy_denied")

    def _revoke(self, token_jti_hash: str, reason: str) -> None:
        if not token_jti_hash:
            return
        try:
            self.revocation_client.revoke(
                {"token_jti_hash": token_jti_hash, "reason": reason, "source": "policy"}
            )
        except RevocationClientError:
            import logging
            logging.getLogger("aztdp.middleware").error(
                "revocation failed for token_jti_hash=%s reason=%s — "
                "token remains valid until expiry",
                token_jti_hash[:12] + "...",
                reason,
            )

    def _endpoint_sensitivity(self, path: str, method: str) -> int:
        for rule in settings.AZTDP_ENDPOINT_SENSITIVITY:
            if method == rule["method"] and path.startswith(rule["path_prefix"]):
                return int(rule["sensitivity"])
        return 2

    def _is_allowlisted(self, path: str) -> bool:
        for allowed in settings.AZTDP_ALLOWLIST_PATHS:
            if path.startswith(allowed):
                return True
        return False

    def _unauthorized(self, code: str):
        return JsonResponse({"error": {"code": code}}, status=401)

    def _deny(self, code: str):
        return JsonResponse({"error": {"code": code}}, status=403)

    def _stepup(self, reason: Dict[str, Any], subject_id: str):
        from .stepup import create_challenge, verify_step_up_token

        challenge_id = reason.get("challenge_id", str(uuid.uuid4()))
        create_challenge(challenge_id, subject_id)
        return JsonResponse(
            {
                "error": {
                    "code": "STEP_UP_REQUIRED",
                    "message": "Additional authentication required",
                    "details": {
                        "challenge_id": challenge_id,
                        "methods": ["otp", "webauthn"],
                        "expires_in_seconds": 300,
                    },
                }
            },
            status=401,
        )

    @staticmethod
    def _sha256(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _now_iso() -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()
