import { cn } from "@/lib/utils";

interface KpiProps {
  label: string;
  value: string | number;
  delta?: { value: string; positive?: boolean };
  hint?: string;
  tone?: "default" | "warn" | "danger" | "good";
  className?: string;
  children?: React.ReactNode;
}

const toneRing = {
  default: "",
  warn: "ring-1 ring-severity-medium/30",
  danger: "ring-1 ring-severity-critical/40",
  good: "ring-1 ring-primary/30",
};

export function KpiCard({ label, value, delta, hint, tone = "default", className, children }: KpiProps) {
  return (
    <div className={cn("card-elev rounded-lg p-4 reveal", toneRing[tone], className)}>
      <div className="flex items-start justify-between">
        <div className="text-[11px] uppercase tracking-[0.14em] text-muted-foreground font-medium">{label}</div>
        {delta && (
          <span className={cn("text-xs font-mono", delta.positive ? "text-primary" : "text-severity-critical")}>{delta.value}</span>
        )}
      </div>
      <div className="mt-2 font-display text-3xl font-bold tabular-nums">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
      {children && <div className="mt-3">{children}</div>}
    </div>
  );
}
