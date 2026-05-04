import { cn } from "@/lib/utils";

export function Heatmap24h({ data }: { data: { type: string; hours: number[] }[] }) {
  const max = Math.max(...data.flatMap((d) => d.hours), 1);
  return (
    <div className="card-elev rounded-lg p-4 reveal overflow-x-auto">
      <div className="min-w-[640px]">
        <div className="grid" style={{ gridTemplateColumns: "180px repeat(24, 1fr)" }}>
          <div />
          {Array.from({ length: 24 }, (_, h) => (
            <div key={h} className="text-[10px] font-mono text-muted-foreground text-center pb-1">
              {h.toString().padStart(2, "0")}
            </div>
          ))}
          {data.map((row) => (
            <div key={row.type} className="contents">
              <div className="text-xs font-mono text-muted-foreground pr-3 py-1 truncate">{row.type}</div>
              {row.hours.map((v, i) => {
                const intensity = v / max;
                const isHot = intensity > 0.7;
                return (
                  <div
                    key={i}
                    className={cn("h-6 m-[1px] rounded-sm border border-border/40")}
                    style={{
                      backgroundColor: isHot
                        ? `hsl(var(--severity-critical) / ${0.25 + intensity * 0.6})`
                        : intensity > 0.4
                        ? `hsl(var(--severity-medium) / ${0.2 + intensity * 0.5})`
                        : `hsl(var(--accent) / ${0.08 + intensity * 0.4})`,
                    }}
                    title={`${row.type} @ ${i}:00 — ${v}`}
                  />
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
