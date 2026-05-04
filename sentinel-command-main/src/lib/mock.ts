import type { AuditEvent, Decision, Incident, ServiceHealth, SessionSummary, Severity, TimelineEvent } from "./types";

const SERVICES = ["auth-svc", "policy-svc", "risk-svc", "forensics-svc", "gateway", "sim-svc"];
const EVENT_TYPES = [
  "auth.login.success",
  "auth.login.failed",
  "auth.token.issued",
  "auth.token.revoked",
  "policy.deny",
  "policy.stepup",
  "policy.allow",
  "risk.elevated",
  "risk.anomaly.detected",
  "session.replay.suspect",
  "ip.geo.shift",
  "device.new",
];
const RULES = ["impossible-travel", "geo-velocity", "device-untrusted", "ip-rep-low", "tor-exit", "burst-mfa-fail", "session-fixation"];
const POLICIES = ["zt-baseline", "zt-strict", "zt-finance", "zt-admin"];
const GEOS = ["US-CA", "US-NY", "DE-BE", "BR-SP", "JP-13", "RU-MOW", "CN-11", "NG-LA", "GB-LND"];
const USERS = ["alice@aztdp.io", "bob@aztdp.io", "carol@aztdp.io", "dave@aztdp.io", "eve@external.io", "ops@aztdp.io"];

let seed = 42;
const rand = () => {
  seed = (seed * 1664525 + 1013904223) % 4294967296;
  return seed / 4294967296;
};
const pick = <T>(arr: T[]) => arr[Math.floor(rand() * arr.length)];
const hex = (n: number) => Array.from({ length: n }, () => Math.floor(rand() * 16).toString(16)).join("");
const uuid = () => `${hex(8)}-${hex(4)}-${hex(4)}-${hex(4)}-${hex(12)}`;
const ip = () => `${Math.floor(rand() * 223) + 1}.${Math.floor(rand() * 255)}.${Math.floor(rand() * 255)}.${Math.floor(rand() * 255)}`;

const SESSION_IDS = Array.from({ length: 18 }, () => uuid());

const decisionFor = (type: string): Decision | undefined => {
  if (type.includes("deny")) return "deny";
  if (type.includes("stepup")) return "stepup";
  if (type.includes("allow") || type === "auth.login.success") return "allow";
  return undefined;
};
const severityFor = (type: string): Severity => {
  if (type.includes("revoked") || type.includes("anomaly") || type.includes("suspect")) return "critical";
  if (type.includes("deny") || type.includes("elevated") || type === "auth.login.failed") return "high";
  if (type.includes("stepup") || type.includes("geo.shift") || type === "device.new") return "medium";
  if (type.includes("allow")) return "low";
  return "info";
};

export const genEvents = (count = 80): AuditEvent[] => {
  const out: AuditEvent[] = [];
  const now = Date.now();
  for (let i = 0; i < count; i++) {
    const type = pick(EVENT_TYPES);
    const session_id = pick(SESSION_IDS);
    out.push({
      event_id: uuid(),
      event_type: type,
      service: pick(SERVICES),
      request_id: uuid(),
      session_id,
      user_id: pick(USERS),
      token_jti_hash: hex(32),
      ip: ip(),
      geo: pick(GEOS),
      payload: { ua: "Mozilla/5.0", method: pick(["GET", "POST", "PATCH"]), path: pick(["/api/me", "/api/transfer", "/api/admin/users", "/api/files"]) },
      occurred_at: new Date(now - i * 1000 * (10 + rand() * 60)).toISOString(),
      severity: severityFor(type),
      decision: decisionFor(type),
      risk_score: Math.round(rand() * 100),
      anomaly_score: Math.round(rand() * 100),
    });
  }
  return out;
};

export const genIncident = (request_id: string, base?: Partial<Incident>): Incident => ({
  request_id,
  decision: base?.decision ?? "deny",
  rule: pick(RULES),
  policy: pick(POLICIES),
  risk_score: 70 + Math.floor(rand() * 30),
  anomaly_score: 60 + Math.floor(rand() * 40),
  service: pick(SERVICES),
  endpoint_path: pick(["/api/transfer", "/api/admin/users", "/api/files/export", "/api/me"]),
  decided_at: new Date().toISOString(),
  reasons: [
    "Impossible travel: 2 logins, 4,820 km in 9 minutes",
    "Device fingerprint not previously seen for user",
    "IP reputation score below threshold (12/100)",
    "Anomalous request rate vs 30-day baseline (+412%)",
  ].slice(0, 2 + Math.floor(rand() * 3)),
  user_id: pick(USERS),
  session_id: pick(SESSION_IDS),
  ip: ip(),
  geo: pick(GEOS),
  ...base,
});

export const genReplay = (session_id: string): TimelineEvent[] => {
  const types = ["auth.login.success", "policy.allow", "risk.elevated", "policy.stepup", "auth.token.issued", "policy.deny", "auth.token.revoked"];
  const start = Date.now() - 1000 * 60 * 8;
  return types.map((t, i) => ({
    event_type: t,
    occurred_at: new Date(start + i * (30000 + rand() * 90000)).toISOString(),
    delta_ms: i === 0 ? 0 : Math.floor(20000 + rand() * 90000),
    payload: { session_id, idx: i },
    decision: decisionFor(t),
    severity: severityFor(t),
  }));
};

export const genSessions = (count = 24): SessionSummary[] =>
  SESSION_IDS.slice(0, count).map((id, i) => ({
    session_id: id,
    user_id: pick(USERS),
    request_count: Math.floor(20 + rand() * 400),
    risk_max: Math.floor(rand() * 100),
    anomaly_max: Math.floor(rand() * 100),
    last_seen_at: new Date(Date.now() - i * 60000 * (1 + rand() * 30)).toISOString(),
    ip: ip(),
    geo: pick(GEOS),
  }));

export const genServices = (): ServiceHealth[] =>
  ["gateway", "auth-svc", "policy-svc", "risk-svc", "forensics-svc", "sim-svc", "prometheus", "redis"].map((name, i) => {
    const status: ServiceHealth["status"] = i === 4 ? "degraded" : i === 7 ? "down" : "healthy";
    return {
      name,
      status,
      latency_ms: Math.floor(8 + rand() * 90),
      last_check: new Date(Date.now() - rand() * 60000).toISOString(),
      uptime_pct: status === "healthy" ? 99.9 : status === "degraded" ? 97.4 : 88.1,
    };
  });

export const genHeatmap = () => {
  const types = ["policy.deny", "policy.stepup", "auth.login.failed", "risk.elevated", "risk.anomaly.detected", "auth.token.revoked"];
  return types.map((t) => ({
    type: t,
    hours: Array.from({ length: 24 }, () => Math.floor(rand() * 100)),
  }));
};

export const genDecisionsSeries = () =>
  Array.from({ length: 24 }, (_, i) => ({
    hour: `${i}:00`,
    allow: Math.floor(800 + rand() * 600),
    stepup: Math.floor(40 + rand() * 90),
    deny: Math.floor(8 + rand() * 50),
  }));

export const genTopRules = () =>
  RULES.map((r) => ({ rule: r, count: Math.floor(20 + rand() * 400) })).sort((a, b) => b.count - a.count);
