import { cn } from "@/lib/utils";
import type { Severity } from "@/lib/types";
import { AlertTriangle, ShieldAlert, ShieldCheck, Info, Flame } from "lucide-react";

const map: Record<Severity, { label: string; cls: string; Icon: typeof AlertTriangle }> = {
  critical: { label: "CRITICAL", cls: "bg-severity-critical/15 text-severity-critical border-severity-critical/40", Icon: Flame },
  high: { label: "HIGH", cls: "bg-severity-high/15 text-severity-high border-severity-high/40", Icon: ShieldAlert },
  medium: { label: "MED", cls: "bg-severity-medium/15 text-severity-medium border-severity-medium/40", Icon: AlertTriangle },
  low: { label: "LOW", cls: "bg-severity-low/15 text-severity-low border-severity-low/40", Icon: ShieldCheck },
  info: { label: "INFO", cls: "bg-severity-info/15 text-severity-info border-severity-info/40", Icon: Info },
};

export function SeverityBadge({ severity, pulse, className }: { severity: Severity; pulse?: boolean; className?: string }) {
  const { label, cls, Icon } = map[severity];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-mono font-medium tracking-wider",
        cls,
        pulse && severity === "critical" && "alert-pulse",
        className,
      )}
    >
      <Icon className="h-3 w-3" />
      {label}
    </span>
  );
}
