import os

OPA_URL = os.getenv("AZTDP_OPA_URL", "http://opa:8181")
OPA_DECISION_PATH = os.getenv("AZTDP_OPA_DECISION_PATH", "/v1/data/aztdp/authz/decision")
REQUEST_TIMEOUT = float(os.getenv("AZTDP_POLICY_TIMEOUT", "0.8"))
FAIL_OPEN = os.getenv("AZTDP_FAIL_OPEN", "false").lower() == "true"
REDIS_URL = os.getenv("AZTDP_REDIS_URL", "")
REVOCATION_TTL_SECONDS = int(os.getenv("AZTDP_REVOCATION_TTL_SECONDS", "3600"))

_DEFAULT_EXP_GRACE_SECONDS = 300


def _parse_grace(raw: str) -> int:
    """Seconds a revocation outlives the token's `exp` (clock-skew margin).

    Relying parties accept tokens slightly past exp (Spring's JwtTimestampValidator
    allows 60 s, plus host clock drift), so the revocation must last longer.
    Unparseable values fall back to the default; negatives clamp to 0.
    """
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_EXP_GRACE_SECONDS
    return max(0, value)


REVOCATION_EXP_GRACE_SECONDS = _parse_grace(
    os.getenv("AZTDP_REVOCATION_EXP_GRACE_SECONDS", str(_DEFAULT_EXP_GRACE_SECONDS))
)
TELEMETRY_URL = os.getenv("AZTDP_TELEMETRY_URL", "")
DB_URL = os.getenv("AZTDP_DB_URL", "")
DB_CONNECT_TIMEOUT = int(os.getenv("AZTDP_DB_CONNECT_TIMEOUT", "3"))
REVOCATION_RESYNC_INTERVAL_SECONDS = float(os.getenv("AZTDP_REVOCATION_RESYNC_INTERVAL_SECONDS", "60"))
