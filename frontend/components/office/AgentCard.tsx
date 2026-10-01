'use client';

import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { LuFileCode2, LuGitBranch, LuShieldCheck, LuTriangleAlert, LuX } from 'react-icons/lu';
import { fetchWorkerDetail } from '@/services/officeApi';
import {
  STATUS_LABEL,
  isActive,
  useOfficeStore,
  type Desk,
  type WorkerDetail,
  type WorkerSummary,
} from '@/stores/officeStore';
import { ago, basename, clock, duration, tokens } from './format';

// Masaya tıklayınca sağdan gelen kart (plan § A.4): kim, rolü ne, şu an hangi
// işte, kim verdi, canlı akış, dosyalar, token, kanıt. Ayrıntı HTTP'den gelir
// ve masa seçiliyken her anlık görüntü değişiminde (en fazla saniyede bir)
// tazelenir — WebSocket'e ağır ayrıntı yüklemiyoruz.

function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now() / 1000), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

const KIND_ICON: Record<string, string> = {
  gorev: '◆',
  arac: '›',
  test: '✓',
  hata: '✕',
  onay: '!',
  bitti: '●',
  oturum: '○',
  bildirim: '·',
};

function giverLabel(givenBy: string, workers: WorkerSummary[]): string {
  if (givenBy === 'Yunus') return 'Yunus';
  const w = workers.find((x) => x.id === givenBy);
  return w ? (w.kind === 'chief' ? 'Claude (şef)' : w.title || w.name) : 'Claude';
}

export function AgentCard({ desk }: { desk: Desk }) {
  const snapshot = useOfficeStore((s) => s.snapshot);
  const selectedWorker = useOfficeStore((s) => s.selectedWorker);
  const selectWorker = useOfficeStore((s) => s.selectWorker);
  const selectDesk = useOfficeStore((s) => s.selectDesk);
  const now = useNow();

  const all = useMemo(() => snapshot?.workers ?? [], [snapshot]);
  const onDesk = useMemo(() => all.filter((w) => w.desk === desk.id), [all, desk.id]);
  const active = onDesk.filter((w) => isActive(w.status));
  const history = onDesk.filter((w) => !isActive(w.status));
  const focusId = selectedWorker ?? active[0]?.id ?? history[0]?.id ?? null;

  const [detail, setDetail] = useState<WorkerDetail | null>(null);
  const version = snapshot?.version ?? 0;
  useEffect(() => {
    if (!focusId) return; // `d` aşağıda focusId'ye göre süzülüyor; eski ayrıntı görünmez
    let cancelled = false;
    const id = setTimeout(() => {
      void fetchWorkerDetail(focusId).then((d) => {
        if (!cancelled) setDetail(d);
      });
    }, 120);
    return () => {
      cancelled = true;
      clearTimeout(id);
    };
  }, [focusId, version]);

  const stats = desk.stats;
  const finished = stats.done + stats.failed;
  const success = finished ? Math.round((stats.done / finished) * 100) : null;
  const avg = finished ? stats.busy_seconds / finished : null;
  const d = detail && detail.id === focusId ? detail : null;

  return (
    <motion.aside
      key={desk.id}
      initial={{ opacity: 0, x: 28, filter: 'blur(8px)' }}
      animate={{ opacity: 1, x: 0, filter: 'blur(0px)' }}
      exit={{ opacity: 0, x: 28, filter: 'blur(8px)' }}
      transition={{ duration: 0.36, ease: [0.22, 1, 0.36, 1] }}
      className="surface-card office-card"
      style={{ ['--desk' as string]: desk.color }}
    >
      {/* Kimlik */}
      <header className="flex items-start gap-3">
        <span className="office-avatar" aria-hidden />
        <div className="min-w-0 flex-1">
          <span className="label-micro">{desk.model}</span>
          <h2 className="text-foreground mt-1.5 text-[15px] leading-tight font-medium">{desk.name}</h2>
          <p className="text-foreground-secondary mt-1 text-[11.5px] leading-snug">{desk.role}</p>
        </div>
        <button
          type="button"
          onClick={() => selectDesk(null)}
          className="text-foreground-disabled hover:text-foreground -m-1 rounded-full p-1.5 transition-colors duration-200 hover:bg-white/[0.06]"
          aria-label="Kartı kapat"
        >
          <LuX size={13} strokeWidth={1.8} />
        </button>
      </header>

      <div className="office-stats">
        <div>
          <span className="label-micro">İş</span>
          <strong>{stats.jobs}</strong>
        </div>
        <div>
          <span className="label-micro">Başarı</span>
          <strong>{success === null ? '—' : `%${success}`}</strong>
        </div>
        <div>
          <span className="label-micro">Ort. süre</span>
          <strong>{avg === null ? '—' : duration(avg)}</strong>
        </div>
        <div>
          <span className="label-micro">Token</span>
          <strong>{desk.id === 'claude' || desk.id === 'subagents' ? '—' : tokens(stats.tokens)}</strong>
        </div>
      </div>

      {/* Masada birden çok işçi varsa (paralel lane'ler, birden çok oturum) seçici */}
      {onDesk.length > 1 && (
        <div className="office-chips">
          {[...active, ...history.slice(0, 6)].map((w) => (
            <button
              type="button"
              key={w.id}
              onClick={() => selectWorker(w.id)}
              className={`office-chip ${w.id === focusId ? 'office-chip--on' : ''}`}
            >
              <span className={`office-dot office-dot--${w.status}`} />
              <span className="truncate">{w.title || w.name}</span>
            </button>
          ))}
        </div>
      )}

      <hr className="hairline my-4" />

      {!focusId && (
        <p className="text-foreground-secondary text-xs leading-relaxed">
          Bu masada henüz iş görülmedi. Kayıtlar Claude Code hook&apos;undan geliyor — bu masaya iş
          verildiğinde burada görünecek.
        </p>
      )}

      {focusId && !d && <p className="text-foreground-disabled text-xs">Yükleniyor…</p>}

      {d && (
        <div className="office-card__body">
          <section>
            <div className="flex items-center justify-between gap-2">
              <span className="label-micro">{isActive(d.status) ? 'Şu anki iş' : 'Son iş'}</span>
              <span className={`office-status office-status--${d.status}`}>{STATUS_LABEL[d.status]}</span>
            </div>
            <h3 className="text-foreground mt-2 text-[13px] leading-snug font-medium">{d.title || '—'}</h3>
            <dl className="office-meta">
              <dt>Veren</dt>
              <dd>{giverLabel(d.given_by, all)}</dd>
              {d.project && (
                <>
                  <dt>Proje</dt>
                  <dd>{d.project}</dd>
                </>
              )}
              <dt>Süre</dt>
              <dd>
                {duration((d.ended ?? now) - d.started)}
                {!d.ended && <span className="text-foreground-disabled"> · son adım {ago(d.last_ts, now)}</span>}
              </dd>
              {d.sandbox && (
                <>
                  <dt>Yetki</dt>
                  <dd>
                    <LuShieldCheck size={11} className="mr-1 inline" />
                    {d.sandbox === 'read-only' ? 'yalnız okuma' : d.sandbox}
                  </dd>
                </>
              )}
              {d.tokens?.total ? (
                <>
                  <dt>Token</dt>
                  <dd>
                    {tokens(d.tokens.total)}
                    {d.tokens.cached ? <span className="text-foreground-disabled"> · önbellek {tokens(d.tokens.cached)}</span> : null}
                  </dd>
                </>
              ) : null}
              <dt>Araç</dt>
              <dd>{d.tool_count} çağrı</dd>
            </dl>
            {d.tracking === 'sinirli' && (
              <p className="office-warn">
                <LuTriangleAlert size={12} />
                Arka planda başlatıldı; bitişini bildiren bir sinyal yok. Durum tahmin edilmiyor.
              </p>
            )}
            {d.brief && (
              <details className="office-brief">
                <summary>Görev metni (brief)</summary>
                <pre>{d.brief}</pre>
              </details>
            )}
          </section>

          {d.result && !isActive(d.status) && (
            <section>
              <span className="label-micro">Sonuç</span>
              <p className="office-result">{d.result}</p>
            </section>
          )}

          {d.task && <ProofCard task={d.task} />}

          <section>
            <span className="label-micro">Canlı akış</span>
            <ol className="office-feed">
              {[...d.activity].reverse().map((a, i) => (
                <li key={`${a.ts}-${i}`} className={`office-feed__item office-feed__item--${a.kind}`}>
                  <span className="office-feed__time">{clock(a.ts)}</span>
                  <span className="office-feed__icon">{KIND_ICON[a.kind] ?? '›'}</span>
                  <span className="office-feed__text">{a.text}</span>
                </li>
              ))}
            </ol>
          </section>

          {(d.files_written_list.length > 0 || d.files_read_list.length > 0) && (
            <section>
              <span className="label-micro">
                Dosyalar · {d.files_written_list.length} değişti · {d.files_read_list.length} okundu
              </span>
              <ul className="office-files">
                {d.files_written_list.slice(-12).map((f) => (
                  <li key={f} title={f}>
                    <LuFileCode2 size={11} /> {basename(f)}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {d.delegated.length > 0 && (
            <section>
              <span className="label-micro">Devrettiği işler</span>
              <ul className="office-delegated">
                {d.delegated
                  .slice()
                  .reverse()
                  .map((w) => (
                    <li key={w.id}>
                      <LuGitBranch size={11} />
                      <span className={`office-dot office-dot--${w.status}`} />
                      <span className="truncate">{w.title || w.name}</span>
                      <span className="text-foreground-disabled shrink-0">{w.name}</span>
                    </li>
                  ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </motion.aside>
  );
}

function ProofCard({ task }: { task: NonNullable<WorkerDetail['task']> }) {
  const p = task.proof;
  const green = p.tests.filter((t) => t.verdict === 'yesil').length;
  const red = p.tests.filter((t) => t.verdict === 'kirmizi').length;
  if (!p.tests.length && !p.files_changed.length && !p.delegations) return null;
  const unknown = p.tests.length - green - red;
  return (
    <section className="office-proof">
      <span className="label-micro">Kanıt</span>
      <div className="office-proof__grid">
        {p.tests.length > 0 && (
          <span className={red ? 'is-red' : green ? 'is-green' : ''}>
            {green || red ? `Test ${green}✓${red ? ` ${red}✕` : ''}` : `${p.tests.length} test`}
            {unknown > 0 && (green || red) ? ` · ${unknown} ?` : ''}
            {!green && !red ? ' · sonuç okunamadı' : ''}
          </span>
        )}
        <span>{p.files_changed.length} dosya</span>
        <span>{p.delegations} devir</span>
        <span>{p.reviews} inceleme</span>
      </div>
      {p.tests.slice(-3).map((t) => (
        <p key={t.ts} className={`office-proof__test is-${t.verdict}`}>
          {t.verdict === 'yesil' ? '✓' : t.verdict === 'kirmizi' ? '✕' : '?'} {t.command}
        </p>
      ))}
    </section>
  );
}
