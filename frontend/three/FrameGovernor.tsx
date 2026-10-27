'use client';

import { useEffect } from 'react';
import { useThree } from '@react-three/fiber';
import { useAIStateStore } from '@/stores/aiStateStore';
import { usePowerStore } from '@/stores/powerStore';

// Uyarlanır kare hızı (Faz 0, 2026-10-02).
//
// ÖLÇÜM: pencere açık ve Chiron BOŞTAYKEN WebView2'nin GPU süreci 3D motoru
// ortalama ~%74 kullanıyordu (tepside %0). Sahne ekran yenileme hızında, hiç
// durmadan çiziliyordu — kimse bakmazken ya da hiçbir şey olmazken bile.
// Hedef: Claude/Codex işleri arka planda koşarken Chiron makineyi yormasın.
//
// Kural: canlılık gerektiğinde tam akıcılık, gerekmediğinde tasarruf.
//   • Chiron dinliyor/düşünüyor/konuşuyor, fare hareket ediyor ya da açılış
//     sahnelemesi sürüyor → 60 FPS (yüksek tazelemeli ekranda da 60'ta sınırlı;
//     CLAUDE.md § PERFORMANCE hedefi zaten 60).
//   • Boşta ve pencere odakta → 30 FPS. Çekirdeğin yavaş nefesi ve tozun
//     süzülmesi 30'da da akıcı okunuyor.
//   • Pencere odakta değil (kullanıcı başka uygulamada) → 20 FPS.
//   • Uyku perdesi → 15 FPS (yalnızca sönük nefes kalıyor).
//   • Sekme/pencere gizli → tarayıcı rAF'ı zaten durduruyor.
//
// Bütün useFrame'ler `delta`/`elapsedTime` ile zamana bağlı (2026-10-02'de
// kontrol edildi) — kare seyrekleşince hareket YAVAŞLAMAZ, yalnızca daha seyrek
// örneklenir. Yeni bir useFrame kare başına sabit artış kullanırsa bu bozulur.
//
// Canvas `frameloop="demand"` ile çalışır; bu bileşen kendi rAF döngüsünde
// hedef aralık dolunca `invalidate()` çağırır. FrameProbe artık gerçek çizim
// hızını ölçer (boşta ~30 görmek beklenen).

const ACTIVE_FPS = 60;
const IDLE_FPS = 30;
const BLURRED_FPS = 20;
const ASLEEP_FPS = 15;
/** Fare/klavye hareketinden sonra tam akıcılığın sürdüğü süre (ms). */
const ACTIVITY_HOLD_MS = 2500;
/** Açılış sahnelemesi (three/reveal.ts + panel girişleri ~5.5 sn) — tam akıcı. */
const BOOT_FULL_MS = 9000;

export function FrameGovernor() {
  const invalidate = useThree((state) => state.invalidate);

  useEffect(() => {
    const born = performance.now();
    let lastInput = born;
    let lastFrame = 0;
    let raf = 0;

    const markInput = () => {
      lastInput = performance.now();
    };
    window.addEventListener('pointermove', markInput, { passive: true });
    window.addEventListener('pointerdown', markInput, { passive: true });
    window.addEventListener('wheel', markInput, { passive: true });
    window.addEventListener('keydown', markInput);

    // Tanı: `window.__chironGovernor()` — hangi kural, hangi hedef, kaç tick/kare.
    // FrameProbe ile aynı gerekçe: "boşta 30 FPS" bir iddia, ölçülebilir kalmalı.
    let rule = 'açılış';
    let ticks = 0;
    let requested = 0;
    const diag = window as unknown as { __chironGovernor?: () => Record<string, unknown> };
    diag.__chironGovernor = () => ({ rule, target: targetFps(performance.now()), ticks, requested });

    const targetFps = (now: number): number => {
      if (usePowerStore.getState().powerState === 'asleep') return ((rule = 'uyku'), ASLEEP_FPS);
      if (now - born < BOOT_FULL_MS) return ((rule = 'açılış'), ACTIVE_FPS);
      if (useAIStateStore.getState().aiState !== 'idle') return ((rule = 'aktif'), ACTIVE_FPS);
      if (now - lastInput < ACTIVITY_HOLD_MS) return ((rule = 'girdi'), ACTIVE_FPS);
      return document.hasFocus() ? ((rule = 'boşta'), IDLE_FPS) : ((rule = 'odak dışı'), BLURRED_FPS);
    };

    const tick = (now: number) => {
      raf = requestAnimationFrame(tick);
      ticks += 1;
      // Birikimli zamanlama: hedef aralık, ekranın vsync aralığının katı değilse
      // (144 Hz'de 6.9 ms) "son kareden beri ≥ aralık" kuralı 60 hedefini 48'e
      // düşürüyordu. Bir sonraki kare zamanı `lastFrame + aralık`; yarım vsync
      // kadar erken gelen tick kabul edilir, uzun vadede ortalama tam hedef olur.
      const interval = 1000 / targetFps(now);
      const due = lastFrame + interval;
      if (now >= due - 3) {
        // Uzun bir boşluktan sonra (sekme gizliydi) geçmişi telafi etmeye çalışma.
        lastFrame = now - due > interval ? now : due;
        requested += 1;
        invalidate();
      }
    };
    raf = requestAnimationFrame(tick);

    return () => {
      delete diag.__chironGovernor;
      cancelAnimationFrame(raf);
      window.removeEventListener('pointermove', markInput);
      window.removeEventListener('pointerdown', markInput);
      window.removeEventListener('wheel', markInput);
      window.removeEventListener('keydown', markInput);
    };
  }, [invalidate]);

  return null;
}
