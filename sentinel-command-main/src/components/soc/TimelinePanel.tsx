import type { TimelineEvent } from "@/lib/types";
import { DecisionBadge } from "./DecisionBadge";
import { SeverityBadge } from "./SeverityBadge";
import { Clock } from "lucide-react";

export function TimelinePanel({ events, title = "Session timeline" }: { events: TimelineEvent[]; title?: string }) {
  return (
    <div className="card-elev rounded-lg p-4 reveal">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-muted-foreground">{title}</h3>
        <Clock className="h-4 w-4 text-muted-foreground" />
      </div>
      <ol className="relative border-l border-border/60 ml-2">
        {events.map((e, i) => (
          <li key={i} className="ml-4 pb-4 last:pb-0">
            <span className="absolute -left-[5px] mt-1.5 h-2 w-2 rounded-full bg-primary ring-2 ring-background" />
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-xs">{e.event_type}</span>
              {e.decision && <DecisionBadge decision={e.decision} />}
              {e.severity && <SeverityBadge severity={e.severity} />}
              {i > 0 && <span className="text-[10px] text-muted-foreground font-mono">+{(e.delta_ms / 1000).toFixed(1)}s</span>}
            </div>
            <div className="text-[11px] text-muted-foreground font-mono mt-0.5">{new Date(e.occurred_at).toLocaleTimeString()}</div>
          </li>
        ))}
      </ol>
    </div>
  );
}
