import { NavLink } from "react-router-dom";
import { Activity, AlertTriangle, Search, Server, Users, Shield } from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Overview", icon: Activity },
  { to: "/threats", label: "Threats", icon: AlertTriangle },
  { to: "/sessions", label: "Sessions", icon: Users },
  { to: "/forensics", label: "Forensics", icon: Search },
  { to: "/operations", label: "Operations", icon: Server },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex w-full">
      <aside className="hidden md:flex w-56 shrink-0 flex-col border-r border-border bg-sidebar">
        <div className="px-4 py-5 border-b border-border flex items-center gap-2">
          <div className="h-7 w-7 rounded-md bg-primary/15 border border-primary/40 flex items-center justify-center">
            <Shield className="h-4 w-4 text-primary" />
          </div>
          <div>
            <div className="font-display text-sm font-bold leading-none tracking-tight">AZTDP</div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground mt-0.5">SOC</div>
          </div>
        </div>
        <nav className="flex-1 p-2">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-primary/10 text-primary border-l-2 border-primary"
                    : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-foreground border-l-2 border-transparent",
                )
              }
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="p-3 border-t border-border">
          <div className="card-elev rounded-md p-2 text-[10px] font-mono">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground uppercase tracking-wider">Env</span>
              <span className="text-primary">production</span>
            </div>
            <div className="flex items-center justify-between mt-1">
              <span className="text-muted-foreground uppercase tracking-wider">Build</span>
              <span>v2.41.0</span>
            </div>
          </div>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-14 border-b border-border bg-surface/80 backdrop-blur flex items-center px-4 sticky top-0 z-30">
          <div className="md:hidden font-display font-bold mr-3">AZTDP</div>
          <div className="flex items-center gap-2 text-xs">
            <span className="h-2 w-2 rounded-full bg-primary animate-pulse" />
            <span className="font-mono uppercase tracking-wider text-muted-foreground">All systems streaming</span>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <div className="hidden sm:flex items-center gap-2 px-2.5 py-1.5 rounded-md bg-surface-2 border border-border">
              <Search className="h-3.5 w-3.5 text-muted-foreground" />
              <input
                placeholder="Search request, session, user…"
                className="bg-transparent text-xs w-72 outline-none placeholder:text-muted-foreground font-mono"
              />
              <kbd className="text-[10px] font-mono text-muted-foreground border border-border rounded px-1">⌘K</kbd>
            </div>
            <div className="text-xs font-mono text-muted-foreground hidden lg:block">
              {new Date().toUTCString().slice(17, 25)} <span className="text-foreground/60">UTC</span>
            </div>
          </div>
        </header>
        <main className="flex-1 p-6 max-w-[1600px] w-full mx-auto">{children}</main>
      </div>
    </div>
  );
}
