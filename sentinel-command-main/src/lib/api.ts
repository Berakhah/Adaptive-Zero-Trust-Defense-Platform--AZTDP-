import { genDecisionsSeries, genEvents, genHeatmap, genIncident, genReplay, genServices, genSessions, genTopRules } from "./mock";
import type { AuditEvent, Incident, ServiceHealth, SessionSummary, TimelineEvent } from "./types";

const USE_MOCK = (import.meta.env.VITE_USE_MOCK ?? "true") !== "false";
const BASE = import.meta.env.VITE_API_BASE ?? "/api";

const wrap = async <T>(real: () => Promise<T>, mock: () => T): Promise<T> => {
  if (USE_MOCK) return mock();
  try {
    return await real();
  } catch {
    return mock();
  }
};

const j = async <T>(url: string): Promise<T> => {
  const r = await fetch(url);
  if (!r.ok) throw new Error(String(r.status));
  return r.json() as Promise<T>;
};

export const api = {
  events: (limit = 100): Promise<AuditEvent[]> =>
    wrap<AuditEvent[]>(() => j<AuditEvent[]>(`${BASE}/forensics/v1/forensics/events?limit=${limit}`), () => genEvents(limit)),
  replay: (session_id: string): Promise<TimelineEvent[]> =>
    wrap<TimelineEvent[]>(() => j<TimelineEvent[]>(`${BASE}/forensics/v1/forensics/replay/${session_id}`), () => genReplay(session_id)),
  incident: (request_id: string, base?: Partial<Incident>): Promise<Incident> =>
    wrap<Incident>(() => j<Incident>(`${BASE}/forensics/v1/forensics/incidents/${request_id}`), () => genIncident(request_id, base)),
  prom: (query: string) =>
    wrap(() => j(`${BASE}/prometheus/api/v1/query?query=${encodeURIComponent(query)}`), () => ({ data: { result: [] } })),
  health: (): Promise<ServiceHealth[]> => Promise.resolve(genServices()),
  sessions: (): Promise<SessionSummary[]> => Promise.resolve(genSessions()),
  heatmap: () => Promise.resolve(genHeatmap()),
  decisionsSeries: () => Promise.resolve(genDecisionsSeries()),
  topRules: () => Promise.resolve(genTopRules()),
  simStream: (attack: string, onLine: (s: string) => void, signal: AbortSignal) => {
    if (!USE_MOCK) {
      const es = new EventSource(`${BASE}/sim/v1/sim/all/run?attack=${attack}`);
      es.onmessage = (e) => onLine(e.data);
      signal.addEventListener("abort", () => es.close());
      return;
    }
    const lines = [
      `[boot] launching exercise: ${attack}`,
      `[recon] enumerating endpoints…`,
      `[probe] /api/auth/login 200`,
      `[brute] attempt 1/50 → policy.stepup`,
      `[brute] attempt 7/50 → policy.deny rule=burst-mfa-fail`,
      `[geo] simulating impossible-travel from RU-MOW`,
      `[risk] risk_score elevated to 87`,
      `[anomaly] anomaly_score=92 (baseline +412%)`,
      `[token] revoked jti=${Math.random().toString(16).slice(2, 14)}`,
      `[done] exercise complete — 3 denies, 4 stepups, 1 revocation`,
    ];
    let i = 0;
    const tick = () => {
      if (signal.aborted || i >= lines.length) return;
      onLine(lines[i++]);
      setTimeout(tick, 350 + Math.random() * 500);
    };
    tick();
  },
};
