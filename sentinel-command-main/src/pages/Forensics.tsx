import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/soc/AppShell";
import { SectionHeader } from "@/components/soc/SectionHeader";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EventRow } from "@/components/soc/EventRow";
import { IncidentDrawer } from "@/components/soc/IncidentDrawer";
import { TimelinePanel } from "@/components/soc/TimelinePanel";
import { MonoId } from "@/components/soc/MonoId";
import { DecisionBadge } from "@/components/soc/DecisionBadge";
import { api } from "@/lib/api";
import type { AuditEvent, Incident, TimelineEvent } from "@/lib/types";
import { Search } from "lucide-react";

type Kind = "events" | "incident" | "session";

function detectKind(q: string): Kind {
  if (!q) return "events";
  const uuidish = /^[0-9a-f-]{8,}$/i.test(q.trim());
  if (uuidish) return q.length > 30 ? "session" : "incident";
  return "events";
}

export default function Forensics() {
  const [q, setQ] = useState("");
  const [tab, setTab] = useState<Kind>("events");
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [selected, setSelected] = useState<AuditEvent | null>(null);
  const [incident, setIncident] = useState<Incident | null>(null);
  const [replay, setReplay] = useState<TimelineEvent[] | null>(null);

  useEffect(() => { api.events(80).then(setEvents); }, []);

  const filtered = useMemo(() => {
    if (!q) return events;
    const ql = q.toLowerCase();
    return events.filter((e) =>
      e.event_type.toLowerCase().includes(ql) ||
      e.user_id.toLowerCase().includes(ql) ||
      e.session_id.toLowerCase().includes(ql) ||
      e.request_id.toLowerCase().includes(ql) ||
      e.ip.includes(ql),
    );
  }, [events, q]);

  const onSearch = async () => {
    const k = detectKind(q);
    setTab(k);
    if (k === "incident" && q) api.incident(q).then(setIncident);
    if (k === "session" && q) api.replay(q).then(setReplay);
  };

  useEffect(() => {
    const k = detectKind(q);
    setTab(k);
  }, [q]);

  return (
    <AppShell>
      <SectionHeader title="Forensics" subtitle="Search events, incidents, and sessions" />

      <div className="card-elev rounded-lg p-3 flex items-center gap-2 reveal">
        <Search className="h-4 w-4 text-muted-foreground ml-1" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onSearch()}
          placeholder="user@host · session uuid · request_id · ip · event_type"
          className="flex-1 bg-transparent outline-none font-mono text-sm placeholder:text-muted-foreground"
        />
        <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground border border-border rounded px-1.5 py-0.5">
          inferred: {detectKind(q)}
        </span>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as Kind)} className="mt-6">
        <TabsList className="bg-surface-2 border border-border">
          <TabsTrigger value="events">Events</TabsTrigger>
          <TabsTrigger value="incident">Incident</TabsTrigger>
          <TabsTrigger value="session">Session</TabsTrigger>
        </TabsList>

        <TabsContent value="events" className="mt-4">
          <div className="card-elev rounded-lg overflow-hidden">
            {filtered.slice(0, 60).map((e) => <EventRow key={e.event_id} event={e} onClick={() => setSelected(e)} />)}
            {filtered.length === 0 && <div className="p-8 text-center text-sm text-muted-foreground">No matching events.</div>}
          </div>
        </TabsContent>

        <TabsContent value="incident" className="mt-4">
          {incident ? (
            <div className="card-elev rounded-lg p-5 reveal">
              <div className="flex items-center gap-3 flex-wrap">
                <h3 className="font-display text-lg font-bold">Incident summary</h3>
                <DecisionBadge decision={incident.decision} />
                <span className="text-xs font-mono text-muted-foreground">rule={incident.rule} · policy={incident.policy}</span>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
                <Stat label="Risk" value={incident.risk_score} />
                <Stat label="Anomaly" value={incident.anomaly_score} />
                <Stat label="Service" value={incident.service} mono />
                <Stat label="Endpoint" value={incident.endpoint_path} mono />
              </div>
              <div className="mt-5">
                <div className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground mb-2">Reasons</div>
                <ul className="space-y-1.5 text-sm">
                  {incident.reasons.map((r, i) => <li key={i}>▸ {r}</li>)}
                </ul>
              </div>
              <div className="mt-5 grid grid-cols-2 gap-3 text-xs">
                <div className="card-elev rounded-md p-3 space-y-1">
                  <div className="text-muted-foreground">Identity</div>
                  <div className="font-mono">{incident.user_id}</div>
                  <MonoId value={incident.session_id} />
                </div>
                <div className="card-elev rounded-md p-3 space-y-1">
                  <div className="text-muted-foreground">Origin</div>
                  <div className="font-mono">{incident.ip}</div>
                  <div className="font-mono">{incident.geo}</div>
                </div>
              </div>
            </div>
          ) : (
            <div className="card-elev rounded-lg p-8 text-center text-sm text-muted-foreground">Search a request_id to load incident details.</div>
          )}
        </TabsContent>

        <TabsContent value="session" className="mt-4">
          {replay ? <TimelinePanel events={replay} /> : (
            <div className="card-elev rounded-lg p-8 text-center text-sm text-muted-foreground">Search a session_id to load timeline.</div>
          )}
        </TabsContent>
      </Tabs>

      <IncidentDrawer event={selected} onClose={() => setSelected(null)} />
    </AppShell>
  );
}

function Stat({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="card-elev rounded-lg p-3">
      <div className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
      <div className={`mt-1 ${mono ? "font-mono text-sm" : "font-display text-2xl font-bold tabular-nums"}`}>{value}</div>
    </div>
  );
}
