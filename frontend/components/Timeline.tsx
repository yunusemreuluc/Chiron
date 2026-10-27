'use client';

import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  LuActivity,
  LuBrain,
  LuChevronDown,
  LuCircleCheck,
  LuCircleX,
  LuTerminal,
} from 'react-icons/lu';
import { useTimelineStore, type TimelineEntry } from '@/stores/timelineStore';
import { AI_STATE_LABELS, useAIStateStore } from '@/stores/aiStateStore';
import { GlassPanel } from './GlassPanel';

// CHIRON alt zaman çizelgesi — Notes/Tasarim-Kurallari.md § Panel yerleşimi
// (Timeline / Reasoning / Tasks / Progress / Logs) + "Never clutter."
//
// "Never clutter" burada belirleyici oldu: panel VARSAYILAN OLARAK KAPALI, alt
// kenarda ince bir şerit hâlinde duruyor ve son olayı tek satırda gösteriyor.
// Açıldığında akışın tamamı geliyor. Sürekli açık duran bir log paneli 3D
// sahnenin alt üçte birini yutardı — oysa sahne bu ürünün kendisi.
//
// Şerit sol kenardan başlamıyor: Sidebar rayı (18px + 68px) ve sağ alttaki
// AssistantDock ile çakışmasın diye iki taraftan da içeride duruyor.
const OPEN_HEIGHT = 208;

export function Timeline() {
  const entries = useTimelineStore((state) => state.entries);
  const runningCount = useTimelineStore((state) => state.runningCount);
  const lastTouchedId = useTimelineStore((state) => state.lastTouchedId);
  const aiState = useAIStateStore((state) => state.aiState);
  const [isOpen, setIsOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Yeni kayıt gelince en alta kaydır — akış canlıysa kullanıcı son olayı
  // görmek ister, elle kaydırmak zorunda kalmamalı.
  useEffect(() => {
    const element = scrollRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [entries, isOpen]);

  // Dizinin sonu DEĞİL, en son dokunulan kayıt: biten bir görev kendi eski
  // satırını güncelliyor, yani en yeni olay listenin sonunda olmayabiliyor
  // (bkz. timelineStore.lastTouchedId).
  const latest = entries.find((entry) => entry.id === lastTouchedId) ?? entries[entries.length - 1];

  return (
    <div className="pointer-events-none absolute bottom-7 left-[104px] z-30 w-[min(520px,calc(100%-460px))]">
      <GlassPanel className="pointer-events-auto flex flex-col overflow-hidden">
        {/* ── Şerit: her zaman görünen tek satır ── */}
        <button
          type="button"
          onClick={() => setIsOpen((open) => !open)}
          aria-expanded={isOpen}
          className="flex items-center gap-3 px-3 py-2.5 text-left transition-colors duration-200 hover:bg-white/[0.03]"
        >
          <span className="relative flex h-7 w-7 shrink-0 items-center justify-center">
            <LuActivity
              size={14}
              strokeWidth={1.8}
              className={runningCount > 0 ? 'text-primary' : 'text-foreground-disabled'}
            />
            {/* İlerleme göstergesi: çalışan araç varken genişleyip sönen halka.
                Sahte bir yüzde göstermiyor — kaç araç çalıştığını biliyoruz,
                ne kadar süreceğini bilmiyoruz. */}
            {runningCount > 0 && (
              <motion.span
                className="border-primary absolute rounded-full border"
                initial={false}
                animate={{ width: [10, 26], height: [10, 26], opacity: [0.5, 0] }}
                transition={{ duration: 1.5, repeat: Infinity, ease: 'easeOut' }}
              />
            )}
          </span>

          <span className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="label-micro">
              {runningCount > 0 ? `${runningCount} görev çalışıyor` : 'Zaman çizelgesi'}
            </span>
            <span className="text-foreground-secondary truncate text-[11px]">
              {latest ? summarize(latest) : `Chiron ${AI_STATE_LABELS[aiState].toLowerCase()}`}
            </span>
          </span>

          <motion.span
            animate={{ rotate: isOpen ? 180 : 0 }}
            transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
            className="text-foreground-disabled shrink-0"
          >
            <LuChevronDown size={14} strokeWidth={1.8} />
          </motion.span>
        </button>

        {/* ── Akış ── */}
        <AnimatePresence initial={false}>
          {isOpen && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: OPEN_HEIGHT, opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
              className="overflow-hidden"
            >
              <hr className="hairline" />
              <div ref={scrollRef} className="h-full overflow-y-auto px-3 py-2.5">
                {entries.length === 0 ? (
                  <p className="text-foreground-disabled text-[11px] leading-relaxed">
                    Chiron bir araç çalıştırdığında (hava durumu, ekran analizi, nesne tanıma...)
                    burada görünecek.
                  </p>
                ) : (
                  <ol className="flex flex-col gap-2">
                    {entries.map((entry) => (
                      <TimelineRow key={entry.id} entry={entry} />
                    ))}
                  </ol>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </GlassPanel>
    </div>
  );
}

function summarize(entry: TimelineEntry): string {
  if (entry.kind === 'task') {
    const suffix = entry.detail ? ` — ${entry.detail}` : '';
    if (entry.status === 'running') return `${entry.title} çalışıyor${suffix}`;
    return `${entry.title}${entry.status === 'failed' ? ' başarısız' : ''}${suffix}`;
  }
  return entry.detail;
}

// Muhakeme satırı diğerlerinden AYRI okunmalı: görev ve log birer olay kaydı,
// muhakeme ise Chiron'un kendi sesi. İtalik ve girintili — bir kenar notu gibi.
const REASONING_TEXT = 'text-foreground-secondary italic';

function TimelineRow({ entry }: { entry: TimelineEntry }) {
  const time = new Date(entry.at).toLocaleTimeString('tr-TR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

  return (
    <li className="flex items-start gap-2.5">
      <span className="numeric text-foreground-disabled w-[52px] shrink-0 pt-[1px] text-[10px]">
        {time}
      </span>
      <span className="flex w-4 shrink-0 justify-center pt-[2px]">
        <StatusMark entry={entry} />
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        {entry.title && (
          <span
            className={`text-[11px] font-medium ${
              entry.status === 'failed' ? 'text-[#ff8f8f]' : 'text-foreground'
            }`}
          >
            {entry.title}
          </span>
        )}
        {entry.detail && (
          <span
            className={`text-[11px] leading-snug break-words ${
              entry.kind === 'reasoning' ? REASONING_TEXT : 'text-foreground-secondary'
            }`}
          >
            {entry.detail}
          </span>
        )}
      </span>
    </li>
  );
}

function StatusMark({ entry }: { entry: TimelineEntry }) {
  if (entry.kind === 'reasoning') {
    return <LuBrain size={11} strokeWidth={1.8} className="text-primary/70" />;
  }
  if (entry.kind === 'log') {
    return <LuTerminal size={11} strokeWidth={1.8} className="text-foreground-disabled" />;
  }
  if (entry.status === 'running') {
    // Dönen değil, nabız atan: dönen bir çember "yükleniyor" der, nabız
    // "yaşıyor" der — sahnenin diliyle aynı.
    return (
      <motion.span
        className="bg-primary mt-[3px] block h-1.5 w-1.5 rounded-full"
        style={{ boxShadow: '0 0 8px var(--color-primary)' }}
        animate={{ opacity: [0.35, 1, 0.35] }}
        transition={{ duration: 1.2, repeat: Infinity, ease: 'easeInOut' }}
      />
    );
  }
  if (entry.status === 'failed') {
    return <LuCircleX size={11} strokeWidth={2} className="text-[#ff8f8f]" />;
  }
  return <LuCircleCheck size={11} strokeWidth={2} className="text-primary/70" />;
}
