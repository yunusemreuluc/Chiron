'use client';

import dynamic from 'next/dynamic';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  LuTriangleAlert,
  LuCopy,
  LuCheck,
  LuX,
  LuSquareTerminal,
  LuOrbit,
  LuRows3,
} from 'react-icons/lu';
import {
  decide,
  endRunaway,
  fetchGozetim,
  fetchLastReply,
  hueMap,
  type Decision,
  type GozetimSession,
  type GozetimView,
  type MarkCat,
  type Runaway,
} from '@/services/gozetimApi';
import { fetchWorkerDetail } from '@/services/officeApi';
import { takeOver } from '@/services/sohbetApi';
import { useNavigationStore } from '@/stores/navigationStore';
import { STATUS_LABEL, useOfficeStore, type WorkerDetail } from '@/stores/officeStore';
import { ago, basename, clock, duration, tokens } from '../format';

// Gözetim (2026-11-04) — Atalay's Terminal'in HUD fikri, Chiron'un diliyle.
// Taslak: claude.ai artifact VEkhnxY622pqRZgHnXPNuM. Veri: backend/core/gozetim.py (3 sn'de bir).
//
// Yerleşim: üst şerit (sayılar) · sol oturum kartları · orta yörünge / şerit · sağ araştırma,
// sıcak dosyalar, araç karışımı · alt canlı akış, alt ajanlar, harcama, senin sıran.
// Dürüstlük: maliyet "API liste fiyatıyla eşdeğer" — abonelikte ödenen bu değil; bilinmeyen "?".

const POLL_MS = 3000;
const LANE_WINDOW_S = 30 * 60;

const GozetimOrbit = dynamic(() => import('./GozetimOrbit').then((m) => m.GozetimOrbit), {
  ssr: false,
});

export const CAT_LABEL: Record<MarkCat, string> = {
  okuma: 'okuma',
  duzenle: 'düzenleme',
  shell: 'shell',
  web: 'web',
  ajan: 'ajan',
  mcp: 'mcp',
  diger: 'diğer',
  onay: 'seni bekledi',
  hata: 'hata',
};
const CAT_ORDER: MarkCat[] = ['okuma', 'duzenle', 'shell', 'web', 'ajan', 'mcp', 'diger'];

const usd = (v: number | null | undefined, digits = 2) =>
  v == null
    ? '?'
    : `$${v.toLocaleString('tr-TR', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;

function useNow(): number {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

export function Gozetim() {
  const [view, setView] = useState<GozetimView | null>(null);
  const [offline, setOffline] = useState(false);
  const [mode, setMode] = useState<'yorunge' | 'serit'>(() => {
    try {
      return (localStorage.getItem('gozetim.mode') as 'yorunge' | 'serit') || 'yorunge';
    } catch {
      return 'yorunge';
    }
  });
  const focus = useOfficeStore((s) => s.focusSession);
  const setFocus = useOfficeStore((s) => s.setFocusSession);
  const now = useNow();

  const load = useCallback(
    () =>
      void fetchGozetim().then((v) => {
        if (v) {
          setView(v);
          setOffline(false);
        } else setOffline(true);
      }),
    [],
  );
  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  const pickMode = (m: 'yorunge' | 'serit') => {
    setMode(m);
    try {
      localStorage.setItem('gozetim.mode', m);
    } catch {
      /* tarayıcı deposu yoksa yalnız bu oturum için */
    }
  };

  const hues = useMemo(() => hueMap((view?.sessions ?? []).map((s) => s.id)), [view]);
  const focused = view?.sessions.find((s) => s.id === focus) ?? null;

  if (!view) {
    return (
      <div className="gz-empty glass-panel">
        {offline ? 'Chiron backend kapalı.' : 'Gözetim yükleniyor…'}
      </div>
    );
  }
  const t = view.totals;

  return (
    <div className="gz">
      {/* ① üst şerit */}
      <div className="gz-strip glass-panel">
        <Stat k="canlı oturum" v={String(t.sessions_live)} />
        <Stat k="alt ajan" v={String(t.subagents_running)} n={`bugün ${t.subagents_today}`} />
        <Stat k="araç / dk" v={String(t.tools_per_min)} n="son 5 dk" />
        <Stat k="token / dk" v={tokens(t.tokens_per_min)} n="önbellek dahil" />
        <Stat
          k="bugün · api eşdeğeri"
          v={t.cost_known ? usd(t.cost_today) : `${usd(t.cost_today)}+`}
          n={`son 1 sa ${usd(t.cost_per_hour)}`}
          accent
        />
        <Stat
          k="önbellek isabeti"
          v={t.cache_hit == null ? '—' : `%${Math.round(t.cache_hit * 100)}`}
          n={`${usd(t.cache_saved)} kazanç`}
        />
        <div className="gz-strip__spacer" />
        <div className="gz-toggle" role="tablist" aria-label="Görünüm">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'yorunge'}
            className={mode === 'yorunge' ? 'is-on' : ''}
            onClick={() => pickMode('yorunge')}
          >
            <LuOrbit size={14} /> Yörünge
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'serit'}
            className={mode === 'serit' ? 'is-on' : ''}
            onClick={() => pickMode('serit')}
          >
            <LuRows3 size={14} /> Şerit
          </button>
        </div>
      </div>

      <AnimatePresence>
        {view.runaways.length > 0 && <RunawayBar items={view.runaways} now={now} onDone={load} />}
      </AnimatePresence>

      <div className="gz-main">
        {/* ② oturum kartları */}
        <div className="gz-col gz-sessions">
          <div className="gz-head">
            <span className="label-micro">Oturumlar</span>
            <span className="gz-sub">{t.sessions_live} canlı</span>
          </div>
          <div className="gz-scroll">
            {view.sessions.length === 0 && (
              <div className="gz-none">Şu an açık Claude oturumu yok.</div>
            )}
            {view.sessions.map((s) => (
              <SessionCard
                key={s.id}
                s={s}
                hue={hues[s.id]}
                now={now}
                onOpen={() => setFocus(s.id)}
              />
            ))}
          </div>
        </div>

        {/* ③ yörünge / şerit */}
        <div className="gz-center glass-panel">
          <div className="gz-head gz-head--float">
            <span className="label-micro">
              {mode === 'yorunge' ? 'Yörünge' : 'Şerit · son 30 dk'}
            </span>
            <span className="gz-sub">
              {view.sessions.length} oturum · {t.subagents_running} alt ajan
            </span>
          </div>
          {mode === 'yorunge' ? (
            <div className="gz-orbit">
              <GozetimOrbit />
              <div className="gz-legend">
                <span>
                  <i className="gz-dot" /> çalışıyor
                </span>
                <span>
                  <i className="gz-dot is-wait" /> onay bekliyor (nabız)
                </span>
                <span>
                  <i className="gz-dot is-idle" /> boşta (kısık)
                </span>
                <span>
                  <i className="gz-dot is-moon" /> alt ajan
                </span>
              </div>
            </div>
          ) : (
            <Lanes sessions={view.sessions} hues={hues} now={view.now} onOpen={setFocus} />
          )}
        </div>

        {/* ④⑤⑥ sağ sütun */}
        <div className="gz-col gz-right">
          <div className="gz-panel glass-panel">
            <div className="gz-head">
              <span className="label-micro">Araştırma</span>
              <span className="gz-sub">
                {view.research.length ? `son ${view.research.length}` : ''}
              </span>
            </div>
            <div className="gz-list">
              {view.research.length === 0 && <div className="gz-none">Bugün web araması yok.</div>}
              {view.research.slice(0, 7).map((r, i) => (
                <div key={`${r.ts}-${i}`} className="gz-research">
                  <span className={`gz-pill ${r.kind === 'ara' ? '' : 'is-alt'}`}>
                    {r.kind === 'ara' ? 'ARA' : 'OKU'}
                  </span>
                  <div className="gz-research__body">
                    <div className="gz-ellipsis">{r.target}</div>
                    <div className="gz-sub">
                      {r.project || '—'} · {ago(r.ts, now)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="gz-panel glass-panel">
            <div className="gz-head">
              <span className="label-micro">Sıcak dosyalar</span>
              <span className="gz-sub">bugün</span>
            </div>
            <FileHeat files={view.files} />
          </div>
          <div className="gz-panel glass-panel">
            <div className="gz-head">
              <span className="label-micro">Araç karışımı</span>
              <span className="gz-sub">
                {Object.values(view.tool_mix).reduce((a, b) => a + (b ?? 0), 0)} çağrı
              </span>
            </div>
            <ToolMix mix={view.tool_mix} />
          </div>
        </div>
      </div>

      {/* ⑦⑧⑨⑩ alt şerit */}
      <div className="gz-bottom">
        <div className="gz-panel glass-panel gz-log">
          <div className="gz-head">
            <span className="label-micro">Canlı akış</span>
            <span className="gz-sub">
              {view.last_event_ts ? `son olay ${ago(view.last_event_ts, now)}` : 'olay yok'}
            </span>
          </div>
          <div className="gz-list">
            {view.log.slice(0, 9).map((l, i) => (
              <div key={`${l.ts}-${i}`} className={`gz-log__row is-${l.kind}`}>
                <span className="gz-sub">{clock(l.ts)}</span>
                <span className="gz-ellipsis gz-log__who">
                  {l.who}
                  {l.worker ? ` › ${l.worker}` : ''}
                </span>
                <span className="gz-ellipsis">{l.text}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="gz-panel glass-panel">
          <div className="gz-head">
            <span className="label-micro">Alt ajanlar</span>
            <span className="gz-sub">{t.subagents_running} çalışıyor</span>
          </div>
          <div className="gz-list">
            {view.sessions.flatMap((s) => s.subagents.map((a) => ({ a, s }))).length === 0 && (
              <div className="gz-none">Son 15 dakikada alt ajan yok.</div>
            )}
            {view.sessions
              .flatMap((s) => s.subagents.map((a) => ({ a, s })))
              .sort((x, y) => y.a.started - x.a.started)
              .slice(0, 5)
              .map(({ a, s }) => (
                <div key={a.id} className="gz-agent">
                  <div className="gz-row">
                    <span className="gz-agent__name">
                      {a.name}
                      {a.status === 'bitti' ? ' ✓' : a.status === 'hata' ? ' ✕' : ''}
                    </span>
                    <span className="gz-sub">{a.tool_count} araç</span>
                  </div>
                  <div className="gz-sub gz-ellipsis">
                    <i className="gz-swatch" style={{ background: hues[s.id] }} /> {s.project} ·{' '}
                    {a.title}
                  </div>
                </div>
              ))}
          </div>
        </div>
        <div className="gz-panel glass-panel">
          <div className="gz-head">
            <span className="label-micro">Harcama</span>
            <span className="gz-sub">API liste fiyatı</span>
          </div>
          <div className="gz-spend">
            {t.cost_known ? usd(t.cost_today) : `${usd(t.cost_today)}+`}
          </div>
          <div className="gz-sub">bugün · son 1 saatte {usd(t.cost_per_hour)}</div>
          <div className="gz-models">
            {Object.entries(t.by_model).map(([m, c]) => (
              <div key={m} className="gz-row">
                <span>{m}</span>
                <span>{usd(c)}</span>
              </div>
            ))}
            <div className="gz-row">
              <span>önbellekle kazanılan</span>
              <span className="gz-accent">{usd(t.cache_saved)}</span>
            </div>
          </div>
        </div>
        <div
          className={`gz-panel glass-panel gz-queue ${view.approvals.length || view.decisions.length ? 'is-on' : ''}`}
        >
          <div className="gz-head">
            <span className="label-micro">Senin sıran</span>
            <span className="gz-sub">
              {view.decisions.length || view.approvals.length
                ? `${Math.max(view.decisions.length, view.approvals.length)} bekliyor`
                : 'kimse beklemiyor'}
            </span>
          </div>
          <div className="gz-list">
            {view.decisions.map((d) => (
              <button
                key={d.id}
                type="button"
                className="gz-approval gz-approval--btn"
                onClick={() => (d.worker_id ? setFocus(d.worker_id) : undefined)}
              >
                <div className="gz-row">
                  <strong>{d.project}</strong>
                  <span className="gz-pill is-warn">CEVAPLA</span>
                </div>
                <div className="gz-sub gz-ellipsis">{d.summary}</div>
              </button>
            ))}
            {view.approvals
              .filter(
                (a) =>
                  !view.decisions.some(
                    (d) => d.worker_id === a.worker_id || d.project === a.project,
                  ),
              )
              .map((a) => (
                <div key={a.id} className="gz-approval">
                  <div className="gz-row">
                    <strong>{a.project || '—'}</strong>
                    <span className="gz-sub">{ago(a.ts, now)}</span>
                  </div>
                  <div className="gz-sub gz-ellipsis">
                    {a.tool}: {a.what}
                  </div>
                </div>
              ))}
            {view.approvals.length > 0 && view.decisions.length === 0 && (
              <div className="gz-hint">
                Bu istek Chiron açılmadan önce gelmiş; terminalde cevapla.
              </div>
            )}
          </div>
        </div>
      </div>

      <AnimatePresence>
        {focused && (
          <SessionDetail
            key={focused.id}
            s={focused}
            hue={hues[focused.id]}
            now={now}
            onClose={() => setFocus(null)}
            decisions={view.decisions.filter((d) => d.worker_id === focused.id)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function Stat({ k, v, n, accent = false }: { k: string; v: string; n?: string; accent?: boolean }) {
  return (
    <div className="gz-stat">
      <span className="label-micro">{k}</span>
      <strong className={accent ? 'gz-accent' : ''}>{v}</strong>
      {n && <span className="gz-sub">{n}</span>}
    </div>
  );
}

function statusClass(s: GozetimSession['status']): string {
  return s === 'onay_bekliyor' ? 'is-wait' : s === 'bosta' ? 'is-idle' : 'is-run';
}

function loopSuspect(s: GozetimSession): boolean {
  const recent = s.marks.slice(-24);
  return recent.filter(([, c]) => c === 'hata').length >= 5;
}

function SessionCard({
  s,
  hue,
  now,
  onOpen,
}: {
  s: GozetimSession;
  hue: string;
  now: number;
  onOpen: () => void;
}) {
  const ctxPct = s.ctx ? Math.min(100, (s.ctx.used / s.ctx.window) * 100) : 0;
  const loop = loopSuspect(s);
  // Son 30 dakikanın aktivite çubukları: 30 kova, her biri o dakikadaki araç sayısı.
  const buckets = useMemo(() => {
    const b = new Array(30).fill(0);
    for (const [ts, c] of s.marks) {
      if (c === 'onay' || c === 'hata') continue;
      const i = 29 - Math.floor((now - ts) / 60);
      if (i >= 0 && i < 30) b[i] += 1;
    }
    const max = Math.max(1, ...b);
    return b.map((v) => v / max);
  }, [s.marks, now]);

  return (
    <button
      type="button"
      className={`gz-card glass-panel ${statusClass(s.status)} ${loop ? 'is-loop' : ''}`}
      onClick={onOpen}
      style={{ ['--hue' as string]: hue }}
    >
      <div className="gz-row">
        <span className="gz-card__name">
          <i className="gz-swatch" /> {s.project}
        </span>
        <span className={`gz-tag ${statusClass(s.status)} ${loop ? 'is-loop' : ''}`}>
          {loop ? 'DÖNGÜ?' : STATUS_LABEL[s.status].toLocaleUpperCase('tr-TR')}
        </span>
      </div>
      <div className="gz-card__task gz-ellipsis">{s.current || s.title}</div>
      <div className="gz-row gz-ctx">
        <span className="gz-sub">bağlam</span>
        <span className="gz-bar">
          <span style={{ width: `${ctxPct}%` }} className={ctxPct > 80 ? 'is-hot' : ''} />
        </span>
        <span className="gz-sub">
          {s.ctx ? `${tokens(s.ctx.used)} / ${tokens(s.ctx.window)}` : '?'}
        </span>
      </div>
      <div className="gz-spark" aria-hidden="true">
        {buckets.map((v, i) => (
          <span key={i} style={{ height: `${Math.max(6, v * 100)}%`, opacity: v ? 0.85 : 0.18 }} />
        ))}
      </div>
      <div className="gz-row gz-sub">
        <span>
          {s.model_short} · {s.tool_count} araç
          {s.subagents.length ? ` · ${s.subagents.length} alt ajan` : ''}
        </span>
        <strong className="gz-card__cost">
          {s.cost == null ? (s.cost_partial ? `${usd(s.cost_partial)}+` : '?') : usd(s.cost)}
        </strong>
      </div>
      {s.approvals.length > 0 && (
        <div className="gz-card__why">
          ⚠ {s.approvals[0].tool}: {s.approvals[0].what}
        </div>
      )}
    </button>
  );
}

function Lanes({
  sessions,
  hues,
  now,
  onOpen,
}: {
  sessions: GozetimSession[];
  hues: Record<string, string>;
  now: number;
  onOpen: (id: string) => void;
}) {
  const start = now - LANE_WINDOW_S;
  const x = (ts: number) => `${Math.max(0, Math.min(100, ((ts - start) / LANE_WINDOW_S) * 100))}%`;
  return (
    <div className="gz-lanes">
      <div className="gz-lanes__axis gz-sub">
        <span>{clock(start).slice(0, 5)}</span>
        <span>{clock(start + LANE_WINDOW_S / 2).slice(0, 5)}</span>
        <span>şimdi</span>
      </div>
      {sessions.map((s) => (
        <div key={s.id} className="gz-lane-group">
          {/* Satır div, yalnız ad düğme: <button> içindeki grid sütunu genişlemiyor, iz 0 px kalıyordu. */}
          <div className="gz-lane">
            <button
              type="button"
              className="gz-lane__name"
              style={{ color: hues[s.id] }}
              onClick={() => onOpen(s.id)}
            >
              {s.project}
              <span className="gz-sub">
                {' '}
                {s.model_short} · {s.cost == null ? '?' : usd(s.cost)}
              </span>
            </button>
            <span className="gz-lane__track">
              {s.marks.map(([ts, c], i) => (
                <i key={i} className={`gz-mark is-${c}`} style={{ left: x(ts) }} />
              ))}
            </span>
          </div>
          {s.subagents.map((a) => (
            <div key={a.id} className="gz-lane is-sub">
              <span className="gz-lane__name gz-sub">↳ {a.name}</span>
              <span className="gz-lane__track">
                {a.marks.map(([ts, c], i) => (
                  <i key={i} className={`gz-mark is-${c}`} style={{ left: x(ts) }} />
                ))}
              </span>
            </div>
          ))}
        </div>
      ))}
      <div className="gz-legend gz-legend--static">
        {(['okuma', 'duzenle', 'shell', 'web', 'ajan', 'onay', 'hata'] as MarkCat[]).map((c) => (
          <span key={c}>
            <i className={`gz-mark is-${c} is-key`} /> {CAT_LABEL[c]}
          </span>
        ))}
      </div>
    </div>
  );
}

function FileHeat({ files }: { files: GozetimView['files'] }) {
  if (!files.length) return <div className="gz-none">Bugün dosyaya dokunulmadı.</div>;
  const max = Math.max(1, ...files.map((f) => f.writes * 2 + f.reads));
  return (
    <div className="gz-list">
      {files.slice(0, 6).map((f) => (
        <div
          key={f.path}
          className="gz-heat"
          title={`${f.path}\nyazan: ${f.writers.join(', ') || '—'}`}
        >
          <span className="gz-ellipsis gz-mono">{basename(f.path)}</span>
          <span className="gz-bar">
            <span style={{ width: `${((f.writes * 2 + f.reads) / max) * 100}%` }} />
          </span>
          {f.collision ? (
            <span className="gz-pill is-warn">ÇAKIŞMA</span>
          ) : (
            <span className="gz-pill">{f.writes ? `Y${f.writes}` : `O${f.reads}`}</span>
          )}
        </div>
      ))}
    </div>
  );
}

function ToolMix({ mix }: { mix: GozetimView['tool_mix'] }) {
  const total = CAT_ORDER.reduce((a, c) => a + (mix[c] ?? 0), 0);
  if (!total) return <div className="gz-none">Bugün araç çağrısı yok.</div>;
  return (
    <>
      <div className="gz-mix">
        {CAT_ORDER.map((c) =>
          mix[c] ? (
            <span
              key={c}
              className={`is-${c}`}
              style={{ width: `${((mix[c] ?? 0) / total) * 100}%` }}
            />
          ) : null,
        )}
      </div>
      <div className="gz-mix__keys">
        {CAT_ORDER.filter((c) => mix[c]).map((c) => (
          <span key={c}>
            <i className={`gz-mark is-${c} is-key`} /> {CAT_LABEL[c]} {mix[c]}
          </span>
        ))}
      </div>
    </>
  );
}

function RunawayBar({ items, now, onDone }: { items: Runaway[]; now: number; onDone: () => void }) {
  const [busy, setBusy] = useState<number | null>(null);
  const [msg, setMsg] = useState('');
  const end = async (r: Runaway) => {
    setBusy(r.pid);
    const res = await endRunaway(r.pid, r.create_time);
    setBusy(null);
    setMsg(res.success ? '' : res.message);
    onDone();
  };
  return (
    <motion.div
      className="gz-runaway glass-panel"
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      role="alert"
    >
      <LuTriangleAlert size={18} className="gz-runaway__icon" />
      <div className="gz-runaway__list">
        {items.slice(0, 3).map((r) => (
          <div key={r.pid} className="gz-runaway__item">
            <strong className="gz-mono">
              {r.name} · pid {r.pid}
            </strong>
            <span className="gz-sub">
              {r.kind === 'yakiyor'
                ? `sahibi yok, %${Math.round(r.cpu)} CPU · ${r.since ? duration(now - r.since) : ''}`
                : `sahibi yok, port tutuyor`}
              {r.ports.length ? ` · :${r.ports.join(', :')}` : ''}
              {r.cwd ? ` · ${basename(r.cwd)}` : ''}
            </span>
            <button
              type="button"
              className="gz-btn is-danger"
              disabled={busy === r.pid}
              onClick={() => void end(r)}
            >
              {busy === r.pid ? 'Kapatılıyor…' : 'Sonlandır (ağacıyla)'}
            </button>
          </div>
        ))}
        {msg && <span className="gz-sub">{msg}</span>}
      </div>
    </motion.div>
  );
}

// Onay terminali (2026-11-04, Yunus: "tıkladığımda önüme terminal gelsin, yazayım onaylayayım").
// Claude Code'un kendi izin sorusunun Chiron'daki karşılığı: aynı üç seçenek + "terminalde cevaplayacağım".
// Karar backend/core/onay.py'ye gider, oradaki hook (~/.claude/hooks/chiron-onay.py) Claude Code'a iletir.
// Süre dolarsa soru terminale düşer — sayaç bu yüzden görünür.
export function ApprovalTerminal({ d, now }: { d: Decision; now: number }) {
  const [pick, setPick] = useState(0);
  const [text, setText] = useState('');
  const [sent, setSent] = useState<'' | 'ok' | string>('');
  const input = useRef<HTMLInputElement>(null);
  const left = Math.max(0, Math.round(d.deadline - now));
  const options = [
    { id: 'evet', label: 'Evet' },
    ...(d.can_always ? [{ id: 'hep', label: 'Evet, bu oturumda bir daha sorma' }] : []),
    { id: 'hayir', label: 'Hayır, şunu yap:' },
    { id: 'terminal', label: 'Terminalde cevaplayacağım' },
  ];

  const send = async (id: string) => {
    if (sent === 'ok') return;
    const behavior = id === 'evet' || id === 'hep' ? 'izin' : id === 'hayir' ? 'red' : 'terminal';
    const res = await decide(d.id, behavior, id === 'hayir' ? text : '', id === 'hep');
    setSent(res.success ? 'ok' : res.message || 'İletilemedi.');
  };

  const onKey = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.target instanceof HTMLInputElement && e.key !== 'Enter') return;
    const n = Number(e.key);
    if (n >= 1 && n <= options.length) {
      e.preventDefault();
      setPick(n - 1);
      if (options[n - 1].id === 'hayir') input.current?.focus();
      else void send(options[n - 1].id);
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      setPick((p) => (p + (e.key === 'ArrowDown' ? 1 : options.length - 1)) % options.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      void send(options[pick].id);
    }
  };

  return (
    <div
      className="gz-term"
      tabIndex={0}
      onKeyDown={onKey}
      role="group"
      aria-label={`${d.project} izin istiyor`}
    >
      <div className="gz-term__head">
        <span>
          <strong>{d.project}</strong> izin istiyor
        </span>
        <span className={left < 20 ? 'gz-term__left is-low' : 'gz-term__left'}>
          {sent === 'ok'
            ? 'iletildi'
            : `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')} sonra terminale düşer`}
        </span>
      </div>
      <div className="gz-term__cmd">{d.summary}</div>
      {d.detail && <pre className="gz-term__detail">{d.detail}</pre>}
      <div className="gz-term__opts" role="listbox" aria-label="Seçenekler">
        {options.map((o, i) => (
          <div key={o.id} className={`gz-term__opt ${pick === i ? 'is-on' : ''}`}>
            <button
              type="button"
              role="option"
              aria-selected={pick === i}
              disabled={sent === 'ok'}
              onClick={() => {
                setPick(i);
                if (o.id === 'hayir' && !text) input.current?.focus();
                else void send(o.id);
              }}
            >
              <span className="gz-term__caret">{pick === i ? '❯' : ' '}</span> {i + 1}. {o.label}
            </button>
            {o.id === 'hayir' && (
              <>
                <label htmlFor={`gz-term-${d.id}`} className="gz-sr">
                  Claude’a ne yapmasını söyle
                </label>
                <input
                  id={`gz-term-${d.id}`}
                  ref={input}
                  value={text}
                  disabled={sent === 'ok'}
                  onFocus={() => setPick(i)}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="örn. önce testleri çalıştır"
                />
              </>
            )}
          </div>
        ))}
      </div>
      {sent && sent !== 'ok' && <div className="gz-hint">{sent}</div>}
      <div className="gz-term__foot gz-sub">
        1–{options.length} seç · Enter gönder · sesle de olur: “izin ver” / “reddet, şunu yap”
      </div>
    </div>
  );
}

function SessionDetail({
  s,
  hue,
  now,
  onClose,
  decisions,
}: {
  s: GozetimSession;
  hue: string;
  now: number;
  onClose: () => void;
  decisions: Decision[];
}) {
  const [detail, setDetail] = useState<WorkerDetail | null>(null);
  const [copied, setCopied] = useState<'' | 'ok' | 'bos'>('');
  const [confirmTake, setConfirmTake] = useState(false);
  const [note, setNote] = useState('');

  useEffect(() => {
    let cancelled = false;
    const load = () => void fetchWorkerDetail(s.id).then((d) => !cancelled && d && setDetail(d));
    load();
    const id = setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [s.id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        // Aynı penceredeki Ofis kapatma dinleyicisi de çalışmasın: önce detay kapanır.
        e.stopImmediatePropagation();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [onClose]);

  const copy = async () => {
    const r = await fetchLastReply(s.id);
    if (!r?.text) {
      setCopied('bos');
      return;
    }
    try {
      await navigator.clipboard.writeText(r.text);
      setCopied('ok');
    } catch {
      setCopied('bos');
    }
    setTimeout(() => setCopied(''), 2200);
  };

  // Komuta'da sürdür: terminaldeki oturumu Chiron'un sohbeti olarak devral (sohbet.takeover).
  // Oturum hâlâ terminalde açıkken iki taraf aynı kayda yazar — ikinci tıklamayla onay.
  const take = async () => {
    if (!s.session_id) return;
    const open = s.status !== 'bosta';
    if (open && !confirmTake) {
      setConfirmTake(true);
      return;
    }
    const res = await takeOver(s.session_id, open);
    setConfirmTake(false);
    if (!res.success || !res.data) {
      setNote(res.message || 'Devralınamadı.');
      return;
    }
    const office = useOfficeStore.getState();
    office.setPendingChat(res.data.chat.id);
    office.setFocusSession(null);
    office.setTab('komuta');
    if (useNavigationStore.getState().activeModule !== 'agents')
      useNavigationStore.getState().toggleModule('agents');
  };

  const ctxPct = s.ctx ? Math.min(100, (s.ctx.used / s.ctx.window) * 100) : 0;
  const activity = (detail?.activity ?? []).slice(-40).reverse();

  return (
    <motion.div
      className="gz-detail-veil"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.div
        className="gz-detail glass-panel"
        style={{ ['--hue' as string]: hue }}
        initial={{ opacity: 0, y: 18, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 18, scale: 0.98 }}
        transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={`${s.project} oturumu`}
      >
        <header className="gz-detail__head">
          <i className="gz-swatch is-big" />
          <div className="gz-detail__title">
            <div className="gz-row" style={{ justifyContent: 'flex-start', gap: 10 }}>
              <strong>{s.project}</strong>
              <span className={`gz-tag ${statusClass(s.status)}`}>
                {STATUS_LABEL[s.status].toLocaleUpperCase('tr-TR')} · {duration(now - s.started)}
              </span>
            </div>
            <div className="gz-sub gz-ellipsis">
              {s.cwd || '—'} · {s.model_short}
              {s.effort ? ` · ${s.effort}` : ''}
            </div>
          </div>
          <div className="gz-detail__ctx">
            <div className="gz-row gz-sub">
              <span>bağlam</span>
              <span>{s.ctx ? `${tokens(s.ctx.used)} / ${tokens(s.ctx.window)}` : '?'}</span>
            </div>
            <span className="gz-bar is-wide">
              <span style={{ width: `${ctxPct}%` }} className={ctxPct > 80 ? 'is-hot' : ''} />
            </span>
          </div>
          <div className="gz-detail__cost">
            <strong>{s.cost == null ? '?' : usd(s.cost)}</strong>
            <span className="gz-sub">
              {s.tool_count} araç · {s.files_written_count} dosya
            </span>
          </div>
          <button type="button" className="gz-icon" aria-label="Kapat" onClick={onClose}>
            <LuX size={16} />
          </button>
        </header>

        <div className="gz-detail__body">
          <div className="gz-detail__feed">
            {decisions.map((d) => (
              <ApprovalTerminal key={d.id} d={d} now={now} />
            ))}
            <span className="label-micro">Akış</span>
            <div className="gz-scroll">
              {activity.length === 0 && <div className="gz-none">Henüz bir şey yok.</div>}
              {activity.map((a, i) => (
                <div key={`${a.ts}-${i}`} className={`gz-feed is-${a.kind}`}>
                  <i />
                  <div>
                    <div className="gz-mono">{a.text}</div>
                    <div className="gz-sub">{clock(a.ts)}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <aside className="gz-detail__side">
            <div>
              <span className="label-micro">Alt ajanları</span>
              {s.subagents.length === 0 && <div className="gz-none">Yok.</div>}
              {s.subagents.map((a) => (
                <div key={a.id} className="gz-row">
                  <span>{a.name}</span>
                  <span className="gz-sub">
                    {a.tool_count} araç · {STATUS_LABEL[a.status].toLocaleLowerCase('tr-TR')}
                  </span>
                </div>
              ))}
            </div>
            <div>
              <span className="label-micro">Yazdığı dosyalar</span>
              {s.files_written.length === 0 && <div className="gz-none">Yok.</div>}
              {s.files_written
                .slice()
                .reverse()
                .slice(0, 8)
                .map((f) => (
                  <div key={f} className="gz-mono gz-ellipsis" title={f}>
                    ✎ {basename(f)}
                  </div>
                ))}
            </div>
            {s.approvals.length > 0 && (
              <div className="gz-detail__wait">
                <span className="label-micro">Seni bekliyor</span>
                {s.approvals.map((a) => (
                  <div key={a.id} className="gz-sub">
                    {a.tool}: {a.what}
                  </div>
                ))}
              </div>
            )}
            <div className="gz-detail__actions">
              <button type="button" className="gz-btn" onClick={() => void copy()}>
                {copied === 'ok' ? <LuCheck size={14} /> : <LuCopy size={14} />}
                {copied === 'ok'
                  ? 'Kopyalandı'
                  : copied === 'bos'
                    ? 'Cevap bulunamadı'
                    : 'Son cevabı kopyala (tamamı)'}
              </button>
              <button
                type="button"
                className={`gz-btn ${confirmTake ? 'is-warn' : ''}`}
                onClick={() => void take()}
                disabled={!s.session_id}
              >
                <LuSquareTerminal size={14} />
                {confirmTake ? 'Terminalde açık — yine de devral' : "Komuta'da sürdür"}
              </button>
              {confirmTake && (
                <div className="gz-hint">
                  Terminalde kapatmadan devralırsan ikisi aynı kayda yazar.
                </div>
              )}
              {note && <div className="gz-hint">{note}</div>}
            </div>
          </aside>
        </div>
      </motion.div>
    </motion.div>
  );
}
