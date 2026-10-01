'use client';

import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { useOfficeStore, COLUMN_LABEL, type OfficeTask, type TaskColumn } from '@/stores/officeStore';
import { ago, duration } from './format';

// Görev panosu (plan § A.5). Yalnız KÖK görevler kart olur (Yunus'un Claude'a
// verdiği iş); alt işler (alt ajan, Codex lane'i) kartın içinde satır. Kart
// sürüklenmez — pano bir gözlem yüzeyi, sırayı olaylar belirler.

const COLUMNS: { id: TaskColumn | 'kapandi'; label: string; accepts: TaskColumn[] }[] = [
  { id: 'yurutuluyor', label: COLUMN_LABEL.yurutuluyor, accepts: ['yurutuluyor'] },
  { id: 'onay', label: COLUMN_LABEL.onay, accepts: ['onay'] },
  { id: 'incelemede', label: COLUMN_LABEL.incelemede, accepts: ['incelemede'] },
  { id: 'bitti', label: COLUMN_LABEL.bitti, accepts: ['bitti'] },
  { id: 'kapandi', label: 'Hata / durdu', accepts: ['hata', 'durdu'] },
];

function useNow(): number {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

export function TaskBoard() {
  const snapshot = useOfficeStore((s) => s.snapshot);
  const selectDesk = useOfficeStore((s) => s.selectDesk);
  const selectWorker = useOfficeStore((s) => s.selectWorker);
  const setTab = useOfficeStore((s) => s.setTab);
  const now = useNow();

  const { roots, byId, deskOf, colorOf } = useMemo(() => {
    const tasks = snapshot?.tasks ?? [];
    const byId = new Map(tasks.map((t) => [t.id, t]));
    const workers = new Map((snapshot?.workers ?? []).map((w) => [w.id, w]));
    const colors = new Map((snapshot?.desks ?? []).map((d) => [d.id, d.color]));
    const deskOf = (t: OfficeTask) => workers.get(t.worker_id)?.desk ?? (t.worker_id.startsWith('claude:') ? 'claude' : 'subagents');
    // Kök: ebeveyni olmayan ya da ebeveyni artık listede olmayan görev.
    const roots = tasks.filter((t) => !t.parent || !byId.has(t.parent));
    return { roots, byId, deskOf, colorOf: (t: OfficeTask) => colors.get(deskOf(t)) ?? '#7fb2ff' };
  }, [snapshot]);

  const open = (t: OfficeTask) => {
    // Karttan masaya: ofis görünümüne dön, ilgili masayı ve işçiyi seç.
    setTab('ofis');
    selectDesk(deskOf(t));
    selectWorker(t.worker_id);
  };

  if (!roots.length) {
    return (
      <div className="office-empty">
        <p>Panoda henüz görev yok.</p>
        <p className="text-foreground-disabled">Claude Code&apos;a bir iş verdiğinde burada belirecek.</p>
      </div>
    );
  }

  return (
    <div className="office-board">
      {COLUMNS.map((col) => {
        const items = roots.filter((t) => col.accepts.includes(t.column));
        return (
          <section key={col.id} className="office-board__col">
            <header>
              <span className="label-micro">{col.label}</span>
              <span className="office-board__count">{items.length}</span>
            </header>
            <div className="office-board__list">
              {items.map((t, i) => (
                <motion.button
                  layout
                  type="button"
                  key={t.id}
                  onClick={() => open(t)}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: Math.min(i, 8) * 0.03, ease: [0.22, 1, 0.36, 1] }}
                  className="office-task"
                  style={{ ['--desk' as string]: colorOf(t) }}
                >
                  <span className="office-task__id">{t.id.startsWith('G-') ? t.id : 'İş'}</span>
                  <span className="office-task__title">{t.title}</span>
                  <span className="office-task__meta">
                    {t.column === 'yurutuluyor' || t.column === 'onay' || t.column === 'incelemede'
                      ? `${duration(now - t.created)} sürüyor`
                      : ago(t.updated, now)}
                  </span>
                  <ProofChips task={t} />
                  {t.children.length > 0 && (
                    <ul className="office-task__children">
                      {t.children.slice(-5).map((cid) => {
                        const c = byId.get(cid);
                        if (!c) return null;
                        return (
                          <li key={cid} style={{ ['--desk' as string]: colorOf(c) }}>
                            <span className={`office-col-dot office-col-dot--${c.column}`} />
                            <span className="truncate">{c.title}</span>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </motion.button>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function ProofChips({ task }: { task: OfficeTask }) {
  const p = task.proof;
  const green = p.tests.filter((x) => x.verdict === 'yesil').length;
  const red = p.tests.filter((x) => x.verdict === 'kirmizi').length;
  const chips: { text: string; tone?: 'green' | 'red' }[] = [];
  if (green || red) chips.push({ text: `test ${green}✓${red ? ` ${red}✕` : ''}`, tone: red ? 'red' : 'green' });
  if (p.files_changed.length) chips.push({ text: `${p.files_changed.length} dosya` });
  if (p.delegations) chips.push({ text: `${p.delegations} devir` });
  if (p.reviews) chips.push({ text: `${p.reviews} inceleme` });
  if (!chips.length) return null;
  return (
    <span className="office-task__chips">
      {chips.map((c) => (
        <span key={c.text} className={c.tone ? `is-${c.tone}` : ''}>
          {c.text}
        </span>
      ))}
    </span>
  );
}
