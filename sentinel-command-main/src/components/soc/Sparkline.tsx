import { cn } from "@/lib/utils";

export function Sparkline({ data, className, color = "hsl(var(--primary))" }: { data: number[]; className?: string; color?: string }) {
  const w = 120, h = 32;
  const min = Math.min(...data), max = Math.max(...data);
  const span = max - min || 1;
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / span) * h}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className={cn("w-full h-8", className)} preserveAspectRatio="none">
      <polyline fill="none" stroke={color} strokeWidth="1.5" points={pts} />
    </svg>
  );
}
