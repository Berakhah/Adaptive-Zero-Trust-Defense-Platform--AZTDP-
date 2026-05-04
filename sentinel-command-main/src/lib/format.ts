export const trunc = (s: string, n = 8) => (s.length > n * 2 + 1 ? `${s.slice(0, n)}…${s.slice(-4)}` : s);

export const relTime = (iso: string) => {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
};

export const fmtNum = (n: number) => new Intl.NumberFormat().format(n);
export const fmtPct = (n: number, d = 1) => `${n.toFixed(d)}%`;
