'use client';

import { useEffect } from 'react';
import { useFrame } from '@react-three/fiber';

// Kare süresi sondası — CLAUDE.md § PERFORMANCE hedefi 60 FPS.
// Ölçüm sonuçları: Notes/Arayuz.md § Kare hızı
//
// NEDEN KALICI BİR PARÇA: 60 FPS bu projede uzun süre ÖLÇÜLMEMİŞ bir iddiaydı
// (yapılmamış bir iş değil, doğrulanmamış bir söz). Tek seferlik bir ölçüm
// yapıp silmek aynı sorunu bir sonraki değişiklikte geri getirirdi — çekirdeğe
// her yeni durum eklendiğinde iddia yeniden doğrulanabilir olmalı.
//
// MALİYETİ: kare başına bir Float32Array yazması ve iki tamsayı işlemi. Ayırma
// YOK (bkz. § useFrame içinde asla bellek ayırma) — tampon modül düzeyinde bir
// kez ayrılıyor. Sıralama/istatistik yalnızca dışarıdan çağrıldığında oluyor.
//
// Okuma: tarayıcı konsolunda ya da pywebview'den `window.__chironFps()`.
// Ölçüme temiz başlamak için önce `window.__chironFpsReset()`.

// 900 örnek = 60 FPS'te ~15 sn. Halka tampon, yani hep son 15 sn duruyor.
const SAMPLE_COUNT = 900;
const samples = new Float32Array(SAMPLE_COUNT);
let writeIndex = 0;
let filled = 0;
// Halka tampon yalnızca SON 900 kareyi tutuyor. Uzun bir ölçümde toplam kare
// sayısı bundan fazla olur ve tamponun ortancası "tipik" kareyi gösterirken
// aradaki takılmaları gizleyebilir. Bu iki sayaç ölçümü KENDİ KENDİNİ
// doğrular hâle getiriyor: `avgFps` (toplam kare / geçen süre) ile `fps`
// (ortancadan) birbirinden uzaklaşıyorsa arada duraklamalar var demektir.
let totalFrames = 0;
let startedAt = 0;

export interface FrameStats {
  /** Tampondaki örnek sayısı (en fazla 900). */
  count: number;
  /** Sıfırlamadan bu yana çizilen TOPLAM kare. */
  frames: number;
  /** Sıfırlamadan bu yana geçen süre (sn). */
  elapsed: number;
  /** Gerçek ortalama: toplam kare / geçen süre. Takılmaları saklamaz. */
  avgFps: number;
  /** Ortanca kare süresinden türetilen FPS — "tipik" kare hızı. */
  fps: number;
  /** Kare süresi (ms): ortanca, %95'lik dilim, en kötü kare. */
  p50: number;
  p95: number;
  worst: number;
  /**
   * 16.7 ms'yi AŞAN karelerin yüzdesi — 60 FPS bütçesinin kaçırıldığı oran.
   * Ortalama FPS'ten daha dürüst: 120 iyi kare, 1 berbat kareyi gizler ama
   * göz o tek kareyi takılma olarak görür.
   */
  overBudget: number;
}

function computeStats(): FrameStats | null {
  if (filled === 0) return null;
  // Kopya + sıralama sadece BURADA (kare döngüsünde değil), o yüzden ayırma
  // yapmak serbest.
  const sorted = Array.from(samples.subarray(0, filled)).sort((a, b) => a - b);
  const at = (q: number) => sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * q))];
  const p50 = at(0.5);
  const overBudget = sorted.filter((ms) => ms > 1000 / 60).length / sorted.length;
  const elapsed = (performance.now() - startedAt) / 1000;

  return {
    count: sorted.length,
    frames: totalFrames,
    elapsed: Math.round(elapsed * 100) / 100,
    avgFps: elapsed > 0 ? Math.round((totalFrames / elapsed) * 10) / 10 : 0,
    fps: Math.round((1000 / p50) * 10) / 10,
    p50: Math.round(p50 * 100) / 100,
    p95: Math.round(at(0.95) * 100) / 100,
    worst: Math.round(sorted[sorted.length - 1] * 100) / 100,
    overBudget: Math.round(overBudget * 1000) / 10,
  };
}

export function FrameProbe() {
  useFrame((_, delta) => {
    samples[writeIndex] = delta * 1000;
    writeIndex = (writeIndex + 1) % SAMPLE_COUNT;
    if (filled < SAMPLE_COUNT) filled += 1;
    totalFrames += 1;
  });

  useEffect(() => {
    const w = window as unknown as Record<string, unknown>;
    if (startedAt === 0) startedAt = performance.now();
    w.__chironFps = computeStats;
    w.__chironFpsReset = () => {
      writeIndex = 0;
      filled = 0;
      totalFrames = 0;
      startedAt = performance.now();
    };
    return () => {
      delete w.__chironFps;
      delete w.__chironFpsReset;
    };
  }, []);

  return null;
}
