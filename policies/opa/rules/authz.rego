package aztdp.authz

# Decision ladder, evaluated top to bottom:
#   1. /v1/admin/* without admin role         -> deny  (admin_required)
#   2. risk >= 0.90                           -> revoke (very_high_risk; was deny in v1)
#   3. risk >= 0.65 AND sensitivity >= 4      -> stepup (high_risk_high_sens)
#   4. risk >= 0.65 AND sensitivity <= 3      -> stepup (high_risk_normal_sens)
#   5. risk <  0.65 (any sensitivity)         -> allow  (low_risk)
#   6. fallthrough                            -> deny   (default_deny)
#
# Note: the gateway short-circuits on revocation BEFORE calling OPA, so the
# `is_token_revoked` rule that lived here in v1 was dead code and has been
# removed (see P1.4). Revocation enforcement lives in the gateway only.

default decision = {
  "decision": "deny",
  "reason": {
    "policy": "aztdp.authz",
    "rule": "default_deny"
  }
}

admin_path {
  startswith(input.resource.path, "/v1/admin")
}

has_admin_role {
  input.subject.roles[_] == "admin"
}

high_risk {
  input.context.risk_score >= 0.65
}

very_high_risk {
  input.context.risk_score >= 0.90
}

decision = {
  "decision": "deny",
  "reason": {
    "policy": "aztdp.authz",
    "rule": "admin_required"
  }
} {
  admin_path
  not has_admin_role
} else = {
  "decision": "revoke",
  "reason": {
    "policy": "aztdp.authz",
    "rule": "very_high_risk"
  }
} {
  very_high_risk
} else = {
  "decision": "stepup",
  "reason": {
    "policy": "aztdp.authz",
    "rule": "high_risk_high_sens"
  }
} {
  high_risk
  input.resource.sensitivity >= 4
} else = {
  "decision": "stepup",
  "reason": {
    "policy": "aztdp.authz",
    "rule": "high_risk_normal_sens"
  }
} {
  high_risk
} else = {
  "decision": "allow",
  "reason": {
    "policy": "aztdp.authz",
    "rule": "low_risk"
  }
} {
  not high_risk
}
