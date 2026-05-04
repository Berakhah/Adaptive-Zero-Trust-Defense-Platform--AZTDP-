import { cn } from "@/lib/utils";
import type { Decision } from "@/lib/types";
import { Check, ShieldQuestion, Ban } from "lucide-react";

const map: Record<Decision, { label: string; cls: string; Icon: typeof Check }> = {
  allow: { label: "ALLOW", cls: "bg-decision-allow/15 text-decision-allow border-decision-allow/40", Icon: Check },
  stepup: { label: "STEP-UP", cls: "bg-decision-stepup/15 text-decision-stepup border-decision-stepup/40", Icon: ShieldQuestion },
  deny: { label: "DENY", cls: "bg-decision-deny/15 text-decision-deny border-decision-deny/40", Icon: Ban },
};

export function DecisionBadge({ decision, className }: { decision: Decision; className?: string }) {
  const { label, cls, Icon } = map[decision];
  return (
    <span className={cn("inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-mono font-semibold tracking-wider", cls, className)}>
      <Icon className="h-3 w-3" />
      {label}
    </span>
  );
}
