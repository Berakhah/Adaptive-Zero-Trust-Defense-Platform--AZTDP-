import { useEffect, useState } from "react";
import { AppShell } from "@/components/soc/AppShell";
import { SectionHeader } from "@/components/soc/SectionHeader";
import { Heatmap24h } from "@/components/soc/Heatmap24h";
import { EventRow } from "@/components/soc/EventRow";
import { IncidentDrawer } from "@/components/soc/IncidentDrawer";
import { MonoId } from "@/components/soc/MonoId";
import { api } from "@/lib/api";
import type { AuditEvent, Severity } from "@/lib/types";
import { relTime } from "@/lib/format";
import { Button } from "@/components/ui/button";

const ORDER: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };

export default function Threats() {
  const [heat, setHeat] = useState<{ type: string; hours: number[] }[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [filter, setFilter] = useState<"all" | "deny" | "stepup">("all");
  const [selected, setSelected] = useState<AuditEvent | null>(null);

  useEffect(() => {
    api.heatmap().then(setHeat);
    api.events(120).then(setEvents);
  }, []);

  const alerts = events
    .filter((e) => e.severity === "critical" || e.severity === "high")
    .filter((e) => filter === "all" || e.decision === filter)
    .sort((a, b) => ORDER[a.severity] - ORDER[b.severity])
    .slice(0, 30);

  const revocations = events.filter((e) => e.event_type === "auth.token.revoked").slice(0, 10);

  return (
    <AppShell>
      <SectionHeader title="24h threat heatmap" subtitle="Event volume by hour and type" />
      <Heatmap24h data={heat} />

      <div className="mt-8">
        <SectionHeader
          title="Active alerts"
          subtitle={`${alerts.length} critical & high severity events`}
          actions={
            <div className="flex gap-1">
              {(["all", "deny", "stepup"] as const).map((f) => (
                <Button key={f} size="sm" variant={filter === f ? "default" : "outline"} className={`h-7 text-xs ${filter === f ? "bg-primary text-primary-foreground" : ""}`} onClick={() => setFilter(f)}>
                  {f}
                </Button>
              ))}
            </div>
          }
        />
        <div className="card-elev rounded-lg overflow-hidden">
          {alerts.map((e) => <EventRow key={e.event_id} event={e} onClick={() => setSelected(e)} />)}
          {alerts.length === 0 && <div className="p-8 text-center text-sm text-muted-foreground">No alerts match the current filter.</div>}
        </div>
      </div>

      <div className="mt-8">
        <SectionHeader title="Recent token revocations" subtitle="Forced invalidations issued by policy or operator" />
        <div className="card-elev rounded-lg overflow-hidden">
          <div className="grid grid-cols-[1fr_1fr_1fr_auto] px-3 py-2 border-b border-border bg-surface-2 text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
            <div>token jti</div><div>user</div><div>ip · geo</div><div>when</div>
          </div>
          {revocations.map((e) => (
            <div key={e.event_id} className="grid grid-cols-[1fr_1fr_1fr_auto] px-3 py-2 border-b border-border/50 items-center text-xs hover:bg-surface-2 cursor-pointer" onClick={() => setSelected(e)}>
              <MonoId value={e.token_jti_hash} len={10} />
              <span className="font-mono">{e.user_id}</span>
              <span className="font-mono text-muted-foreground">{e.ip} · {e.geo}</span>
              <span className="font-mono text-muted-foreground">{relTime(e.occurred_at)}</span>
            </div>
          ))}
          {revocations.length === 0 && <div className="p-8 text-center text-sm text-muted-foreground">No revocations in scope.</div>}
        </div>
      </div>

      <IncidentDrawer event={selected} onClose={() => setSelected(null)} />
    </AppShell>
  );
}
