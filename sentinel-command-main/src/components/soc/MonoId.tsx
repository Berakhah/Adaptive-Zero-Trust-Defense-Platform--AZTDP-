import { cn } from "@/lib/utils";
import { trunc } from "@/lib/format";
import { Copy } from "lucide-react";
import { useState } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export function MonoId({ value, len = 6, className, copyable = true }: { value: string; len?: number; className?: string; copyable?: boolean }) {
  const [copied, setCopied] = useState(false);
  const onCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          onClick={copyable ? onCopy : undefined}
          className={cn("inline-flex items-center gap-1 font-mono text-xs text-muted-foreground hover:text-foreground", copyable && "cursor-pointer", className)}
        >
          {trunc(value, len)}
          {copyable && <Copy className="h-3 w-3 opacity-50" />}
        </span>
      </TooltipTrigger>
      <TooltipContent className="font-mono text-xs">{copied ? "Copied" : value}</TooltipContent>
    </Tooltip>
  );
}
