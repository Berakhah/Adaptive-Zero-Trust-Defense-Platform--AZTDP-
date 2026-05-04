import type { AuditEvent } from "@/lib/types";
import { SeverityBadge } from "./SeverityBadge";
import { DecisionBadge } from "./DecisionBadge";
import { MonoId } from "./MonoId";
import { relTime } from "@/lib/format";
import { cn } from "@/lib/utils";

export function EventRow({ event, onClick, dense }: { event: AuditEvent; onClick?: () => void; dense?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left grid items-center gap-3 px-3 hover:bg-surface-2 border-b border-border/50 transition-colors",
        dense ? "py-1.5" : "py-2.5",
        "grid-cols-[80px_1fr_auto_auto_auto]",
        event.severity === "critical" && "border-l-2 border-l-severity-critical",
      )}
    >
      <div className="flex items-center gap-1">
        <SeverityBadge severity={event.severity} />
      </div>
      <div className="min-w-0">
        <div className="font-mono text-xs truncate">{event.event_type}</div>
        <div className="text-[10px] text-muted-foreground font-mono truncate">
          {event.service} · {event.user_id} · {event.geo}
        </div>
      </div>
      {event.decision && <DecisionBadge decision={event.decision} />}
      <MonoId value={event.request_id} />
      <span className="text-[11px] text-muted-foreground font-mono whitespace-nowrap">{relTime(event.occurred_at)}</span>
    </button>
  );
}
