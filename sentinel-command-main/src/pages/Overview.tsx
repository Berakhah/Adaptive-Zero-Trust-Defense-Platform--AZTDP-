import { useEffect, useState } from "react";
import { AppShell } from "@/components/soc/AppShell";
import { KpiCard } from "@/components/soc/KpiCard";
import { Sparkline } from "@/components/soc/Sparkline";
import { LiveFeed } from "@/components/soc/LiveFeed";
import { SectionHeader } from "@/components/soc/SectionHeader";
import { IncidentDrawer } from "@/components/soc/IncidentDrawer";
import { api } from "@/lib/api";
import type { AuditEvent } from "@/lib/types";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";

export default function Overview() {
  const [selected, setSelected] = useState<AuditEvent | null>(null);
  const [series, setSeries] = useState<{ hour: string; allow: number; stepup: number; deny: number }[]>([]);
  const [rules, setRules] = useState<{ rule: string; count: number }[]>([]);

  useEffect(() => {
    api.decisionsSeries().then(setSeries);
    api.topRules().then(setRules);
  }, []);

  const sparkA = Array.from({ length: 24 }, () => Math.random() * 50 + 10);
  const sparkB = Array.from({ length: 24 }, () => Math.random() * 30 + 5);
  const sparkC = Array.from({ length: 24 }, () => Math.random() * 80 + 40);
  const sparkD = Array.from({ length: 24 }, () => Math.random() * 100 + 200);

  return (
    <AppShell>
      <SectionHeader
        title="Threat posture"
        subtitle="Last 1 hour · streaming"
        actions={<span className="text-xs font-mono text-muted-foreground">env=production · region=us-east-1</span>}
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Deny rate (1h)" value="3.4%" delta={{ value: "+0.8pp", positive: false }} hint="vs 24h avg 2.6%" tone="danger">
          <Sparkline data={sparkA} color="hsl(var(--severity-critical))" />
        </KpiCard>
        <KpiCard label="Step-up rate" value="11.7%" delta={{ value: "−1.2pp", positive: true }} hint="MFA challenges issued" tone="warn">
          <Sparkline data={sparkB} color="hsl(var(--severity-medium))" />
        </KpiCard>
        <KpiCard label="Anomaly p95" value="74" delta={{ value: "+6", positive: false }} hint="risk-svc score" tone="danger">
          <Sparkline data={sparkC} color="hsl(var(--severity-high))" />
        </KpiCard>
        <KpiCard label="Active sessions" value="3,481" delta={{ value: "+184", positive: true }} hint="across 8 services" tone="good">
          <Sparkline data={sparkD} />
        </KpiCard>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 mt-6">
        <div className="card-elev rounded-lg p-4 reveal xl:col-span-2">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-display text-sm font-semibold uppercase tracking-wider">Decisions · 24h</h3>
            <div className="flex gap-3 text-[10px] font-mono uppercase tracking-wider">
              <Legend color="hsl(var(--decision-allow))" label="allow" />
              <Legend color="hsl(var(--decision-stepup))" label="step-up" />
              <Legend color="hsl(var(--decision-deny))" label="deny" />
            </div>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={series}>
              <defs>
                <linearGradient id="g-allow" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="hsl(var(--decision-allow))" stopOpacity={0.5} /><stop offset="100%" stopColor="hsl(var(--decision-allow))" stopOpacity={0} /></linearGradient>
                <linearGradient id="g-stepup" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="hsl(var(--decision-stepup))" stopOpacity={0.5} /><stop offset="100%" stopColor="hsl(var(--decision-stepup))" stopOpacity={0} /></linearGradient>
                <linearGradient id="g-deny" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="hsl(var(--decision-deny))" stopOpacity={0.6} /><stop offset="100%" stopColor="hsl(var(--decision-deny))" stopOpacity={0} /></linearGradient>
              </defs>
              <CartesianGrid stroke="hsl(var(--border))" vertical={false} />
              <XAxis dataKey="hour" tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10, fontFamily: "JetBrains Mono" }} stroke="hsl(var(--border))" />
              <YAxis tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10, fontFamily: "JetBrains Mono" }} stroke="hsl(var(--border))" />
              <RTooltip contentStyle={{ background: "hsl(var(--surface-2))", border: "1px solid hsl(var(--border))", fontSize: 12 }} />
              <Area type="monotone" dataKey="allow" stackId="1" stroke="hsl(var(--decision-allow))" fill="url(#g-allow)" />
              <Area type="monotone" dataKey="stepup" stackId="1" stroke="hsl(var(--decision-stepup))" fill="url(#g-stepup)" />
              <Area type="monotone" dataKey="deny" stackId="1" stroke="hsl(var(--decision-deny))" fill="url(#g-deny)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="card-elev rounded-lg p-4 reveal">
          <h3 className="font-display text-sm font-semibold uppercase tracking-wider mb-2">Top rules triggered</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={rules} layout="vertical" margin={{ left: 24 }}>
              <CartesianGrid stroke="hsl(var(--border))" horizontal={false} />
              <XAxis type="number" tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10, fontFamily: "JetBrains Mono" }} stroke="hsl(var(--border))" />
              <YAxis type="category" dataKey="rule" width={120} tick={{ fill: "hsl(var(--foreground))", fontSize: 10, fontFamily: "JetBrains Mono" }} stroke="hsl(var(--border))" />
              <RTooltip contentStyle={{ background: "hsl(var(--surface-2))", border: "1px solid hsl(var(--border))", fontSize: 12 }} />
              <Bar dataKey="count" fill="hsl(var(--accent))" radius={[0, 3, 3, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-5 gap-4 mt-6">
        <div className="xl:col-span-3">
          <SectionHeader title="Live event feed" subtitle="Click any event for forensics" />
          <LiveFeed onSelect={setSelected} />
        </div>
        <div className="xl:col-span-2">
          <SectionHeader title="Posture summary" />
          <div className="card-elev rounded-lg p-5 reveal space-y-4">
            <PostureRow label="Identity perimeter" status="HARDENED" tone="good" detail="MFA enforced on 100% of admin paths" />
            <PostureRow label="Token hygiene" status="ATTENTION" tone="warn" detail="14 tokens revoked in last hour" />
            <PostureRow label="Network egress" status="STABLE" tone="good" detail="No anomalous outbound flows" />
            <PostureRow label="Active incidents" status="3 OPEN" tone="danger" detail="2 critical · 1 high — assigned to oncall" />
            <PostureRow label="Policy drift" status="NONE" tone="good" detail="All services aligned to zt-baseline" />
          </div>
        </div>
      </div>

      <IncidentDrawer event={selected} onClose={() => setSelected(null)} />
    </AppShell>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-muted-foreground">
      <span className="h-2 w-2 rounded-sm" style={{ background: color }} />
      {label}
    </span>
  );
}

function PostureRow({ label, status, tone, detail }: { label: string; status: string; tone: "good" | "warn" | "danger"; detail: string }) {
  const cls = tone === "good" ? "text-primary border-primary/40 bg-primary/10" : tone === "warn" ? "text-severity-medium border-severity-medium/40 bg-severity-medium/10" : "text-severity-critical border-severity-critical/40 bg-severity-critical/10";
  return (
    <div className="flex items-start justify-between gap-3 pb-3 border-b border-border last:border-0 last:pb-0">
      <div>
        <div className="text-sm font-medium">{label}</div>
        <div className="text-xs text-muted-foreground mt-0.5">{detail}</div>
      </div>
      <span className={`shrink-0 inline-flex items-center rounded border px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider ${cls}`}>{status}</span>
    </div>
  );
}
