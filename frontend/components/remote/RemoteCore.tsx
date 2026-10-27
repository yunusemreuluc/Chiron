'use client';

import type { AIState } from '@/stores/aiStateStore';
import { SLEEP_PALETTE, STATE_PALETTE } from '@/three/coreColors';

// Telefonun enerji çekirdeği — masaüstündeki tel kafes hologramın CSS kardeşi.
//
// Neden WebGL değil: telefonda sürekli açık bir bloom sahnesi pili bitirir ve
// Three.js paketi mobil veride ağır. Kural yine aynı (Notes/Tasarim-Kurallari.md
// § Enerji çekirdeği): asla durağan değil, durumu RENKLE anlatıyor ve renk
// palette.ts'in TEK kaynağından geliyor — telefonda konuşan Chiron da turkuaz.
//
// Hareket hızları duruma göre DEĞİŞMİYOR, bilerek: CSS'te çalışan bir
// animasyonun süresini değiştirmek dönüşü o anda ileri/geri sıçratıyor
// (bkz. Bilinen-Tuzaklar § Sönümle, asla sıçratma). Durum geçişi yalnızca
// renk ve ışıma üzerinden, uzun bir easing ile akıyor.
//
// Yörüngelerin `linear` dönüşü § Animasyon'daki "asla lineer" kuralının tek
// bilinçli istisnası: sürekli bir dönüşe easing verilirse her turun sonunda
// yavaşlayıp hızlanıyor, yani cisim takılıyormuş gibi okunuyor. Masaüstündeki
// yörünge düğümleri de sabit açısal hızla dönüyor.

const COLOR_TRANSITION =
  'background-color 900ms var(--ease-standard), border-color 900ms var(--ease-standard), box-shadow 900ms var(--ease-standard), opacity 900ms var(--ease-standard)';

export function RemoteCore({
  state,
  size,
  online = true,
}: {
  state: AIState;
  size: number;
  /** PC'ye bağlı değilken çekirdek uyku paletine iner: sönmüş değil, dinlenen. */
  online?: boolean;
}) {
  const palette = online ? STATE_PALETTE[state] : SLEEP_PALETTE;
  const active = online && state !== 'idle' && state !== 'listening';
  const ring = Math.max(1, size / 90);

  return (
    <div
      aria-hidden
      className="pointer-events-none relative shrink-0"
      style={{ width: size, height: size }}
    >
      {/* Işıma — çekirdeğin arkasındaki bulanık hacim. */}
      <span
        className="absolute inset-[14%] rounded-full"
        style={{
          backgroundColor: palette.bodyLight,
          opacity: active ? 0.5 : 0.3,
          filter: `blur(${size * 0.22}px)`,
          animation: 'remote-halo 5.2s var(--ease-standard) infinite',
          transition: COLOR_TRANSITION,
        }}
      />

      {/* Dış yörünge — yarım ark, yavaş dönüş. */}
      <span
        className="absolute inset-0 rounded-full border-solid"
        style={{
          borderWidth: ring,
          borderColor: `${palette.corona}10`,
          borderTopColor: `${palette.corona}cc`,
          borderRightColor: `${palette.corona}55`,
          animation: 'remote-spin 14s linear infinite',
          transition: COLOR_TRANSITION,
        }}
      />

      {/* İç yörünge — tam halka + ters dönen kısa ark: tel kafesin enlem hissi. */}
      <span
        className="absolute inset-[15%] rounded-full border-solid"
        style={{
          borderWidth: ring,
          borderColor: `${palette.rim}1f`,
          borderBottomColor: `${palette.rim}99`,
          animation: 'remote-spin-reverse 9s linear infinite',
          transition: COLOR_TRANSITION,
        }}
      />

      {/* Gövde — nefes alan küre. */}
      <span
        className="absolute inset-[31%] rounded-full"
        style={{
          backgroundColor: palette.bodyDeep,
          boxShadow: `0 0 ${size * 0.16}px ${palette.bodyLight}${active ? 'aa' : '66'}, inset 0 0 ${size * 0.1}px ${palette.bodyLight}cc, inset 0 ${size * 0.03}px ${size * 0.05}px ${palette.rim}66`,
          animation: 'remote-breathe 4.6s var(--ease-standard) infinite',
          transition: COLOR_TRANSITION,
        }}
      >
        {/* Parlama — durumdan bağımsız beyaz bir tepe ışığı, küreye hacim veriyor. */}
        <span
          className="absolute inset-0 rounded-full"
          style={{
            background:
              'radial-gradient(circle at 34% 28%, rgba(255,255,255,0.55) 0%, rgba(255,255,255,0.08) 32%, transparent 58%)',
          }}
        />
      </span>
    </div>
  );
}
