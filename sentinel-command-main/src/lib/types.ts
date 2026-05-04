export type Decision = "allow" | "stepup" | "deny";
export type Severity = "critical" | "high" | "medium" | "low" | "info";

export interface AuditEvent {
  event_id: string;
  event_type: string;
  service: string;
  request_id: string;
  session_id: string;
  user_id: string;
  token_jti_hash: string;
  ip: string;
  geo: string;
  payload: Record<string, unknown>;
  occurred_at: string;
  severity: Severity;
  decision?: Decision;
  risk_score?: number;
  anomaly_score?: number;
}

export interface Incident {
  request_id: string;
  decision: Decision;
  rule: string;
  policy: string;
  risk_score: number;
  anomaly_score: number;
  service: string;
  endpoint_path: string;
  decided_at: string;
  reasons: string[];
  user_id: string;
  session_id: string;
  ip: string;
  geo: string;
}

export interface TimelineEvent {
  event_type: string;
  occurred_at: string;
  delta_ms: number;
  payload: Record<string, unknown>;
  decision?: Decision;
  severity?: Severity;
}

export interface SessionSummary {
  session_id: string;
  user_id: string;
  request_count: number;
  risk_max: number;
  anomaly_max: number;
  last_seen_at: string;
  ip: string;
  geo: string;
}

export interface ServiceHealth {
  name: string;
  status: "healthy" | "degraded" | "down";
  latency_ms: number;
  last_check: string;
  uptime_pct: number;
}
