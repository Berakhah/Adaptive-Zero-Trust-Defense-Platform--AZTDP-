package com.aztdp.springapp.model;

import java.util.HashMap;
import java.util.Map;

public class PolicyDecision {
    private String decision;
    private Map<String, String> reason = new HashMap<>();

    public static PolicyDecision fromMap(Map<String, Object> map) {
        PolicyDecision decision = new PolicyDecision();
        Object action = map.get("decision");
        decision.decision = action == null ? "deny" : action.toString();
        Object reasonObj = map.get("reason");
        if (reasonObj instanceof Map<?, ?> reasonMap) {
            for (Map.Entry<?, ?> entry : reasonMap.entrySet()) {
                decision.reason.put(entry.getKey().toString(), entry.getValue().toString());
            }
        }
        return decision;
    }

    public static PolicyDecision deny(String code) {
        PolicyDecision decision = new PolicyDecision();
        decision.decision = "deny";
        decision.reason.put("code", code);
        return decision;
    }

    public String getDecision() {
        return decision == null ? "deny" : decision;
    }

    public Map<String, String> getReason() {
        return reason;
    }
}
