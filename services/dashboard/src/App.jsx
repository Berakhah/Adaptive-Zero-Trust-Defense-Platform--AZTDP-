import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Chart,
  ArcElement,
  LineElement,
  CategoryScale,
  LinearScale,
  PointElement,
  Tooltip,
  Legend,
} from 'chart.js';

Chart.register(ArcElement, LineElement, CategoryScale, LinearScale, PointElement, Tooltip, Legend);

const CFG = {
  POLL_MS: 5000,
  FEED_MAX: 50,
  EVENT_FETCH_LIMIT: 200,
  ANM_HISTORY: 24,
  HEALTH_TIMEOUT: 3500,
  TELEMETRY_FRESH_MS: 60000,
  TELEMETRY_ACTIVE_MS: 300000,
};

const SERVICES = [
  { key: 'gateway', label: 'Gateway', url: '/api/gateway/health', port: 8000 },
  { key: 'risk-engine', label: 'Risk Engine', url: '/api/risk/health', port: 8001 },
  { key: 'anomaly', label: 'Anomaly', url: '/api/anomaly/health', port: 8002 },
  { key: 'telemetry', label: 'Telemetry', url: '/api/telemetry/health', port: 8003 },
  { key: 'forensics', label: 'Forensics', url: '/api/forensics/health', port: 8004 },
  { key: 'django-app', label: 'Django App', url: '/api/django/health', port: 8010 },
  { key: 'spring-app', label: 'Spring App', url: '/api/spring/actuator/health', port: 8011 },
  { key: 'keycloak', label: 'Keycloak', url: '/api/keycloak/health/ready', port: 9000 },
  { key: 'opa', label: 'OPA', url: '/api/opa/health', port: 8181 },
  { key: 'prometheus', label: 'Prometheus', url: '/api/prometheus/-/healthy', port: 9090 },
  { key: 'grafana', label: 'Grafana', url: '/api/grafana/api/health', port: 3000, link: 'http://localhost:3000' },
  { key: 'attack-sim', label: 'Attack Sim', url: '/api/sim/health', port: 8090 },
  { key: 'dashboard', label: 'Dashboard', url: '/', port: 8099 },
];

const ROUTES = [
  { id: 'overview', label: 'Overview' },
  { id: 'threats', label: 'Threats' },
  { id: 'sessions', label: 'Sessions' },
  { id: 'forensics', label: 'Forensics' },
  { id: 'operations', label: 'Operations' },
];

const HIGHLIGHTS = [
  {
    title: 'Adaptive risk scoring',
    detail: 'Scores every request for IP drift, geo drift, device change, and ML anomaly signals before policy enforcement.',
  },
  {
    title: 'Policy-as-code enforcement',
    detail: 'OPA-backed decisions deliver allow, deny, step-up MFA, or revoke outcomes with full audit traceability.',
  },
  {
    title: 'Live forensics replay',
    detail: 'Session timelines, incident reconstruction, and token revocation streams keep investigations actionable.',
  },
  {
    title: 'Unified SOC observability',
    detail: 'Prometheus + Grafana telemetry with the SOC console for real-time, executive-ready reporting.',
  },
];

const fetchWithTimeout = async (url, options = {}, timeoutMs = CFG.HEALTH_TIMEOUT) => {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    return await fetch(url, { cache: 'no-store', ...options, signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
};

const fetchJSON = async (url, options = {}) => {
  const res = await fetchWithTimeout(url, options);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

const fmtTs = (iso) => {
  if (!iso) return '--';
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-GB', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return iso.slice(11, 19) || '--';
  }
};

const relTime = (iso) => {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60000) return `${Math.round(diff / 1000)}s ago`;
  if (diff < 3600000) return `${Math.round(diff / 60000)}m ago`;
  return `${Math.round(diff / 3600000)}h ago`;
};

const shortId = (id, n = 8) => {
  if (!id) return '--';
  return id.length > n ? `${id.slice(0, n)}...` : id;
};

const riskColor = (score) => {
  if (score == null) return 'var(--muted)';
  if (score >= 0.8) return 'var(--red)';
  if (score >= 0.5) return 'var(--amber)';
  if (score >= 0.25) return 'var(--accent)';
  return 'var(--green)';
};

const decisionClass = (d) => {
  if (!d) return '';
  const m = { allow: 'allow', deny: 'deny', stepup: 'stepup', revoke: 'revoke', fail_open: 'allow' };
  return m[d.toLowerCase()] || '';
};

const computeThreat = (metrics, health) => {
  const denyPct = metrics?.denyPct || 0;
  const anmPct = metrics?.anmPct || 0;
  const down = Object.values(health || {}).filter((h) => h.status === 'down').length;
  if (anmPct > 25 || denyPct > 40 || down >= 4) return 'CRITICAL';
  if (anmPct > 10 || denyPct > 20 || down >= 2) return 'HIGH';
  if (anmPct > 3 || denyPct > 8 || down >= 1) return 'MEDIUM';
  return 'LOW';
};

const prometheusQuery = async (expr) => {
  const q = new URLSearchParams({ query: expr });
  const data = await fetchJSON(`/api/prometheus/api/v1/query?${q}`);
  if (data?.status !== 'success') return null;
  const res = data?.data?.result;
  if (!res || !res.length) return null;
  const total = res.reduce((acc, r) => {
    const v = parseFloat(r.value?.[1]);
    return Number.isFinite(v) ? acc + v : acc;
  }, 0);
  return Number.isFinite(total) ? total : null;
};

const routeFromHash = () => {
  const raw = window.location.hash.replace(/^#\/?/, '').trim();
  const match = ROUTES.find((r) => r.id === raw);
  return match ? match.id : 'overview';
};

export default function App() {
  const [route, setRoute] = useState('overview');
  const [events, setEvents] = useState([]);
  const [sessions, setSessions] = useState({});
  const [health, setHealth] = useState({});
  const [metrics, setMetrics] = useState({ dpm: null, denyPct: null, anmPct: null });
  const [polling, setPolling] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [connecting, setConnecting] = useState(true);
  const [clock, setClock] = useState(new Date());

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerEvent, setDrawerEvent] = useState(null);

  const [timelineSessionId, setTimelineSessionId] = useState('');
  const [timeline, setTimeline] = useState([]);

  const [inspectorType, setInspectorType] = useState('user_id');
  const [inspectorValue, setInspectorValue] = useState('');
  const [inspectorTab, setInspectorTab] = useState('events');
  const [inspectorEvents, setInspectorEvents] = useState([]);
  const [inspectorIncident, setInspectorIncident] = useState(null);
  const [inspectorSession, setInspectorSession] = useState([]);

  const [simRunning, setSimRunning] = useState(false);
  const [simRunningType, setSimRunningType] = useState('');
  const [simLog, setSimLog] = useState([]);

  const [anomalyHist, setAnomalyHist] = useState(() => new Array(CFG.ANM_HISTORY).fill(0));

  const riskChartRef = useRef(null);
  const anmChartRef = useRef(null);
  const decChartRef = useRef(null);
  const chartsRef = useRef({});

  const feedEvents = useMemo(() => events.slice(0, CFG.FEED_MAX), [events]);

  const decisionCounts = useMemo(() => {
    const counts = { allow: 0, deny: 0, stepup: 0, revoke: 0 };
    feedEvents.forEach((ev) => {
      const dec = ev.payload?.decision || ev.event_type;
      const cls = decisionClass(dec);
      if (counts[cls] !== undefined) counts[cls] += 1;
    });
    return counts;
  }, [feedEvents]);

  const avgRisk = useMemo(() => {
    let sum = 0;
    let count = 0;
    feedEvents.forEach((ev) => {
      const risk = ev.payload?.risk_score;
      if (risk != null) {
        sum += risk;
        count += 1;
      }
    });
    return count ? sum / count : null;
  }, [feedEvents]);

  const latestAnomaly = useMemo(() => {
    const val = feedEvents[0]?.payload?.anomaly_score;
    return val != null ? val : null;
  }, [feedEvents]);

  const threatLevel = useMemo(() => computeThreat(metrics, health), [metrics, health]);

  const sessionsList = useMemo(() => Object.values(sessions), [sessions]);

  const heatmap = useMemo(() => {
    const EVENT_TYPES = ['policy_decision', 'risk_eval', 'token_revocation', 'anomaly_score'];
    const LABELS = ['Policy', 'Risk Eval', 'Revocation', 'Anomaly'];
    const now = new Date();
    const hours = [];
    for (let i = 23; i >= 0; i -= 1) {
      const h = new Date(now - i * 3600000);
      hours.push(h.getHours());
    }
    const matrix = {};
    EVENT_TYPES.forEach((t) => {
      matrix[t] = new Array(24).fill(0);
    });
    events.forEach((ev) => {
      const col = 23 - Math.floor((now - new Date(ev.occurred_at)) / 3600000);
      if (col >= 0 && col < 24 && matrix[ev.event_type]) {
        matrix[ev.event_type][col] += 1;
      }
    });
    const maxVal = Math.max(1, ...Object.values(matrix).flat());
    return { EVENT_TYPES, LABELS, hours, matrix, maxVal };
  }, [events]);

  const alerts = useMemo(() => {
    const fiveMins = Date.now() - 5 * 60000;
    return events.filter((ev) => {
      const dec = ev.payload?.decision;
      return (dec === 'deny' || dec === 'revoke') && new Date(ev.occurred_at) > fiveMins;
    });
  }, [events]);

  const revocations = useMemo(
    () => events.filter((ev) => ev.event_type === 'token_revocation').slice(0, 10),
    [events]
  );

  const latestEventAt = useMemo(() => {
    if (!events.length) return null;
    return events.reduce((latest, ev) => {
      if (!ev?.occurred_at) return latest;
      if (!latest) return ev.occurred_at;
      return new Date(ev.occurred_at) > new Date(latest) ? ev.occurred_at : latest;
    }, null);
  }, [events]);

  const telemetryFreshness = useMemo(() => {
    if (!latestEventAt) {
      return { label: 'No telemetry', detail: 'Awaiting event ingest', tone: 'muted' };
    }
    const diff = Date.now() - new Date(latestEventAt).getTime();
    if (diff < CFG.TELEMETRY_FRESH_MS) {
      return { label: 'Live', detail: `Last event ${relTime(latestEventAt)}`, tone: 'good' };
    }
    if (diff < CFG.TELEMETRY_ACTIVE_MS) {
      return { label: 'Active', detail: `Last event ${relTime(latestEventAt)}`, tone: 'warn' };
    }
    return { label: 'Delayed', detail: `Last event ${relTime(latestEventAt)}`, tone: 'alert' };
  }, [latestEventAt]);

  const healthSummary = useMemo(() => {
    const counts = SERVICES.reduce(
      (acc, svc) => {
        const st = health[svc.key]?.status || 'unknown';
        acc[st] = (acc[st] || 0) + 1;
        return acc;
      },
      { ok: 0, degraded: 0, down: 0, unknown: 0 }
    );
    const total = SERVICES.length;
    return {
      ...counts,
      total,
      coverage: total ? Math.round((counts.ok / total) * 100) : 0,
    };
  }, [health]);

  const pollEvents = useCallback(async () => {
    try {
      const data = await fetchJSON(`/api/forensics/v1/forensics/events?limit=${CFG.EVENT_FETCH_LIMIT}`);
      const fetched = data?.events || [];
      setEvents(fetched);

      const nextSessions = {};
      fetched.forEach((ev) => {
        if (!ev.session_id) return;
        const sess = nextSessions[ev.session_id] || {
          sessionId: ev.session_id,
          userId: ev.user_id,
          count: 0,
          riskMax: null,
          anomalyMax: null,
          lastSeen: ev.occurred_at,
        };
        sess.count += 1;
        const risk = ev.payload?.risk_score;
        const anm = ev.payload?.anomaly_score;
        if (risk != null && (sess.riskMax == null || risk > sess.riskMax)) sess.riskMax = risk;
        if (anm != null && (sess.anomalyMax == null || anm > sess.anomalyMax)) sess.anomalyMax = anm;
        if (!sess.lastSeen || ev.occurred_at > sess.lastSeen) sess.lastSeen = ev.occurred_at;
        nextSessions[ev.session_id] = sess;
      });
      setSessions(nextSessions);
    } catch (_) {
      // ignore fetch errors and keep last good data
    }
  }, []);

  const pollHealth = useCallback(async () => {
    const results = await Promise.allSettled(
      SERVICES.map(async (svc) => {
        const start = performance.now();
        try {
          const r = await fetchWithTimeout(svc.url);
          const latency = Math.round(performance.now() - start);
          return { key: svc.key, status: r.ok ? 'ok' : 'degraded', latency, checkedAt: new Date().toISOString() };
        } catch {
          return { key: svc.key, status: 'down', latency: null, checkedAt: new Date().toISOString() };
        }
      })
    );

    const next = {};
    results.forEach((r) => {
      if (r.status === 'fulfilled') next[r.value.key] = r.value;
    });
    setHealth((prev) => ({ ...prev, ...next }));
  }, []);

  const pollPrometheus = useCallback(async () => {
    const [dpm, denyRate, anmRate] = await Promise.allSettled([
      prometheusQuery('sum(rate(aztdp_policy_decisions_total[1m])) * 60'),
      prometheusQuery(
        'sum(rate(aztdp_policy_decisions_total{decision="deny"}[5m])) / sum(rate(aztdp_policy_decisions_total[5m])) * 100'
      ),
      prometheusQuery(
        'sum(rate(aztdp_anomaly_flagged_total[5m])) / sum(rate(aztdp_policy_decisions_total[5m])) * 100'
      ),
    ]);

    setMetrics({
      dpm: dpm.status === 'fulfilled' ? dpm.value : null,
      denyPct: denyRate.status === 'fulfilled' ? denyRate.value : null,
      anmPct: anmRate.status === 'fulfilled' ? anmRate.value : null,
    });
  }, []);

  const pollAll = useCallback(async () => {
    setPolling(true);
    await Promise.allSettled([pollEvents(), pollHealth(), pollPrometheus()]);
    setPolling(false);
    setLastUpdated(new Date());
    setConnecting(false);
  }, [pollEvents, pollHealth, pollPrometheus]);

  useEffect(() => {
    if (!window.location.hash || window.location.hash === '#') {
      window.location.hash = '#/overview';
    }
    const apply = () => setRoute(routeFromHash());
    apply();
    window.addEventListener('hashchange', apply);
    return () => window.removeEventListener('hashchange', apply);
  }, []);

  useEffect(() => {
    pollAll();
    const id = setInterval(pollAll, CFG.POLL_MS);
    return () => clearInterval(id);
  }, [pollAll]);

  useEffect(() => {
    const id = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (latestAnomaly == null) return;
    setAnomalyHist((prev) => {
      const next = [...prev, latestAnomaly];
      return next.slice(-CFG.ANM_HISTORY);
    });
  }, [latestAnomaly]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') setDrawerOpen(false);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    if (!riskChartRef.current || chartsRef.current.risk) return;
    chartsRef.current.risk = new Chart(riskChartRef.current.getContext('2d'), {
      type: 'doughnut',
      data: {
        datasets: [
          {
            data: [0.01, 0.99],
            backgroundColor: ['#ff3b57', 'rgba(255,59,87,0.08)'],
            borderWidth: 0,
            circumference: 180,
            rotation: 270,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '76%',
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        animation: { animateRotate: true, duration: 700 },
      },
    });
  }, []);

  useEffect(() => {
    if (!anmChartRef.current || chartsRef.current.anomaly) return;
    chartsRef.current.anomaly = new Chart(anmChartRef.current.getContext('2d'), {
      type: 'line',
      data: {
        labels: new Array(CFG.ANM_HISTORY).fill(''),
        datasets: [
          {
            data: new Array(CFG.ANM_HISTORY).fill(0),
            borderColor: '#9bff00',
            backgroundColor: 'rgba(155,255,0,0.12)',
            borderWidth: 1.5,
            pointRadius: 2,
            pointBackgroundColor: '#9bff00',
            fill: true,
            tension: 0.4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { display: false },
          y: {
            min: 0,
            max: 1,
            display: true,
            grid: { color: 'rgba(255,255,255,0.05)' },
            ticks: { color: '#64748b', font: { family: 'IBM Plex Mono', size: 9 }, maxTicksLimit: 3 },
          },
        },
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        animation: { duration: 300 },
      },
    });
  }, []);

  useEffect(() => {
    if (!decChartRef.current || chartsRef.current.decisions) return;
    chartsRef.current.decisions = new Chart(decChartRef.current.getContext('2d'), {
      type: 'doughnut',
      data: {
        labels: ['Allow', 'Deny', 'Step-Up', 'Revoke'],
        datasets: [
          {
            data: [1, 0, 0, 0],
            backgroundColor: ['#00f29b', '#ff3b57', '#f5b800', '#3ed1ff'],
            borderColor: '#0b0f17',
            borderWidth: 2,
            hoverOffset: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '60%',
        plugins: {
          legend: {
            position: 'right',
            labels: { color: '#94a3b8', font: { size: 10, family: 'IBM Plex Mono' }, boxWidth: 10, padding: 6 },
          },
          tooltip: {
            callbacks: {
              label: (ctx) => ` ${ctx.label}: ${ctx.parsed}`,
            },
          },
        },
        animation: { duration: 500 },
      },
    });
  }, []);

  useEffect(() => {
    if (!chartsRef.current.risk) return;
    const s = Math.max(0.001, Math.min(1, avgRisk || 0));
    const colors =
      s >= 0.8
        ? ['#ff3b57', 'rgba(255,59,87,0.08)']
        : s >= 0.5
        ? ['#f5b800', 'rgba(245,184,0,0.08)']
        : s >= 0.25
        ? ['#9bff00', 'rgba(155,255,0,0.08)']
        : ['#00f29b', 'rgba(0,242,155,0.08)'];
    chartsRef.current.risk.data.datasets[0].data = [s, 1 - s];
    chartsRef.current.risk.data.datasets[0].backgroundColor = colors;
    chartsRef.current.risk.update('none');
  }, [avgRisk]);

  useEffect(() => {
    if (!chartsRef.current.anomaly) return;
    chartsRef.current.anomaly.data.datasets[0].data = [...anomalyHist];
    chartsRef.current.anomaly.update('none');
  }, [anomalyHist]);

  useEffect(() => {
    if (!chartsRef.current.decisions) return;
    chartsRef.current.decisions.data.datasets[0].data = [
      decisionCounts.allow || 0,
      decisionCounts.deny || 0,
      decisionCounts.stepup || 0,
      decisionCounts.revoke || 0,
    ];
    chartsRef.current.decisions.update('none');
  }, [decisionCounts]);

  const openEvent = (ev) => {
    setDrawerEvent(ev);
    setDrawerOpen(true);
  };

  const replaySession = async (sessionId) => {
    setTimelineSessionId(sessionId);
    setTimeline([]);
    try {
      const data = await fetchJSON(`/api/forensics/v1/forensics/replay/${sessionId}`);
      setTimeline(data?.timeline || []);
      setRoute('sessions');
      window.location.hash = '#/sessions';
    } catch (_) {
      setTimeline([]);
    }
  };

  const runInspectorSearch = async () => {
    const value = inspectorValue.trim();
    if (!value) return;
    setInspectorTab('events');
    setInspectorEvents([]);
    setInspectorIncident(null);
    setInspectorSession([]);

    try {
      const params = new URLSearchParams({ limit: 100, [inspectorType]: value });
      const data = await fetchJSON(`/api/forensics/v1/forensics/events?${params}`);
      const evs = data?.events || [];
      setInspectorEvents(evs);

      if (inspectorType === 'request_id') {
        const incident = await fetchJSON(`/api/forensics/v1/forensics/incidents/${value}`);
        setInspectorIncident(incident || null);
        setInspectorTab('incident');
      }

      if (inspectorType === 'session_id') {
        const replay = await fetchJSON(`/api/forensics/v1/forensics/replay/${value}`);
        setInspectorSession(replay?.timeline || []);
        setInspectorTab('session');
      }
    } catch (_) {
      setInspectorEvents([]);
    }
  };

  const appendLog = (msg, type = 'log') => {
    setSimLog((prev) => {
      const next = [...prev, { id: `${Date.now()}-${Math.random()}`, type, msg, ts: new Date() }];
      return next.slice(-400);
    });
  };

  const clearLog = () => setSimLog([]);

  const runAttack = async (attackType) => {
    if (simRunning) return;
    clearLog();
    setSimRunning(true);
    setSimRunningType(attackType);
    appendLog(`Launching ${attackType} scenario...`, 'start');

    try {
      const response = await fetch(`/api/sim/v1/sim/${attackType}`, { method: 'POST', cache: 'no-store' });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        appendLog(`Error: ${err.detail || response.status}`, 'error');
        setSimRunning(false);
        setSimRunningType('');
        return;
      }
      await streamResponse(response);
    } catch (e) {
      appendLog(`Connection failed: ${e.message}`, 'error');
    } finally {
      setSimRunning(false);
      setSimRunningType('');
    }
  };

  const runAll = async () => {
    if (simRunning) return;
    clearLog();
    setSimRunning(true);
    setSimRunningType('all');
    appendLog('Launching all attack scenarios...', 'start');

    try {
      const response = await fetch('/api/sim/v1/sim/all/run', { method: 'POST', cache: 'no-store' });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        appendLog(`Error: ${err.detail || response.status}`, 'error');
      } else {
        await streamResponse(response);
      }
    } catch (e) {
      appendLog(`Connection failed: ${e.message}`, 'error');
    } finally {
      setSimRunning(false);
      setSimRunningType('');
    }
  };

  const streamResponse = async (response) => {
    const reader = response.body?.getReader();
    if (!reader) return;
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const evt = JSON.parse(line.slice(6));
          appendLog(evt.msg, evt.type);
        } catch (_) {
          // ignore parse errors
        }
      }
    }
  };

  const healthCount = useMemo(() => `${healthSummary.ok}/${healthSummary.total}`, [healthSummary]);

  return (
    <div className="app-shell">
      <div className={`connecting ${connecting ? '' : 'hidden'}`}>
        <div className="connect-logo">AZTDP</div>
        <div className="spinner" />
        <div className="connect-text">SECURITY OPERATIONS CENTER</div>
        <div className="connect-sub">Initializing live intelligence feeds...</div>
      </div>

      <header className="topbar">
        <div className="brand">
          <div className="brand-icon" />
          <div>
            <div className="brand-title">AZTDP</div>
            <div className="brand-sub">Adaptive Zero Trust SOC</div>
          </div>
        </div>

        <div className="svc-pips">
          {SERVICES.map((svc) => {
            const h = health[svc.key] || {};
            const st = h.status || 'unknown';
            return (
              <div className="svc-pip" key={svc.key} title={`${svc.label}: ${st}${h.latency ? ` (${h.latency}ms)` : ''}`}>
                <span className={`svc-dot ${st}`} />
                <span className="svc-label">{svc.label.split(' ')[0]}</span>
              </div>
            );
          })}
        </div>

        <div className="topbar-right">
          <div className={`poll-indicator ${polling ? 'polling' : ''}`} title="Polling status" />
          <div className={`threat-badge ${threatLevel}`}>{threatLevel}</div>
          <div className="clock">{clock.toLocaleTimeString('en-GB', { hour12: false })}</div>
        </div>
      </header>

      <main>
        <nav className="page-nav" aria-label="Page navigation">
          {ROUTES.map((r) => (
            <a key={r.id} href={`#/${r.id}`} className={route === r.id ? 'active' : ''}>
              {r.label}
            </a>
          ))}
        </nav>

        {route === 'overview' && (
          <>
            <section className="section">
              <div className="section-hdr">
                <div className="section-title">Executive Summary</div>
                <div className="section-sep" />
                <div className="section-meta">
                  {lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString('en-GB', { hour12: false })}` : 'Awaiting data'}
                </div>
              </div>
              <div className="grid grid-4">
                <div className="card stat">
                  <div className="stat-label">Decisions per min</div>
                  <div className="stat-val">{metrics.dpm != null ? Math.round(metrics.dpm) : '--'}</div>
                  <div className="stat-sub">Prometheus 1m rate</div>
                  <div className="stat-bar">
                    <div className="stat-bar-fill" style={{ width: `${metrics.dpm ? Math.min(100, metrics.dpm * 2) : 0}%` }} />
                  </div>
                </div>
                <div className="card stat">
                  <div className="stat-label">Deny rate</div>
                  <div className="stat-val danger">{metrics.denyPct != null ? `${metrics.denyPct.toFixed(1)}%` : '--%'}</div>
                  <div className="stat-sub">Prometheus 5m rate</div>
                  <div className="stat-bar">
                    <div
                      className="stat-bar-fill danger"
                      style={{ width: `${metrics.denyPct ? Math.min(100, metrics.denyPct) : 0}%` }}
                    />
                  </div>
                </div>
                <div className="card stat">
                  <div className="stat-label">Anomaly rate</div>
                  <div className="stat-val warn">{metrics.anmPct != null ? `${metrics.anmPct.toFixed(1)}%` : '--%'}</div>
                  <div className="stat-sub">Prometheus 5m rate</div>
                  <div className="stat-bar">
                    <div
                      className="stat-bar-fill warn"
                      style={{ width: `${metrics.anmPct ? Math.min(100, metrics.anmPct) : 0}%` }}
                    />
                  </div>
                </div>
                <div className="card stat">
                  <div className="stat-label">Active sessions</div>
                  <div className="stat-val accent">{sessionsList.length || '--'}</div>
                  <div className="stat-sub">last {CFG.EVENT_FETCH_LIMIT} events</div>
                  <div className="stat-bar">
                    <div
                      className="stat-bar-fill accent"
                      style={{ width: `${Math.min(100, sessionsList.length * 5)}%` }}
                    />
                  </div>
                </div>
              </div>
              <div className="grid grid-3">
                <div className="card summary-card">
                  <div className="summary-label">Threat posture</div>
                  <div className="summary-value">
                    <span className={`threat-badge ${threatLevel}`}>{threatLevel}</span>
                  </div>
                  <div className="summary-sub">Derived from anomaly rate, deny rate, and service health.</div>
                </div>
                <div className="card summary-card">
                  <div className="summary-label">Service coverage</div>
                  <div className="summary-metric">
                    {healthSummary.ok}/{healthSummary.total}
                  </div>
                  <div className="summary-sub">
                    {healthSummary.degraded} degraded • {healthSummary.down} down • {healthSummary.unknown} pending
                  </div>
                </div>
                <div className="card summary-card">
                  <div className="summary-label">Telemetry freshness</div>
                  <div className={`summary-metric ${telemetryFreshness.tone}`}>{telemetryFreshness.label}</div>
                  <div className="summary-sub">{telemetryFreshness.detail}</div>
                </div>
              </div>
              <div className="card highlights-card">
                <div className="chart-title">Platform highlights</div>
                <div className="highlights-grid">
                  {HIGHLIGHTS.map((item) => (
                    <div key={item.title} className="highlight-item">
                      <div className="highlight-title">{item.title}</div>
                      <div className="highlight-sub">{item.detail}</div>
                    </div>
                  ))}
                </div>
              </div>
            </section>

            <section className="section">
              <div className="section-hdr">
                <div className="section-title">Live Risk Intelligence</div>
                <div className="section-count">{feedEvents.length} events</div>
                <div className="section-sep" />
              </div>
              <div className="grid grid-2-1">
                <div className="card feed-card">
                  <div className="feed-hdr">
                    <span>Timestamp</span>
                    <span>Decision</span>
                    <span>User</span>
                    <span>Path or IP</span>
                    <span>Risk</span>
                  </div>
                  <div className="feed-list">
                    {feedEvents.length === 0 ? (
                      <div className="feed-empty">No events yet. Start a simulation or generate traffic.</div>
                    ) : (
                      feedEvents.map((ev) => {
                        const dec = ev.payload?.decision || ev.event_type;
                        const cls = decisionClass(dec);
                        const risk = ev.payload?.risk_score;
                        const path = ev.payload?.endpoint_path || ev.payload?.path || '';
                        const ip = ev.ip || '';
                        return (
                          <button
                            key={ev.event_id}
                            className={`feed-row ${cls}`}
                            type="button"
                            onClick={() => openEvent(ev)}
                          >
                            <span className="feed-ts">{fmtTs(ev.occurred_at)}</span>
                            <span className={`badge b-${cls}`}>{cls || ev.event_type}</span>
                            <span className="feed-user">{shortId(ev.user_id, 10)}</span>
                            <span className="feed-path">{path || ip}</span>
                            <span className="feed-risk" style={{ color: riskColor(risk) }}>
                              {risk != null ? risk.toFixed(2) : '--'}
                            </span>
                          </button>
                        );
                      })
                    )}
                  </div>
                </div>

                <div className="chart-stack">
                  <div className="card chart-card">
                    <div className="chart-title">Avg Risk Score</div>
                    <div className="chart-wrap">
                      <canvas ref={riskChartRef} />
                      <div className="chart-center">
                        <div className="chart-center-val" style={{ color: riskColor(avgRisk) }}>
                          {avgRisk != null ? avgRisk.toFixed(2) : '--'}
                        </div>
                        <div className="chart-center-sub">risk</div>
                      </div>
                    </div>
                  </div>
                  <div className="card chart-card">
                    <div className="chart-title">Anomaly Score Trend</div>
                    <div className="chart-wrap small">
                      <canvas ref={anmChartRef} />
                    </div>
                  </div>
                  <div className="card chart-card">
                    <div className="chart-title">Decision Distribution</div>
                    <div className="chart-wrap medium">
                      <canvas ref={decChartRef} />
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </>
        )}

        {route === 'threats' && (
          <section className="section">
            <div className="section-hdr">
              <div className="section-title">Threat Detection</div>
              <div className="section-sep" />
            </div>
            <div className="grid grid-2">
              <div className="card">
                <div className="chart-title">Activity Heatmap - last 24 hours</div>
                <div className="heatmap-wrap">
                  <table className="heatmap-table">
                    <thead>
                      <tr>
                        <th />
                        {heatmap.hours.map((h, idx) => (
                          <th key={`h-${idx}`}>{String(h).padStart(2, '0')}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {heatmap.EVENT_TYPES.map((type, rowIdx) => (
                        <tr key={type}>
                          <td className="row-label">{heatmap.LABELS[rowIdx]}</td>
                          {heatmap.matrix[type].map((count, ci) => {
                            const intensity = count / heatmap.maxVal;
                            const alpha = Math.min(0.9, intensity * 0.85 + (count > 0 ? 0.1 : 0));
                            const bg = count > 0 ? `rgba(255,59,87,${alpha.toFixed(2)})` : 'rgba(155,255,0,0.05)';
                            return (
                              <td
                                key={`${type}-${ci}`}
                                className="hm-cell"
                                title={`${heatmap.hours[ci]}:00 - ${type}: ${count}`}
                                style={{ background: bg }}
                              >
                                {count > 0 ? count : ''}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="stack">
                <div className="card">
                  <div className="chart-title">Active Alerts</div>
                  <div className="alert-list">
                    {alerts.length === 0 ? (
                      <div className="empty">No active alerts in last 5 minutes</div>
                    ) : (
                      alerts.slice(0, 5).map((ev) => {
                        const dec = ev.payload?.decision;
                        const risk = ev.payload?.risk_score;
                        return (
                          <div key={ev.event_id} className="alert-row">
                            <span className={`badge b-${decisionClass(dec)}`}>{dec}</span>
                            <span className="alert-msg">
                              {shortId(ev.user_id, 10)} - {ev.ip || ''}
                            </span>
                            <span className="alert-risk" style={{ color: riskColor(risk) }}>
                              {risk != null ? `risk ${risk.toFixed(2)}` : '--'}
                            </span>
                            <span className="alert-time">{relTime(ev.occurred_at)}</span>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
                <div className="card">
                  <div className="chart-title">Token Revocation Log</div>
                  <div className="revoc-list">
                    {revocations.length === 0 ? (
                      <div className="empty">No recent revocations</div>
                    ) : (
                      revocations.map((ev) => (
                        <div key={ev.event_id} className="revoc-row">
                          <span className="revoc-token">{shortId(ev.token_jti_hash, 16)}</span>
                          <span className="revoc-user">{shortId(ev.user_id, 8)}</span>
                          <span className="revoc-time">{relTime(ev.occurred_at)}</span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </div>
          </section>
        )}

        {route === 'sessions' && (
          <section className="section">
            <div className="section-hdr">
              <div className="section-title">Session Explorer</div>
              <div className="section-count">{sessionsList.length} sessions</div>
              <div className="section-sep" />
            </div>

            <div className="card table-card">
              <div className="table-scroll">
                <table className="session-table">
                  <thead>
                    <tr>
                      <th>Session ID</th>
                      <th>User</th>
                      <th>Requests</th>
                      <th>Risk Max</th>
                      <th>Anomaly Max</th>
                      <th>Status</th>
                      <th>Last Seen</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {sessionsList.length === 0 ? (
                      <tr>
                        <td colSpan="8" className="empty">No sessions detected yet</td>
                      </tr>
                    ) : (
                      sessionsList
                        .sort((a, b) => new Date(b.lastSeen) - new Date(a.lastSeen))
                        .slice(0, 30)
                        .map((s) => {
                          const susp = s.riskMax > 0.7 || s.anomalyMax > 0.7;
                          return (
                            <tr key={s.sessionId}>
                              <td className="mono accent">{shortId(s.sessionId, 14)}</td>
                              <td className="mono">{shortId(s.userId, 12)}</td>
                              <td className="mono muted">{s.count}</td>
                              <td className="mono" style={{ color: riskColor(s.riskMax) }}>
                                {s.riskMax != null ? s.riskMax.toFixed(2) : '--'}
                              </td>
                              <td className="mono" style={{ color: riskColor(s.anomalyMax) }}>
                                {s.anomalyMax != null ? s.anomalyMax.toFixed(2) : '--'}
                              </td>
                              <td>
                                <span className={`badge ${susp ? 'b-suspicious' : 'b-clean'}`}>
                                  {susp ? 'SUSPICIOUS' : 'CLEAN'}
                                </span>
                              </td>
                              <td className="muted">{relTime(s.lastSeen)}</td>
                              <td>
                                <button className="btn" type="button" onClick={() => replaySession(s.sessionId)}>
                                  Replay
                                </button>
                              </td>
                            </tr>
                          );
                        })
                    )}
                  </tbody>
                </table>
              </div>

              {timelineSessionId && (
                <div className="timeline-panel">
                  <div className="chart-title">
                    Session Timeline - <span className="mono accent">{shortId(timelineSessionId, 20)}</span>
                  </div>
                  <div className="timeline-list">
                    {timeline.length === 0 ? (
                      <div className="empty">Loading timeline...</div>
                    ) : (
                      timeline.map((ev, idx) => {
                        const delta = ev.delta_ms != null ? `+${Math.round(ev.delta_ms)}ms` : '';
                        const detail = [ev.ip, ev.geo, ev.payload?.decision || ev.payload?.risk_score]
                          .filter(Boolean)
                          .join(' - ');
                        return (
                          <div key={`${ev.event_id || idx}`} className="timeline-row">
                            <span className="timeline-time">{fmtTs(ev.occurred_at)}</span>
                            <span className="timeline-delta">{delta}</span>
                            <span className={`timeline-pill ${ev.event_type}`}>{ev.event_type.replace('_', ' ')}</span>
                            <span className="timeline-detail">{detail}</span>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              )}
            </div>
          </section>
        )}

        {route === 'forensics' && (
          <section className="section">
            <div className="section-hdr">
              <div className="section-title">Policy and Forensics Inspector</div>
              <div className="section-sep" />
            </div>

            <div className="card">
              <div className="inspector-search">
                <select value={inspectorType} onChange={(e) => setInspectorType(e.target.value)}>
                  <option value="user_id">User ID</option>
                  <option value="session_id">Session ID</option>
                  <option value="request_id">Request ID</option>
                  <option value="event_type">Event Type</option>
                </select>
                <input
                  value={inspectorValue}
                  onChange={(e) => setInspectorValue(e.target.value)}
                  onKeyDown={(e) => (e.key === 'Enter' ? runInspectorSearch() : null)}
                  placeholder="Search forensics events..."
                />
                <button className="btn" type="button" onClick={runInspectorSearch}>
                  Search
                </button>
              </div>

              <div className="tabs">
                <button
                  type="button"
                  className={`tab ${inspectorTab === 'events' ? 'active' : ''}`}
                  onClick={() => setInspectorTab('events')}
                >
                  Events
                </button>
                <button
                  type="button"
                  className={`tab ${inspectorTab === 'incident' ? 'active' : ''}`}
                  onClick={() => setInspectorTab('incident')}
                >
                  Incident
                </button>
                <button
                  type="button"
                  className={`tab ${inspectorTab === 'session' ? 'active' : ''}`}
                  onClick={() => setInspectorTab('session')}
                >
                  Session
                </button>
              </div>

              {inspectorTab === 'events' && (
                <div className="tab-panel">
                  {inspectorEvents.length === 0 ? (
                    <div className="empty">Enter a search term above to query events.</div>
                  ) : (
                    <table className="inspector-table">
                      <thead>
                        <tr>
                          <th>Time</th>
                          <th>Type</th>
                          <th>Decision</th>
                          <th>User</th>
                          <th>IP</th>
                          <th>Risk</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {inspectorEvents.map((ev) => {
                          const dec = ev.payload?.decision;
                          const risk = ev.payload?.risk_score;
                          return (
                            <tr key={ev.event_id}>
                              <td className="mono muted">{fmtTs(ev.occurred_at)}</td>
                              <td>{ev.event_type}</td>
                              <td>{dec ? <span className={`badge b-${decisionClass(dec)}`}>{dec}</span> : '--'}</td>
                              <td className="mono">{shortId(ev.user_id, 12)}</td>
                              <td className="mono">{ev.ip || '--'}</td>
                              <td className="mono" style={{ color: riskColor(risk) }}>
                                {risk != null ? risk.toFixed(3) : '--'}
                              </td>
                              <td>
                                <button className="btn" type="button" onClick={() => openEvent(ev)}>
                                  Detail
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </div>
              )}

              {inspectorTab === 'incident' && (
                <div className="tab-panel">
                  {inspectorIncident ? (
                    <div className="incident-grid">
                      <div className="incident-field">
                        <div className="field-label">Decision</div>
                        <div className="field-val">
                          <span className={`badge b-${decisionClass(inspectorIncident?.decision?.decision)}`}>
                            {inspectorIncident?.decision?.decision || '--'}
                          </span>
                        </div>
                      </div>
                      <div className="incident-field">
                        <div className="field-label">Rule</div>
                        <div className="field-val mono">{inspectorIncident?.decision?.rule || '--'}</div>
                      </div>
                      <div className="incident-field">
                        <div className="field-label">Risk Score</div>
                        <div className="field-val mono" style={{ color: riskColor(inspectorIncident?.decision?.risk_score) }}>
                          {inspectorIncident?.decision?.risk_score != null
                            ? inspectorIncident.decision.risk_score.toFixed(4)
                            : '--'}
                        </div>
                      </div>
                      <div className="incident-field">
                        <div className="field-label">Anomaly Score</div>
                        <div className="field-val mono" style={{ color: riskColor(inspectorIncident?.decision?.anomaly_score) }}>
                          {inspectorIncident?.decision?.anomaly_score != null
                            ? inspectorIncident.decision.anomaly_score.toFixed(4)
                            : '--'}
                        </div>
                      </div>
                      <div className="incident-field">
                        <div className="field-label">User</div>
                        <div className="field-val mono">{inspectorIncident?.decision?.user_id || '--'}</div>
                      </div>
                      <div className="incident-field">
                        <div className="field-label">Service Path</div>
                        <div className="field-val mono">
                          {`${inspectorIncident?.decision?.service || ''} ${inspectorIncident?.decision?.endpoint_path || ''}`}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="empty">Search by request ID to reconstruct an incident.</div>
                  )}
                </div>
              )}

              {inspectorTab === 'session' && (
                <div className="tab-panel">
                  {inspectorSession.length === 0 ? (
                    <div className="empty">Search by session ID to replay a session timeline.</div>
                  ) : (
                    <div className="timeline-list">
                      {inspectorSession.map((ev, idx) => {
                        const delta = ev.delta_ms != null ? `+${Math.round(ev.delta_ms)}ms` : '';
                        const detail = [ev.ip, ev.geo, ev.payload?.decision || ev.payload?.risk_score?.toFixed(3)]
                          .filter(Boolean)
                          .join(' - ');
                        return (
                          <div key={`${ev.event_id || idx}`} className="timeline-row">
                            <span className="timeline-time">{fmtTs(ev.occurred_at)}</span>
                            <span className="timeline-delta">{delta}</span>
                            <span className={`timeline-pill ${ev.event_type}`}>{ev.event_type.replace('_', ' ')}</span>
                            <span className="timeline-detail">{detail}</span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          </section>
        )}

        {route === 'operations' && (
          <>
            <section className="section">
              <div className="section-hdr">
                <div className="section-title">Service Health</div>
                <div className="section-count">{healthCount} online</div>
                <div className="section-sep" />
                <a className="inline-link" href="http://localhost:3000" target="_blank" rel="noreferrer">
                  Open Grafana
                </a>
              </div>
              <div className="svc-grid">
                {SERVICES.map((svc) => {
                  const h = health[svc.key] || { status: 'unknown', latency: null };
                  const st = h.status;
                  const checked = h.checkedAt ? relTime(h.checkedAt) : 'pending';
                  return (
                    <div key={svc.key} className={`svc-card ${st}`}>
                      <div className="svc-card-hdr">
                        <span className={`svc-dot ${st}`} />
                        <span className="svc-name">{svc.label}</span>
                        <span className="svc-port">:{svc.port}</span>
                      </div>
                      <div className="svc-latency">
                        {h.latency != null ? <span className="val">{h.latency}ms</span> : <span className="muted">--</span>}
                      </div>
                      <div className="svc-checked">{checked}</div>
                      {svc.link ? (
                        <a className="inline-link" href={svc.link} target="_blank" rel="noreferrer">
                          Open
                        </a>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </section>

            <section className="section">
              <div className="section-hdr">
                <div className="section-title">Attack Simulation Control</div>
                <div className="section-sep" />
                <div className="section-meta">{simRunning ? `RUNNING - ${simRunningType}` : 'IDLE'}</div>
              </div>
              <div className="grid grid-2-3">
                <div className="card">
                  <div className="chart-title">Scenarios</div>
                  <div className="attack-grid">
                    {[
                      { key: 'brute_force', label: 'Brute Force' },
                      { key: 'token_replay', label: 'Token Replay' },
                      { key: 'privilege_escalation', label: 'Privilege Escalation' },
                      { key: 'credential_stuffing', label: 'Credential Stuffing' },
                      { key: 'geo_drift', label: 'Geo Drift' },
                      { key: 'anomaly_flood', label: 'Anomaly Flood' },
                    ].map((a) => (
                      <button
                        key={a.key}
                        type="button"
                        className={`attack-btn ${simRunningType === a.key ? 'running' : ''}`}
                        onClick={() => runAttack(a.key)}
                        disabled={simRunning}
                      >
                        {a.label}
                      </button>
                    ))}
                  </div>
                  <button type="button" className="btn-run" onClick={runAll} disabled={simRunning}>
                    Run All Scenarios
                  </button>
                  <div className="muted hint">Simulates attack patterns. Requires full stack running.</div>
                </div>

                <div className="card">
                  <div className="log-header">
                    <div className="chart-title">Output Log</div>
                    <button type="button" className="btn ghost" onClick={clearLog}>
                      Clear
                    </button>
                  </div>
                  <div className="log">
                    {simLog.length === 0 ? (
                      <div className="empty">Click a scenario button to begin simulation.</div>
                    ) : (
                      simLog.map((line) => (
                        <div key={line.id} className={`log-line ${line.type}`}>
                          {line.ts.toLocaleTimeString('en-GB', { hour12: false })} {line.msg}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </section>
          </>
        )}
      </main>

      {drawerOpen && (
        <div className="drawer open">
          <div className="drawer-hdr">
            <div className="drawer-title">Incident Detail</div>
            <button className="btn ghost" type="button" onClick={() => setDrawerOpen(false)}>
              Close
            </button>
          </div>
          <div className="drawer-body">
            {!drawerEvent ? (
              <div className="empty">Select an event to inspect.</div>
            ) : (
              <>
                <div className="drawer-field">
                  <div className="field-label">Event ID</div>
                  <div className="field-val mono accent">{shortId(drawerEvent.event_id, 28)}</div>
                </div>
                <div className="drawer-field">
                  <div className="field-label">Timestamp</div>
                  <div className="field-val mono">{drawerEvent.occurred_at || '--'}</div>
                </div>
                <div className="drawer-field">
                  <div className="field-label">Event Type</div>
                  <div className="field-val">{drawerEvent.event_type || '--'}</div>
                </div>
                <div className="drawer-field">
                  <div className="field-label">Decision</div>
                  <div className="field-val">
                    <span className={`badge b-${decisionClass(drawerEvent.payload?.decision)}`}>
                      {drawerEvent.payload?.decision || '--'}
                    </span>
                  </div>
                </div>
                <div className="drawer-section">Identity</div>
                <div className="drawer-field">
                  <div className="field-label">User ID</div>
                  <div className="field-val mono">{drawerEvent.user_id || '--'}</div>
                </div>
                <div className="drawer-field">
                  <div className="field-label">Session ID</div>
                  <div className="field-val mono accent">{shortId(drawerEvent.session_id, 24)}</div>
                </div>
                <div className="drawer-field">
                  <div className="field-label">IP Address</div>
                  <div className="field-val mono">{drawerEvent.ip || '--'}</div>
                </div>
                <div className="drawer-field">
                  <div className="field-label">Geo</div>
                  <div className="field-val mono">{drawerEvent.geo || '--'}</div>
                </div>

                <div className="drawer-section">Risk Scores</div>
                {drawerEvent.payload?.risk_score != null && (
                  <div className="drawer-field">
                    <div className="field-label">Risk Score</div>
                    <div className="field-val mono" style={{ color: riskColor(drawerEvent.payload.risk_score) }}>
                      {drawerEvent.payload.risk_score.toFixed(4)}
                    </div>
                    <div className="risk-bar">
                      <div
                        className="risk-fill"
                        style={{
                          width: `${Math.round(drawerEvent.payload.risk_score * 100)}%`,
                          background: riskColor(drawerEvent.payload.risk_score),
                        }}
                      />
                    </div>
                  </div>
                )}
                {drawerEvent.payload?.anomaly_score != null && (
                  <div className="drawer-field">
                    <div className="field-label">Anomaly Score</div>
                    <div className="field-val mono" style={{ color: riskColor(drawerEvent.payload.anomaly_score) }}>
                      {drawerEvent.payload.anomaly_score.toFixed(4)}
                    </div>
                    <div className="risk-bar">
                      <div
                        className="risk-fill"
                        style={{
                          width: `${Math.round(drawerEvent.payload.anomaly_score * 100)}%`,
                          background: riskColor(drawerEvent.payload.anomaly_score),
                        }}
                      />
                    </div>
                  </div>
                )}
                {drawerEvent.payload?.reasons?.length ? (
                  <>
                    <div className="drawer-section">Risk Reasons</div>
                    <div className="risk-reasons">
                      {drawerEvent.payload.reasons.map((r) => (
                        <div key={r.code} className="risk-reason">
                          <span className="badge b-deny">{r.code}</span>
                          <span className="mono muted">weight {Number(r.weight || 0).toFixed(3)}</span>
                        </div>
                      ))}
                    </div>
                  </>
                ) : null}

                <div className="drawer-section">Service</div>
                <div className="drawer-field">
                  <div className="field-label">Service</div>
                  <div className="field-val">{drawerEvent.service || '--'}</div>
                </div>
                <div className="drawer-field">
                  <div className="field-label">Endpoint</div>
                  <div className="field-val mono">{drawerEvent.payload?.endpoint_path || '--'}</div>
                </div>
                <div className="drawer-actions">
                  <button className="btn" type="button" onClick={() => replaySession(drawerEvent.session_id)}>
                    View Session Timeline
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
