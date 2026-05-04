import os

OPA_URL = os.getenv("AZTDP_OPA_URL", "http://opa:8181")
OPA_DECISION_PATH = os.getenv("AZTDP_OPA_DECISION_PATH", "/v1/data/aztdp/authz/decision")
REQUEST_TIMEOUT = float(os.getenv("AZTDP_POLICY_TIMEOUT", "0.8"))
FAIL_OPEN = os.getenv("AZTDP_FAIL_OPEN", "false").lower() == "true"
REDIS_URL = os.getenv("AZTDP_REDIS_URL", "")
REVOCATION_TTL_SECONDS = int(os.getenv("AZTDP_REVOCATION_TTL_SECONDS", "3600"))
TELEMETRY_URL = os.getenv("AZTDP_TELEMETRY_URL", "")
DB_URL = os.getenv("AZTDP_DB_URL", "")
