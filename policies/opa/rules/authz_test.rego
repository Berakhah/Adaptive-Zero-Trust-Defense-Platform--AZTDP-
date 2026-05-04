package aztdp.authz

# Run with:  opa test policies/

_in(risk, sensitivity, roles, path) = {
  "subject": {"user_id": "u", "roles": roles},
  "resource": {"service": "django", "method": "GET", "path": path, "sensitivity": sensitivity},
  "context": {"risk_score": risk, "ip": "1.1.1.1", "geo": "US-CA"},
}

# ── allow band (risk < 0.65) ──
test_low_risk_low_sens_allows {
  decision.decision == "allow"
  with input as _in(0.10, 2, ["user"], "/v1/foo")
}

test_low_risk_high_sens_allows {  # was the regression that blocked all payments
  decision.decision == "allow"
  with input as _in(0.10, 4, ["user"], "/v1/payments/1")
}

test_low_risk_max_sens_allows {
  decision.decision == "allow"
  with input as _in(0.40, 5, ["user"], "/v1/admin/flags")  # not admin path-only — explicit prefix below
}

# ── stepup band (0.65 ≤ risk < 0.90) ──
test_high_risk_high_sens_stepup {
  result := decision with input as _in(0.70, 4, ["user"], "/v1/payments/1")
  result.decision == "stepup"
  result.reason.rule == "high_risk_high_sens"
}

test_high_risk_low_sens_stepup {
  result := decision with input as _in(0.70, 2, ["user"], "/v1/foo")
  result.decision == "stepup"
  result.reason.rule == "high_risk_normal_sens"
}

# ── revoke band (risk ≥ 0.90) ──
test_very_high_risk_revokes {
  result := decision with input as _in(0.95, 2, ["user"], "/v1/foo")
  result.decision == "revoke"
  result.reason.rule == "very_high_risk"
}

test_very_high_risk_revokes_even_on_high_sens {
  result := decision with input as _in(0.95, 4, ["user"], "/v1/payments/1")
  result.decision == "revoke"
}

# ── admin path enforcement ──
test_admin_path_without_admin_role_denies {
  result := decision with input as _in(0.10, 5, ["user"], "/v1/admin/flags")
  result.decision == "deny"
  result.reason.rule == "admin_required"
}

test_admin_path_with_admin_role_allows_when_low_risk {
  result := decision with input as _in(0.10, 5, ["admin"], "/v1/admin/flags")
  result.decision == "allow"
}

test_admin_path_with_admin_role_stepup_when_high_risk {
  result := decision with input as _in(0.70, 5, ["admin"], "/v1/admin/flags")
  result.decision == "stepup"
}

test_admin_path_with_admin_role_revoke_when_very_high_risk {
  result := decision with input as _in(0.95, 5, ["admin"], "/v1/admin/flags")
  result.decision == "revoke"
}

# ── boundary tests ──
test_risk_at_0_65_is_high_risk {
  result := decision with input as _in(0.65, 4, ["user"], "/v1/payments/1")
  result.decision == "stepup"
}

test_risk_at_0_64_is_low_risk {
  result := decision with input as _in(0.64, 4, ["user"], "/v1/payments/1")
  result.decision == "allow"
}

test_risk_at_0_90_is_very_high_risk {
  result := decision with input as _in(0.90, 4, ["user"], "/v1/payments/1")
  result.decision == "revoke"
}

test_risk_at_0_89_is_stepup {
  result := decision with input as _in(0.89, 4, ["user"], "/v1/payments/1")
  result.decision == "stepup"
}
