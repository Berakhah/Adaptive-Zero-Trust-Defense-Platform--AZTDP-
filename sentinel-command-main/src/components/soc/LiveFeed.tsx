import { useEffect, useRef, useState } from "react";
import type { AuditEvent } from "@/lib/types";
import { api } from "@/lib/api";
import { EventRow } from "./EventRow";
import { Pause, Play } from "lucide-react";
import { Button } from "@/components/ui/button";

export function LiveFeed({ onSelect, limit = 60 }: { onSelect: (e: AuditEvent) => void; limit?: number }) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [paused, setPaused] = useState(false);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  useEffect(() => {
    api.events(limit).then(setEvents);
    const id = setInterval(async () => {
      if (pausedRef.current) return;
      const fresh = await api.events(3);
      setEvents((prev) => [...fresh.map((e) => ({ ...e, occurred_at: new Date().toISOString() })), ...prev].slice(0, limit));
    }, 3500);
    return () => clearInterval(id);
  }, [limit]);

  return (
    <div className="card-elev rounded-lg overflow-hidden flex flex-col">
      <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-surface-2">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className={`absolute inline-flex h-full w-full rounded-full bg-primary ${paused ? "" : "animate-ping opacity-60"}`} />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
          </span>
          <span className="text-xs font-mono uppercase tracking-wider text-muted-foreground">{paused ? "Paused" : "Live"}</span>
        </div>
        <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => setPaused((p) => !p)}>
          {paused ? <Play className="h-3 w-3 mr-1" /> : <Pause className="h-3 w-3 mr-1" />}
          {paused ? "Resume" : "Pause"}
        </Button>
      </div>
      <div className="max-h-[520px] overflow-y-auto">
        {events.map((e) => (
          <EventRow key={e.event_id} event={e} onClick={() => onSelect(e)} dense />
        ))}
      </div>
    </div>
  );
}
