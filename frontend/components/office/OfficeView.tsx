'use client';

import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { LuX } from 'react-icons/lu';
import { fetchOfficeState } from '@/services/officeApi';
import { fetchPano, type ClaudeQuota } from '@/services/panoApi';
import { useNavigationStore } from '@/stores/navigationStore';
import { isActive, useOfficeStore } from '@/stores/officeStore';
import { AgentCard } from './AgentCard';
import { CardBoard } from './CardBoard';
import { Komuta } from './Komuta';
import { TaskBoard } from './TaskBoard';
import { ago } from './format';

// Komuta (2026-10-27) eski "Ofis" sekmesinin yerine: istasyon artık Komuta'nın sağ üstünde
// küçük bir pencere — tam ekran sahne kalktı ("istasyon gözümün önünde olsun").
const TABS = [
  { id: 'komuta', label: 'Komuta' },
  { id: 'isler', label: 'İşler' },
  { id: 'gecmis', label: 'Geçmiş' },
] as const;

// Ajan Ofisi ekranı (2026-10-02). Kenar çubuğundaki "Ajanlar" modülü burayı
// açar. Tam ekran: 286 px'lik sol panel bir ofis sahnesi için fazla dar.
// Ofis açıkken ana sahne durur (three/Scene.tsx frameloop) — GPU iki sahneyi
// birden çizmesin (Faz 0 performans hedefi).

function useNow(): number {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

export function OfficeView() {
  const open = useNavigationStore((s) => s.activeModule === 'agents');
  const toggleModule = useNavigationStore((s) => s.toggleModule);
  const snapshot = useOfficeStore((s) => s.snapshot);
  const setSnapshot = useOfficeStore((s) => s.setSnapshot);
  const selectedDesk = useOfficeStore((s) => s.selectedDesk);
  const selectDesk = useOfficeStore((s) => s.selectDesk);
  const tab = useOfficeStore((s) => s.tab);
  const setTab = useOfficeStore((s) => s.setTab);
  const [offline, setOffline] = useState(false);
  const [claudeQuota, setClaudeQuota] = useState<ClaudeQuota | null>(null);

  // Claude kotası panodan (adım 6): Claude Code'un kendi rate_limit_event'i, 30 sn'de bir.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const load = () =>
      void fetchPano().then((data) => {
        if (!cancelled && data?.agents?.claude) setClaudeQuota(data.agents.claude);
      });
    load();
    const id = setInterval(load, 30_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [open]);
  const now = useNow();

  // Açılışta bir kez tam görüntü — WebSocket yalnız değişiklikte yayınlıyor,
  // ofis kapalıyken gelenler zaten store'da ama backend yeni açılmış olabilir.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void fetchOfficeState().then((s) => {
      if (cancelled) return;
      if (s) {
        setSnapshot(s);
        setOffline(false);
      } else {
        setOffline(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [open, setSnapshot]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (selectedDesk) selectDesk(null);
      else toggleModule('agents');
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, selectedDesk, selectDesk, toggleModule]);

  const stats = useMemo(() => {
    const workers = snapshot?.workers ?? [];
    const active = workers.filter((w) => w.status === 'calisiyor' || w.status === 'onay_bekliyor');
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const todayTs = today.getTime() / 1000;
    const rootsToday = (snapshot?.tasks ?? []).filter((t) => !t.parent && t.created >= todayTs);
    return {
      active: active.length,
      sessions: workers.filter((w) => w.kind === 'chief' && isActive(w.status)).length,
      tasksToday: rootsToday.length,
      approvals: snapshot?.approvals.length ?? 0,
    };
  }, [snapshot]);

  const desk = snapshot?.desks.find((d) => d.id === selectedDesk) ?? null;
  const quota = snapshot?.quota.codex;
  const lastEvent = snapshot?.tracking.last_event_ts ?? null;

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="office"
          className="office-view"
          initial={{ opacity: 0, scale: 1.02, filter: 'blur(10px)' }}
          animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }}
          exit={{ opacity: 0, scale: 1.02, filter: 'blur(10px)' }}
          transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
        >
          {/* Üst şerit */}
          <header className="office-top">
            <div className="glass-panel office-top__brand">
              <span className="label-micro">Aıron · Ajan Ofisi</span>
              <span className="office-live">
                <span className={`office-live__dot ${lastEvent && now - lastEvent < 60 ? 'is-live' : ''}`} />
                {offline ? 'Aıron backend kapalı' : lastEvent ? `son olay ${ago(lastEvent, now)}` : 'henüz olay yok'}
              </span>
            </div>

            <div className="glass-panel office-tabs" role="tablist">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={tab === t.id}
                  onClick={() => setTab(t.id)}
                  className={`office-tabs__tab ${tab === t.id ? 'is-on' : ''}`}
                >
                  {tab === t.id && <motion.span layoutId="office-tab" className="office-tabs__glow" />}
                  <span className="relative">{t.label}</span>
                </button>
              ))}
            </div>

            <div className="office-top__right">
              <div className="glass-panel office-kpis">
                <Kpi label="Çalışan" value={stats.active} />
                <Kpi label="Oturum" value={stats.sessions} />
                <Kpi label="Bugün" value={stats.tasksToday} />
                <Kpi label="Onay" value={stats.approvals} warn={stats.approvals > 0} />
                {claudeQuota && (claudeQuota.five_hour || claudeQuota.seven_day) && (
                  <div
                    className={`office-quota is-${claudeQuota.level}`}
                    title={claudeQuota.reason || 'Claude aboneliğinin doluluğu (Claude Code bildiriyor) · %90’da yeni iş durur'}
                  >
                    <span className="label-micro">Claude kota</span>
                    {claudeQuota.five_hour && <QuotaBar label="5 sa" pct={claudeQuota.five_hour.used * 100} />}
                    {claudeQuota.seven_day && <QuotaBar label="hafta" pct={claudeQuota.seven_day.used * 100} />}
                  </div>
                )}
                {quota?.primary && (
                  <div className="office-quota" title="Codex kullanım sınırı (Codex'in kendi kaydından)">
                    <span className="label-micro">Codex kota</span>
                    <QuotaBar label="5 sa" pct={quota.primary.used_percent} />
                    {quota.secondary && <QuotaBar label="hafta" pct={quota.secondary.used_percent} />}
                  </div>
                )}
              </div>
              <button
                type="button"
                className="glass-panel office-close"
                onClick={() => toggleModule('agents')}
                aria-label="Ofisi kapat"
              >
                <LuX size={15} strokeWidth={1.8} />
              </button>
            </div>
          </header>

          <AnimatePresence mode="wait">
            <motion.div
              key={tab}
              className="office-board-layer"
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 14 }}
              transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
            >
              {tab === 'komuta' ? <Komuta /> : tab === 'isler' ? <CardBoard /> : <TaskBoard />}
            </motion.div>
          </AnimatePresence>

          {/* Geçmiş'teki bir görevden açılan masa kartı (canlı akış) Komuta'nın üstüne gelir. */}
          <AnimatePresence>{tab === 'komuta' && desk && <AgentCard key={desk.id} desk={desk} />}</AnimatePresence>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function Kpi({ label, value, warn = false }: { label: string; value: number; warn?: boolean }) {
  return (
    <div className={`office-kpi ${warn ? 'is-warn' : ''}`}>
      <span className="label-micro">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function QuotaBar({ label, pct }: { label: string; pct: number }) {
  const v = Math.max(0, Math.min(100, pct));
  return (
    <div className="office-quota__row">
      <span>{label}</span>
      <span className="office-quota__track">
        <span className={`office-quota__fill ${v > 80 ? 'is-hot' : ''}`} style={{ width: `${v}%` }} />
      </span>
      <span>%{Math.round(v)}</span>
    </div>
  );
}
