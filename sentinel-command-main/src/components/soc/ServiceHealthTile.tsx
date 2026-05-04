import { cn } from "@/lib/utils";
import type { ServiceHealth } from "@/lib/types";
import { relTime } from "@/lib/format";
import { CircleDot } from "lucide-react";

const statusCls: Record<ServiceHealth["status"], string> = {
  healthy: "text-primary border-primary/40 bg-primary/10",
  degraded: "text-severity-medium border-severity-medium/40 bg-severity-medium/10",
  down: "text-severity-critical border-severity-critical/50 bg-severity-critical/10",
};

export function ServiceHealthTile({ svc }: { svc: ServiceHealth }) {
  return (
    <div className={cn("card-elev rounded-lg p-4 reveal", svc.status === "down" && "ring-1 ring-severity-critical/40")}>
      <div className="flex items-center justify-between">
        <div className="font-mono text-sm font-medium">{svc.name}</div>
        <span className={cn("inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-mono uppercase", statusCls[svc.status])}>
          <CircleDot className="h-3 w-3" />
          {svc.status}
        </span>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
        <div>
          <div className="text-muted-foreground text-[10px] uppercase tracking-wider">Latency</div>
          <div className="font-mono mt-0.5">{svc.latency_ms}ms</div>
        </div>
        <div>
          <div className="text-muted-foreground text-[10px] uppercase tracking-wider">Uptime</div>
          <div className="font-mono mt-0.5">{svc.uptime_pct}%</div>
        </div>
        <div>
          <div className="text-muted-foreground text-[10px] uppercase tracking-wider">Check</div>
          <div className="font-mono mt-0.5">{relTime(svc.last_check)}</div>
        </div>
      </div>
    </div>
  );
}
