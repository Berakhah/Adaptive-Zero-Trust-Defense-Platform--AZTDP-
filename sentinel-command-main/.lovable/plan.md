
# AZTDP SOC — Build Plan

A premium, dark, command-center UI for the Adaptive Zero-Trust Defense Platform. Five routes, one cohesive design system, one shared component library, and an API client layer designed to swap from mock data to the real Nginx-proxied endpoints.

## 1. Design system

Theme: deep carbon base, signal-lime + oxidized-teal accents, disciplined red/amber for alerts. No purple. Dark-only, high contrast.

Tokens (added to `src/index.css` + `tailwind.config.ts`, all HSL):

- `--background` carbon 222 20% 6%
- `--surface` 222 18% 9%, `--surface-2` 222 16% 12%
- `--foreground` 210 30% 96%, `--muted-foreground` 215 15% 65%
- `--border` 220 14% 18%, `--grid` 220 14% 14%
- `--primary` signal-lime 78 90% 55% (CTA, focus, "go")
- `--accent-teal` oxidized teal 178 55% 42%
- `--severity-critical` 0 85% 60%, `--severity-high` 14 90% 58%, `--severity-medium` 38 95% 55%, `--severity-low` 178 55% 42%, `--severity-info` 210 25% 60%
- `--decision-allow` lime, `--decision-stepup` amber, `--decision-deny` red
- Gradients: `--gradient-ambient` (slow-drift carbon→teal), `--gradient-alert-pulse`
- Shadows: `--shadow-rail` for the right drawer, `--shadow-card` subtle

Typography (self-hosted via `@fontsource`, no defaults):
- Display/headings: **Space Grotesk** (700/600)
- Body/UI: **Inter** (400/500/600)
- Mono identifiers (jti, request_id, ip): **JetBrains Mono** (400/500)

Motion (disciplined):
- Ambient background: 30s gradient drift on app shell
- Card reveal: staggered fade-up 60ms apart, only on first mount
- `alert-pulse` keyframe applied only to severity=critical badges/rows
- Reduced-motion media query disables drift + pulse

Accessibility:
- Status uses badge shape + label + icon, never color alone
- Min contrast AA on all text; focus ring uses `--primary`

## 2. Shared component library (`src/components/soc/`)

- `AppShell` — left nav rail (collapsible icon mode), top command bar with global search + env indicator, ambient gradient background
- `KpiCard` — label, big value, delta, sparkline slot, severity tint
- `SeverityBadge` / `DecisionBadge` — shape + icon + label
- `LiveFeed` — virtualized streaming list with pause/resume, severity stripe
- `EventRow` — dense table row, mono identifiers, hover→drawer
- `Heatmap24h` — 24×N grid by event type, intensity scale
- `RiskGauge` / `AnomalyBars` — compact SVG charts (no heavy lib; use Recharts already available)
- `Sparkline` — inline SVG
- `IncidentDrawer` — right rail (Sheet), shows identity, decision, rule, risk reasons, geo/IP, timeline CTA
- `TimelinePanel` — vertical timeline with `delta_ms` gaps, payload accordion
- `ServiceHealthTile` — name, status pill, latency, last-check
- `SimConsole` — terminal-style streaming log, run controls
- `MonoId` — copyable monospace identifier with truncation + tooltip
- `SectionHeader` — bold display heading + actions slot

All built on existing shadcn primitives (Card, Sheet, Table, Badge, Tabs, Tooltip, Command).

## 3. Routes & layouts

Router updated in `src/App.tsx` to wrap routes in `AppShell`.

### `/` Overview
Grid: 4 KPI cards (Deny rate 1h, Step-up rate, Anomaly p95, Active sessions) → row of 3 visualizations (Decisions stacked area, Risk distribution, Top rules triggered) → two-column: Live event feed (left, 60%) + Posture summary card (right).

### `/threats` Threats
- Top: 24h heatmap by `event_type`
- Middle: Active alerts list (sortable by severity, decision filter chips)
- Bottom: Recent token revocations table (mono `token_jti_hash`)

### `/sessions` Sessions
- Left 65%: Sessions table (session_id, user_id, request_count, risk_max bar, anomaly_max bar, last_seen_at, action: Replay)
- Right 35%: Replay timeline panel (loads on selection), scrubber + per-event detail

### `/forensics` Forensics
- Search bar with type detection (uuid → session/request, email/string → user, known event_type → events)
- Tabs: Events | Incident | Session — tab auto-selects from query type, manual override allowed
- Incident tab: summary header (decision, rule, policy, scores) + reasons list + linked session CTA

### `/operations` Operations
- Service health grid (auth, policy, risk, forensics, sim, prometheus, gateway)
- Attack simulation panel: attack type select + "Run all" button + streaming `SimConsole`

## 4. Data layer

`src/lib/api.ts` — typed fetchers for all endpoints listed in the brief, with `VITE_API_BASE` (defaults to `/api`).

`src/lib/types.ts` — `AuditEvent`, `Incident`, `TimelineEvent`, `SessionSummary`.

`src/lib/mock.ts` — deterministic mock generators so the UI is fully usable without the backend; React Query hooks (`useEvents`, `useIncident`, `useReplay`, `useSessions`, `usePromQuery`, `useServiceHealth`) read from mock by default and switch to live when `VITE_USE_MOCK=false`.

SSE for `/api/sim/v1/sim/all/run` handled via `EventSource` in `SimConsole` with mock fallback that streams synthetic lines.

## 5. File map (new)

```text
src/
  components/soc/
    AppShell.tsx, NavRail.tsx, CommandBar.tsx
    KpiCard.tsx, SeverityBadge.tsx, DecisionBadge.tsx
    LiveFeed.tsx, EventRow.tsx, MonoId.tsx
    Heatmap24h.tsx, Sparkline.tsx, RiskGauge.tsx
    IncidentDrawer.tsx, TimelinePanel.tsx
    ServiceHealthTile.tsx, SimConsole.tsx
    SectionHeader.tsx
  pages/
    Overview.tsx, Threats.tsx, Sessions.tsx, Forensics.tsx, Operations.tsx
  lib/
    api.ts, types.ts, mock.ts, format.ts
  hooks/
    useEvents.ts, useIncident.ts, useReplay.ts, useSessions.ts,
    usePromQuery.ts, useServiceHealth.ts, useSimStream.ts
```

`src/App.tsx`, `src/index.css`, `tailwind.config.ts` updated. `src/pages/Index.tsx` becomes the Overview page (or redirects to it).

## 6. Out of scope (this pass)

- Auth/login flow (assumed handled upstream by the gateway)
- Writing back to policy or risk services
- Persisting UI prefs to a backend (uses localStorage only)

## 7. Acceptance checks

- All five routes render with realistic mock data, no console errors
- Drawer opens from any event row across Overview/Threats/Sessions/Forensics
- Sim console streams lines and can be stopped
- Lighthouse: contrast passes; reduced-motion disables drift/pulse
- Swapping `VITE_USE_MOCK=false` calls the documented endpoints with no code changes
