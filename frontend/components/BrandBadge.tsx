'use client';

import { motion } from 'framer-motion';
import { AI_STATE_LABELS, useAIStateStore, type AIState } from '@/stores/aiStateStore';
import { useAmbientContext } from '@/hooks/useAmbientContext';
import { useRailHoverStore } from '@/stores/railHoverStore';

// Kullanıcı isteğiyle (2026-07-28) — üst panel tamamen kaldırıldı; CHIRON adı ve
// canlı durum sahnenin sol üstünde küçük, çerçevesiz bir imza olarak duruyor
// (gökyüzünü kapatan bir çubuk yerine). Bildirim/profil ikonları Sidebar'ın altına
// taşındı, bkz. Sidebar.tsx.
//
// "Daha profesyonel" düzenleme (2026-07-28): durum artık sadece metin değil —
// yanındaki nokta AI durumuna göre hem renk hem nabız hızı değiştiriyor. Tek
// vurgu renkli palette (bkz. app/globals.css) durumlar farklı RENKLERLE değil,
// aynı mavinin farklı YOĞUNLUKLARIYLA ayrışıyor; boştayken nötr çeliğe düşüyor.
const STATE_DOT: Record<AIState, { color: string; pulseSeconds: number }> = {
  idle: { color: 'var(--color-secondary)', pulseSeconds: 4 },
  listening: { color: 'var(--color-primary)', pulseSeconds: 1.2 },
  thinking: { color: 'var(--color-cyan)', pulseSeconds: 2.4 },
  speaking: { color: 'var(--color-primary-strong)', pulseSeconds: 0.9 },
  vision: { color: 'var(--color-primary)', pulseSeconds: 1.8 },
  // Bu iki durum tek vurgu renginin DIŞINA çıkan tek istisna (2026-07-31, bkz.
  // Notes/Arayuz.md § Beş tepki): çekirdek zaten kehribar/mora dönüyor, nokta
  // mavide kalsaydı rozet sahneyle çelişirdi. Değerler three/palette.ts'teki
  // SOLAR_AMBER.rim / DEEP_VIOLET.rim ile aynı — nokta, kürenin kenar rengi.
  automation: { color: '#fff0d6', pulseSeconds: 0.7 },
  memory: { color: '#dcc9ff', pulseSeconds: 2.8 },
};

export function BrandBadge() {
  const aiState = useAIStateStore((state) => state.aiState);
  const { color, pulseSeconds } = STATE_DOT[aiState];
  const context = useAmbientContext();
  // Ray etiketi imzanın ÜSTÜNE biniyor (ölçüldü, bkz. stores/railHoverStore.ts).
  // Çakışmayı gizlemek yerine imza geri çekiliyor: o an bakılan şey kazanır.
  const railHovered = useRailHoverStore((state) => state.hoveredLabel) !== null;

  return (
    // left-[104px]: Sidebar rayının (18px + 68px genişlik) hemen sağında, ondan
    // bir "nefes payı" bırakarak başlar.
    //
    // Sönme framer-motion ile DEĞİL Tailwind ile: bu düz bir div ve satır içi
    // stil yazan bir motion bileşeni değil — tersi olsaydı satır içi opacity
    // sınıfı ezerdi (bkz. Notes/Bilinen-Tuzaklar.md § framer-motion opacity'yi
    // satır içi yazar).
    <div
      className={`pointer-events-none absolute top-7 left-[104px] z-30 flex flex-col gap-1.5 transition-opacity duration-200 ${
        railHovered ? 'opacity-15' : 'opacity-100'
      }`}
    >
      <div className="flex items-center gap-3">
        <span className="relative flex h-1.5 w-1.5 items-center justify-center">
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ background: color, boxShadow: `0 0 10px ${color}` }}
          />
          {/* Genişleyip sönen halka — "canlı bağlantı" işareti. Nabız hızı AI
              durumundan geliyor: dinlerken hızlı, boştayken neredeyse durgun. */}
          <motion.span
            className="absolute rounded-full"
            style={{ border: `1px solid ${color}` }}
            initial={false}
            animate={{ width: [6, 18], height: [6, 18], opacity: [0.5, 0] }}
            transition={{ duration: pulseSeconds, repeat: Infinity, ease: 'easeOut' }}
          />
        </span>
        <span className="text-foreground text-[13px] font-semibold tracking-[0.42em]">CHIRON</span>
      </div>
      <span className="label-micro pl-[18px]">{AI_STATE_LABELS[aiState]}</span>

      {/* Ambient bağlam — Chiron'un farkında OLDUĞU şey (2026-08-01).
          Durum satırından bir kademe daha kısık: bu Chiron'un ne yaptığı değil,
          kullanıcının ne yaptığı. Aynı vurguyla yazılsaydı ikisi tek bir cümle
          gibi okunurdu. Veri yoksa satır hiç çizilmiyor (bkz. useAmbientContext). */}
      {context && (
        <span className="text-foreground-disabled max-w-[260px] truncate pl-[18px] text-[10px] leading-none">
          {context.app || context.windowTitle}
          {context.away && ` · ${Math.floor(context.idleSeconds / 60)} dk uzakta`}
        </span>
      )}
    </div>
  );
}
