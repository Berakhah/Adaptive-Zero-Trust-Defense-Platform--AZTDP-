import { useEffect, useState } from "react";
import { AppShell } from "@/components/soc/AppShell";
import { SectionHeader } from "@/components/soc/SectionHeader";
import { TimelinePanel } from "@/components/soc/TimelinePanel";
import { MonoId } from "@/components/soc/MonoId";
import { api } from "@/lib/api";
import type { SessionSummary, TimelineEvent } from "@/lib/types";
import { relTime } from "@/lib/format";
import { PlayCircle } from "lucide-react";

function ScoreBar({ value, tone }: { value: number; tone: "risk" | "anom" }) {
  const color = value > 70 ? "bg-severity-critical" : value > 40 ? "bg-severity-medium" : tone === "risk" ? "bg-accent" : "bg-primary/70";
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 rounded-full bg-surface-2 overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${value}%` }} />
      </div>
      <span className="font-mono text-xs tabular-nums w-7 text-right">{value}</span>
    </div>
  );
}

export default function Sessions() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selected, setSelected] = useState<SessionSummary | null>(null);
  const [replay, setReplay] = useState<TimelineEvent[] | null>(null);

  useEffect(() => {
    api.sessions().then((s) => {
      setSessions(s);
      if (s[0]) setSelected(s[0]);
    });
  }, []);

  useEffect(() => {
    if (!selected) return;
    setReplay(null);
    api.replay(selected.session_id).then(setReplay);
  }, [selected]);

  return (
    <AppShell>
      <SectionHeader title="Sessions" subtitle="Highest risk and anomaly scores per session, last 24h" />
      <div className="grid grid-cols-1 xl:grid-cols-[1.6fr_1fr] gap-4">
        <div className="card-elev rounded-lg overflow-hidden">
          <div className="grid grid-cols-[1.1fr_1fr_60px_1fr_1fr_auto_auto] px-3 py-2 bg-surface-2 border-b border-border text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
            <div>session</div><div>user</div><div>req</div><div>risk max</div><div>anomaly max</div><div>last seen</div><div></div>
          </div>
          <div className="max-h-[640px] overflow-y-auto">
            {sessions.map((s) => (
              <div
                key={s.session_id}
                onClick={() => setSelected(s)}
                className={`grid grid-cols-[1.1fr_1fr_60px_1fr_1fr_auto_auto] items-center gap-2 px-3 py-2.5 border-b border-border/50 cursor-pointer hover:bg-surface-2 ${selected?.session_id === s.session_id ? "bg-primary/5 border-l-2 border-l-primary" : ""}`}
              >
                <MonoId value={s.session_id} />
                <span className="font-mono text-xs">{s.user_id}</span>
                <span className="font-mono text-xs tabular-nums">{s.request_count}</span>
                <ScoreBar value={s.risk_max} tone="risk" />
                <ScoreBar value={s.anomaly_max} tone="anom" />
                <span className="font-mono text-[11px] text-muted-foreground whitespace-nowrap">{relTime(s.last_seen_at)}</span>
                <PlayCircle className="h-4 w-4 text-primary" />
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-4">
          {selected && (
            <div className="card-elev rounded-lg p-4 reveal">
              <div className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Replay target</div>
              <div className="mt-1"><MonoId value={selected.session_id} len={12} /></div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-xs font-mono">
                <div><span className="text-muted-foreground">User </span>{selected.user_id}</div>
                <div><span className="text-muted-foreground">IP </span>{selected.ip}</div>
                <div><span className="text-muted-foreground">Geo </span>{selected.geo}</div>
                <div><span className="text-muted-foreground">Reqs </span>{selected.request_count}</div>
              </div>
            </div>
          )}
          {replay ? <TimelinePanel events={replay} title="Replay timeline" /> : (
            <div className="card-elev rounded-lg p-8 text-center text-sm text-muted-foreground">Select a session to load replay.</div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
