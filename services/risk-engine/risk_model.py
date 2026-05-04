import time
from typing import Any, Dict, List, Tuple

from . import config


def score_risk(request: Dict[str, Any], last_seen: Dict[str, Any] | None) -> Tuple[float, List[Dict[str, Any]], bool]:
    risk = config.RISK_BASE
    reasons: List[Dict[str, Any]] = []
    replay_detected = False

    sensitivity = int(request.get("endpoint", {}).get("sensitivity", 2))
    if sensitivity >= 4:
        risk += config.RISK_SENSITIVITY_WEIGHT
        reasons.append({"code": "HIGH_SENSITIVITY", "weight": config.RISK_SENSITIVITY_WEIGHT})

    if last_seen:
        if request.get("ip") and last_seen.get("ip") and request.get("ip") != last_seen.get("ip"):
            risk += config.RISK_IP_DRIFT_WEIGHT
            reasons.append({"code": "IP_GEO_DRIFT", "weight": config.RISK_IP_DRIFT_WEIGHT})
            if time.time() - float(last_seen.get("ts", 0)) < config.REPLAY_WINDOW_SECONDS:
                replay_detected = True

        if request.get("user_agent_hash") and last_seen.get("ua") and request.get("user_agent_hash") != last_seen.get("ua"):
            risk += config.RISK_UA_DRIFT_WEIGHT
            reasons.append({"code": "NEW_DEVICE", "weight": config.RISK_UA_DRIFT_WEIGHT})

        if request.get("geo") and last_seen.get("geo") and request.get("geo") != last_seen.get("geo"):
            risk += config.RISK_GEO_DRIFT_WEIGHT
            reasons.append({"code": "GEO_DRIFT", "weight": config.RISK_GEO_DRIFT_WEIGHT})

    risk = min(risk, 1.0)
    return risk, reasons, replay_detected
