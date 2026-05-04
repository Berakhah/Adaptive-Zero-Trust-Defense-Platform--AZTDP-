import { useEffect, useState } from "react";
import { AppShell } from "@/components/soc/AppShell";
import { SectionHeader } from "@/components/soc/SectionHeader";
import { ServiceHealthTile } from "@/components/soc/ServiceHealthTile";
import { SimConsole } from "@/components/soc/SimConsole";
import { api } from "@/lib/api";
import type { ServiceHealth } from "@/lib/types";

export default function Operations() {
  const [services, setServices] = useState<ServiceHealth[]>([]);
  useEffect(() => {
    const load = () => api.health().then(setServices);
    load();
    const id = setInterval(load, 8000);
    return () => clearInterval(id);
  }, []);

  return (
    <AppShell>
      <SectionHeader title="Service health" subtitle="Live probes against /api/*/health" actions={<span className="text-xs font-mono text-muted-foreground">refresh · 8s</span>} />
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {services.map((s) => <ServiceHealthTile key={s.name} svc={s} />)}
      </div>

      <div className="mt-8">
        <SectionHeader title="Adversary exercises" subtitle="Launch attack scenarios and stream impact" />
        <SimConsole />
      </div>
    </AppShell>
  );
}
