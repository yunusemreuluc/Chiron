'use client';

import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { LuX } from 'react-icons/lu';
import { useResearchStore, type ResearchRun } from '@/stores/researchStore';

// Araştırmanın canlı kartı (2026-11-01, ROSE'daki "RESEARCH // ACTIVE" kartının karşılığı). Üst ortada süzülür:
// süren aramanın sayaçları gerçek (Claude'un her WebSearch/WebFetch çağrısı bir olay), sahte yüzde yok —
// bu yüzden çubuk dolmuyor, tarıyor; ancak "pano kuruluyor" aşamasında doluyor (bkz. Bilinen-Tuzaklar §
// Arayüzde dürüstlük).

const SEGMENTS = 22;

function useElapsed(run: ResearchRun | null): number {
  const [now, setNow] = useState(() => Date.now() / 1000);
  const running = run?.status === 'running';
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(id);
  }, [running]);
  if (!run) return 0;
  const end = run.finished_at ?? (running ? now : run.started_at);
  return Math.max(0, Math.round(end - run.started_at));
}

export function clock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function ResearchMeter({ run }: { run: ResearchRun }) {
  const building = run.status === 'running' && run.phase === 'building';
  const done = run.status === 'done';
  return (
    <div className={`research-meter ${run.status === 'running' && !building ? 'is-scanning' : ''}`} aria-hidden>
      {Array.from({ length: SEGMENTS }, (_, i) => (
        <span
          key={i}
          className="research-meter__seg"
          style={{
            animationDelay: `${i * 70}ms`,
            opacity: done || building ? 1 : undefined,
            background: run.status === 'error' ? 'var(--office-err)' : undefined,
          }}
        />
      ))}
    </div>
  );
}

export function ResearchStatusCard({ run, onOpen, onClose }: {
  run: ResearchRun;
  onOpen?: () => void;
  onClose?: () => void;
}) {
  const elapsed = useElapsed(run);
  const label =
    run.status === 'done' ? 'Hazır' : run.status === 'error' ? 'Durdu' : run.phase === 'building' ? 'Pano kuruluyor' : 'Aktif';
  const blocks = run.blocks?.length ?? 0;
  const sources = run.sources?.length ?? 0;

  return (
    <div className={`research-card research-card--${run.status}`}>
      <div className="research-card__head">
        <span className="research-card__tag">
          Araştırma <span className="research-card__sep">{'//'}</span>{' '}
          <span className="research-card__state">{label}</span>
        </span>
        <span className="research-card__time">{clock(elapsed)}</span>
        {onClose && (
          <button type="button" className="research-card__close" onClick={onClose} aria-label="Kartı kapat">
            <LuX size={12} />
          </button>
        )}
      </div>
      <div className="research-card__title">{run.title || run.topic}</div>
      <div className="research-card__step">
        {run.status === 'error'
          ? run.error
          : run.status === 'done'
            ? run.summary
            : run.step
              ? run.step
              : 'Araştırma ajanı başlatılıyor'}
      </div>
      <ResearchMeter run={run} />
      <div className="research-card__foot">
        {run.status === 'done' ? (
          <>
            <span>{blocks} blok</span>
            <span>{sources} kaynak</span>
          </>
        ) : (
          <>
            <span>{run.searches ?? 0} arama</span>
            <span>{run.reads ?? 0} sayfa okundu</span>
          </>
        )}
      </div>
      {run.status === 'done' && onOpen && (
        <button type="button" className="research-card__open" onClick={onOpen}>
          Panoyu aç
        </button>
      )}
    </div>
  );
}

export function ResearchChip() {
  const run = useResearchStore((s) => s.run);
  const open = useResearchStore((s) => s.open);
  const dismissedId = useResearchStore((s) => s.dismissedId);
  const setOpen = useResearchStore((s) => s.setOpen);
  const dismiss = useResearchStore((s) => s.dismiss);
  const visible = Boolean(run) && !open && run?.id !== dismissedId;

  return (
    <AnimatePresence>
      {visible && run && (
        <motion.div
          key="research-chip"
          className="research-chip"
          initial={{ opacity: 0, y: -14, filter: 'blur(8px)' }}
          animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
          exit={{ opacity: 0, y: -10, filter: 'blur(8px)' }}
          transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        >
          <ResearchStatusCard run={run} onOpen={() => setOpen(true)} onClose={dismiss} />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
