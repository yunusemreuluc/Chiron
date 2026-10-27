'use client';

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { LuClock, LuEye } from 'react-icons/lu';
import { fetchAutomation, type AutomationSnapshot } from '@/services/modulesApi';

// Otomasyon modülü — kullanıcı isteğiyle (2026-07-30) backend'e bağlandı.
// Veri kaynağı `ChironLive._active_watches` (bkz. backend/api/automation.py).
//
// Hafızanın aksine bu veri DOSYADA DEĞİL, ses döngüsünün belleğinde — o yüzden
// periyodik olarak yenilenmesi gerekiyor: bir izleme koşulu gerçekleşince
// kendiliğinden kalkıyor ve panel bunu ancak tekrar sorarak öğrenebilir.
const REFRESH_MS = 5000;

function formatRemaining(totalSeconds: number): string {
  if (totalSeconds <= 0) return 'süresi doldu';
  const minutes = Math.floor(totalSeconds / 60);
  if (minutes < 1) return `${totalSeconds} sn kaldı`;
  if (minutes < 60) return `${minutes} dk kaldı`;
  const hours = Math.floor(minutes / 60);
  return `${hours} sa ${minutes % 60} dk kaldı`;
}

export function AutomationPanelContent() {
  const [snapshot, setSnapshot] = useState<AutomationSnapshot | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      void fetchAutomation().then((data) => {
        if (!cancelled && data) setSnapshot(data);
      });
    };
    load();
    const timer = window.setInterval(load, REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  if (!snapshot) {
    return <p className="text-foreground-disabled text-xs">Otomasyon durumu okunuyor...</p>;
  }

  if (!snapshot.available) {
    return (
      <p className="text-foreground-secondary text-xs leading-relaxed">
        Sesli asistan bu pencerede çalışmıyor, bakacak bir izleme yok. Masaüstündeki{' '}
        <strong className="text-foreground font-medium">Chiron</strong> kısayoluyla açarsan aktif
        izlemeler burada görünür.
      </p>
    );
  }

  const briefingEntries = Object.entries(snapshot.briefing ?? {});

  if (snapshot.watches.length === 0 && briefingEntries.length === 0) {
    return (
      <p className="text-foreground-secondary text-xs leading-relaxed">
        Aktif izleme yok. Chiron&apos;a &ldquo;şunu izle, olunca haber ver&rdquo; dediğinde burada
        görünür.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {snapshot.watches.length > 0 && (
        <div className="flex flex-col gap-2">
          <div className="flex items-baseline justify-between gap-2">
            <span className="label-micro">Aktif izleme</span>
            <span className="numeric text-foreground-disabled text-[10px]">
              {snapshot.watches.length}
            </span>
          </div>

          <ul className="flex flex-col gap-1.5">
            {snapshot.watches.map((watch) => (
              <li
                key={watch.id}
                className="border-border-subtle flex gap-2.5 rounded-[10px] border bg-white/[0.03] px-2.5 py-2"
              >
                {/* Nabız atan göz: izleme AKTİF, yani şu anda bir şey oluyor. */}
                <motion.span
                  className="text-primary mt-[2px] shrink-0"
                  animate={{ opacity: [0.4, 1, 0.4] }}
                  transition={{ duration: 2.2, repeat: Infinity, ease: 'easeInOut' }}
                >
                  <LuEye size={12} strokeWidth={1.8} />
                </motion.span>
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="text-foreground text-[11px] leading-snug break-words">
                    {watch.instruction}
                  </span>
                  <span className="text-foreground-secondary text-[10px] leading-snug break-words">
                    Koşul: {watch.condition}
                  </span>
                  <span className="numeric text-foreground-disabled text-[10px]">
                    {formatRemaining(watch.remainingSeconds)}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {briefingEntries.length > 0 && (
        <div className="flex flex-col gap-2">
          <span className="label-micro">Günlük brifing</span>
          <ul className="flex flex-col gap-1.5">
            {briefingEntries.map(([key, value]) => (
              <li
                key={key}
                className="border-border-subtle flex items-center gap-2.5 rounded-[10px] border bg-white/[0.03] px-2.5 py-2"
              >
                <LuClock
                  size={12}
                  strokeWidth={1.8}
                  className="text-foreground-disabled shrink-0"
                />
                <span className="text-foreground text-[11px] break-words">
                  {readBriefingValue(value)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** Brifing kayıtları hafızadan geliyor: {"value": "08:30"} sarmalı olabilir de olmayabilir. */
function readBriefingValue(value: unknown): string {
  if (typeof value === 'object' && value !== null && 'value' in value) {
    return String((value as { value: unknown }).value);
  }
  return String(value);
}
