import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Play, Square, Zap } from "lucide-react";

const ATTACKS = [
  { id: "all", label: "Run all exercises" },
  { id: "credential-stuffing", label: "Credential stuffing" },
  { id: "impossible-travel", label: "Impossible travel" },
  { id: "token-replay", label: "Token replay" },
  { id: "privilege-escalation", label: "Privilege escalation" },
  { id: "session-fixation", label: "Session fixation" },
];

export function SimConsole() {
  const [attack, setAttack] = useState("all");
  const [running, setRunning] = useState(false);
  const [lines, setLines] = useState<string[]>([]);
  const ctrl = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  const start = () => {
    setLines([]);
    setRunning(true);
    ctrl.current = new AbortController();
    api.simStream(attack, (line) => setLines((p) => [...p, `${new Date().toLocaleTimeString()}  ${line}`]), ctrl.current.signal);
    setTimeout(() => setRunning(false), 6000);
  };
  const stop = () => {
    ctrl.current?.abort();
    setRunning(false);
    setLines((p) => [...p, `${new Date().toLocaleTimeString()}  [abort] exercise stopped by operator`]);
  };

  return (
    <div className="card-elev rounded-lg p-4 reveal">
      <div className="flex items-center gap-2 mb-3">
        <Zap className="h-4 w-4 text-primary" />
        <h3 className="font-display text-sm font-semibold uppercase tracking-wider">Attack simulation</h3>
        <div className="ml-auto flex items-center gap-2">
          <Select value={attack} onValueChange={setAttack} disabled={running}>
            <SelectTrigger className="h-8 w-[220px] bg-surface-2 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              {ATTACKS.map((a) => <SelectItem key={a.id} value={a.id}>{a.label}</SelectItem>)}
            </SelectContent>
          </Select>
          {!running ? (
            <Button onClick={start} size="sm" className="h-8 bg-primary text-primary-foreground hover:bg-primary/90">
              <Play className="h-3 w-3 mr-1" /> Launch
            </Button>
          ) : (
            <Button onClick={stop} size="sm" variant="destructive" className="h-8">
              <Square className="h-3 w-3 mr-1" /> Stop
            </Button>
          )}
        </div>
      </div>
      <div className="bg-background/80 grid-bg rounded-md border border-border h-[360px] overflow-y-auto p-3 font-mono text-xs">
        {lines.length === 0 && <div className="text-muted-foreground">// console idle — launch an exercise to stream events</div>}
        {lines.map((l, i) => (
          <div key={i} className="leading-relaxed">
            <span className="text-primary">›</span> <span className="text-foreground/90">{l}</span>
          </div>
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}
