'use client';

import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion, type Variants } from 'framer-motion';
import { LuPlay, LuX } from 'react-icons/lu';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';
import { fetchLastResearch } from '@/services/researchApi';
import {
  useResearchStore,
  type ChartBlock,
  type ResearchBlock,
  type StatBlock,
  type TextBlock,
  type VideoBlock,
} from '@/stores/researchStore';
import { clock, ResearchStatusCard } from './ResearchChip';

// Araştırma panosu (2026-11-01). "Göster" denince açılır; çekirdek küçülüp sağ kolona çekilir (three/CameraRig.tsx)
// ve kartlar sırayla onun yerine oturur (ROSE'daki panel duvarının karşılığı). Pano yarı saydam — sahne arkada
// çizilmeye devam ediyor, HUD panelleri ise çekiliyor (AppShell).
//
// Kaynak bağlantıları TIKLANMIYOR: WebView2 içinde dış bağlantı Chiron penceresinin kendisinde açılırdı ve geri
// dönüş yolu yok. Alan adı + tam adres (title) gösteriliyor.

const cardVariants: Variants = {
  // Kartlar sağdan, çekirdeğin oturduğu yerden çıkıyor gibi gelir (çekirdek CameraRig'te kenara kayıyor).
  hidden: { opacity: 0, x: 70, y: 10, scale: 0.94, filter: 'blur(8px)' },
  visible: (i: number) => ({
    opacity: 1,
    x: 0,
    y: 0,
    scale: 1,
    filter: 'blur(0px)',
    transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1], delay: 0.55 + i * 0.075 },
  }),
};

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return '';
  }
}

function SourceTag({ index, sources }: { index: number | null; sources: { title: string; url: string }[] }) {
  if (!index) return null;
  const source = sources[index - 1];
  if (!source) return null;
  return (
    <span className="rb-source" title={source.url || source.title}>
      [{index}] {host(source.url) || source.title}
    </span>
  );
}

function TextCard({ block, sources }: { block: TextBlock; sources: { title: string; url: string }[] }) {
  return (
    <>
      {block.title && <h3 className="rb-card__title">{block.title}</h3>}
      <p className="rb-card__body">{block.body}</p>
      <SourceTag index={block.source} sources={sources} />
    </>
  );
}

function StatCard({ block, sources }: { block: StatBlock; sources: { title: string; url: string }[] }) {
  return (
    <>
      <div className="rb-stat__value">{block.value}</div>
      <div className="rb-stat__label">{block.label}</div>
      {block.note && <p className="rb-card__note">{block.note}</p>}
      <SourceTag index={block.source} sources={sources} />
    </>
  );
}

function ChartCard({ block, sources, delay }: { block: ChartBlock; sources: { title: string; url: string }[]; delay: number }) {
  const max = Math.max(...block.items.map((item) => item.value), 0) || 1;
  return (
    <>
      {block.title && <h3 className="rb-card__title">{block.title}</h3>}
      <div className="rb-chart" role="img" aria-label={block.title}>
        {block.items.map((item, i) => (
          <div key={`${item.label}-${i}`} className="rb-chart__col">
            <span className="rb-chart__num">{item.value.toLocaleString('tr-TR', { maximumFractionDigits: 1 })}</span>
            <motion.span
              className="rb-chart__bar"
              style={{ height: `${Math.max(3, (item.value / max) * 100)}%` }}
              initial={{ scaleY: 0 }}
              animate={{ scaleY: 1 }}
              transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: delay + 0.35 + i * 0.06 }}
            />
            <span className="rb-chart__label" title={item.label}>
              {item.label}
            </span>
          </div>
        ))}
      </div>
      <div className="rb-card__meta">
        {block.unit && <span className="rb-chart__unit">birim: {block.unit}</span>}
        <SourceTag index={block.source} sources={sources} />
      </div>
      {block.note && <p className="rb-card__note">{block.note}</p>}
    </>
  );
}

function VideoCard({ block }: { block: VideoBlock }) {
  const [playing, setPlaying] = useState(false);
  return (
    <>
      <div className="rb-video">
        {playing ? (
          <iframe
            src={`https://www.youtube-nocookie.com/embed/${block.video_id}?autoplay=1&rel=0`}
            title={block.title}
            allow="autoplay; encrypted-media; picture-in-picture"
            referrerPolicy="strict-origin-when-cross-origin"
            allowFullScreen
          />
        ) : (
          <button type="button" className="rb-video__poster" onClick={() => setPlaying(true)} aria-label={`Oynat: ${block.title}`}>
            {/* eslint-disable-next-line @next/next/no-img-element -- dış küçük resim, statik dışa aktarımda next/image optimize edemez */}
            <img src={`https://i.ytimg.com/vi/${block.video_id}/hqdefault.jpg`} alt="" loading="lazy" />
            <span className="rb-video__play">
              <LuPlay size={18} />
            </span>
            {block.duration ? <span className="rb-video__time">{clock(block.duration)}</span> : null}
          </button>
        )}
      </div>
      <div className="rb-video__title">{block.title}</div>
      <div className="rb-video__channel">{block.channel}</div>
    </>
  );
}

function blockClass(block: ResearchBlock): string {
  if (block.type === 'chart') return 'rb-card rb-card--wide';
  return `rb-card rb-card--${block.type}`;
}

export function ResearchBoard() {
  const open = useResearchStore((s) => s.open);
  const run = useResearchStore((s) => s.run);
  const setOpen = useResearchStore((s) => s.setOpen);
  const reduced = usePrefersReducedMotion();

  // Açılışta son pano diskten (Chiron yeniden başlamış olabilir). Eski pano için ilerleme kartı açılmasın.
  useEffect(() => {
    let cancelled = false;
    void fetchLastResearch().then((board) => {
      if (cancelled || !board) return;
      const state = useResearchStore.getState();
      if (state.run) return; // canlı olay daha önce geldi — o daha yeni
      state.update(board);
      state.dismiss();
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, setOpen]);

  const blocks = useMemo(() => {
    const known = (run?.blocks ?? []).filter((b) => ['text', 'stat', 'chart', 'video'].includes(b.type));
    // Rakam kartları başa: göz önce en çarpıcı sayıyı görsün; geri kalanı araştırmanın sırasıyla.
    return [...known.filter((b) => b.type === 'stat'), ...known.filter((b) => b.type !== 'stat')];
  }, [run]);
  const sources = run?.sources ?? [];
  const done = run?.status === 'done';
  const elapsed = run?.finished_at ? Math.round(run.finished_at - run.started_at) : 0;

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="research-board"
          className="research-board"
          initial={{ opacity: 0, filter: 'blur(12px)' }}
          animate={{ opacity: 1, filter: 'blur(0px)' }}
          exit={{ opacity: 0, filter: 'blur(12px)' }}
          transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
        >
          <div className="research-board__grid-bg" aria-hidden />
          <header className="rb-head">
            <div className="rb-head__main">
              <span className="label-micro">Chiron · Araştırma{done ? ' · Tamamlandı' : ''}</span>
              <h2 className="rb-head__title">{run?.title || run?.topic || 'Araştırma panosu'}</h2>
              {done && run?.summary && <p className="rb-head__summary">{run.summary}</p>}
            </div>
            <div className="rb-head__meta">
              {done && (
                <>
                  <span>
                    <b>{blocks.length}</b> blok
                  </span>
                  <span>
                    <b>{sources.length}</b> kaynak
                  </span>
                  <span>
                    <b>{run?.searches ?? 0}</b> arama
                  </span>
                  <span>
                    <b>{clock(elapsed)}</b> süre
                  </span>
                </>
              )}
              <button type="button" className="rb-close" onClick={() => setOpen(false)} aria-label="Panoyu kapat">
                <LuX size={16} />
              </button>
            </div>
          </header>

          {!run && <div className="rb-empty">Henüz bir araştırma yok. Chiron&apos;a &quot;şunu araştır&quot; de.</div>}
          {run && !done && (
            <div className="rb-empty">
              <ResearchStatusCard run={run} />
            </div>
          )}

          {done && (
            <div className="rb-scroll">
              <div className="rb-wall">
                {blocks.map((block, i) => (
                  <motion.article
                    key={`${block.type}-${i}`}
                    className={blockClass(block)}
                    custom={reduced ? 0 : i}
                    variants={reduced ? undefined : cardVariants}
                    initial={reduced ? false : 'hidden'}
                    animate="visible"
                  >
                    <span className="rb-card__index">{String(i + 1).padStart(2, '0')}</span>
                    {block.type === 'text' && <TextCard block={block} sources={sources} />}
                    {block.type === 'stat' && <StatCard block={block} sources={sources} />}
                    {block.type === 'chart' && (
                      <ChartCard block={block} sources={sources} delay={reduced ? 0 : 0.55 + i * 0.075} />
                    )}
                    {block.type === 'video' && <VideoCard block={block} />}
                  </motion.article>
                ))}
              </div>
              {sources.length > 0 && (
                <footer className="rb-sources">
                  <span className="label-micro">Kaynaklar</span>
                  <ol>
                    {sources.map((s, i) => (
                      <li key={`${s.url}-${i}`} title={s.url}>
                        <span className="rb-sources__n">{i + 1}</span>
                        <span className="rb-sources__t">{s.title}</span>
                        <span className="rb-sources__h">{host(s.url)}</span>
                      </li>
                    ))}
                  </ol>
                </footer>
              )}
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
