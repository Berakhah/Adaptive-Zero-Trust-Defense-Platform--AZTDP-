import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import type { AuditEvent, Incident, TimelineEvent } from "@/lib/types";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { DecisionBadge } from "./DecisionBadge";
import { SeverityBadge } from "./SeverityBadge";
import { MonoId } from "./MonoId";
import { TimelinePanel } from "./TimelinePanel";
import { ArrowRight, MapPin, Server, User } from "lucide-react";

export function IncidentDrawer({ event, onClose }: { event: AuditEvent | null; onClose: () => void }) {
  const [incident, setIncident] = useState<Incident | null>(null);
  const [replay, setReplay] = useState<TimelineEvent[] | null>(null);
  const [showReplay, setShowReplay] = useState(false);

  useEffect(() => {
    setShowReplay(false);
    setReplay(null);
    if (!event) {
      setIncident(null);
      return;
    }
    api.incident(event.request_id, { decision: event.decision, user_id: event.user_id, session_id: event.session_id, ip: event.ip, geo: event.geo, service: event.service }).then(setIncident);
  }, [event]);

  const loadReplay = async () => {
    if (!event) return;
    const r = await api.replay(event.session_id);
    setReplay(r);
    setShowReplay(true);
  };

  return (
    <Sheet open={!!event} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full sm:max-w-xl bg-surface border-l border-border overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="font-display text-xl flex items-center gap-2">
            Incident
            {incident && <DecisionBadge decision={incident.decision} />}
            {event && <SeverityBadge severity={event.severity} pulse />}
          </SheetTitle>
        </SheetHeader>

        {event && incident && (
          <div className="mt-6 space-y-5">
            <div className="grid grid-cols-2 gap-3">
              <Stat label="Risk score" value={incident.risk_score} tone={incident.risk_score > 70 ? "danger" : "default"} />
              <Stat label="Anomaly score" value={incident.anomaly_score} tone={incident.anomaly_score > 70 ? "danger" : "default"} />
              <Stat label="Rule" value={<span className="font-mono text-sm">{incident.rule}</span>} />
              <Stat label="Policy" value={<span className="font-mono text-sm">{incident.policy}</span>} />
            </div>

            <div>
              <div className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground mb-2">Risk reasons</div>
              <ul className="space-y-1.5">
                {incident.reasons.map((r, i) => (
                  <li key={i} className="flex gap-2 text-sm">
                    <span className="text-severity-medium mt-0.5">▸</span>
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="card-elev rounded-lg p-3 space-y-2 text-sm">
              <Row icon={User} label="User"><span className="font-mono">{incident.user_id}</span></Row>
              <Row icon={Server} label="Service"><span className="font-mono">{incident.service} · {incident.endpoint_path}</span></Row>
              <Row icon={MapPin} label="Origin"><span className="font-mono">{incident.ip} · {incident.geo}</span></Row>
              <Row icon={ArrowRight} label="Request"><MonoId value={incident.request_id} /></Row>
              <Row icon={ArrowRight} label="Session"><MonoId value={incident.session_id} /></Row>
            </div>

            {!showReplay ? (
              <Button onClick={loadReplay} variant="default" className="w-full bg-primary text-primary-foreground hover:bg-primary/90">
                Load session replay
              </Button>
            ) : replay ? (
              <TimelinePanel events={replay} />
            ) : null}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

function Stat({ label, value, tone = "default" }: { label: string; value: React.ReactNode; tone?: "default" | "danger" }) {
  return (
    <div className={`card-elev rounded-lg p-3 ${tone === "danger" ? "ring-1 ring-severity-critical/40" : ""}`}>
      <div className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
      <div className="mt-1 font-display text-2xl font-bold tabular-nums">{value}</div>
    </div>
  );
}

function Row({ icon: Icon, label, children }: { icon: React.ComponentType<{ className?: string }>; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <Icon className="h-3.5 w-3.5 text-muted-foreground" />
      <span className="text-[11px] uppercase tracking-wider text-muted-foreground w-16">{label}</span>
      <div className="flex-1 min-w-0">{children}</div>
    </div>
  );
}
