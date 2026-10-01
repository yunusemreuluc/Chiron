// Ofis ekranının küçük biçimlendiricileri — süre, "ne zaman", token, dosya adı.

export function duration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} sn`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} dk ${s % 60 ? `${s % 60} sn` : ''}`.trim();
  const h = Math.floor(m / 60);
  return `${h} sa ${m % 60 ? `${m % 60} dk` : ''}`.trim();
}

export function ago(ts: number | null | undefined, now: number): string {
  if (!ts) return '—';
  const d = now - ts;
  if (d < 5) return 'şimdi';
  return `${duration(d)} önce`;
}

export function tokens(n: number | undefined): string {
  if (!n) return '0';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(n >= 10_000 ? 0 : 1)} B`;
  return String(n);
}

export function basename(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() ?? path;
}

export function clock(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
