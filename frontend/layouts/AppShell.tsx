'use client';

import { useEffect } from 'react';
import dynamic from 'next/dynamic';
import { motion, type Variants } from 'framer-motion';
import { AssistantDock } from '@/components/AssistantDock';
import { BootOverlay } from '@/components/BootOverlay';
import { BrandBadge } from '@/components/BrandBadge';
import { LeftPanel } from '@/components/LeftPanel';
import { NodeFocusCard } from '@/components/NodeFocusCard';
import { OfficeView } from '@/components/office/OfficeView';
import { Sidebar } from '@/components/Sidebar';
import { SleepVeil } from '@/components/SleepVeil';
import { TelemetryCard } from '@/components/TelemetryCard';
import { Timeline } from '@/components/Timeline';
import { TrayControl } from '@/components/TrayControl';
import { VisionPanel } from '@/components/VisionPanel';
import { useAIStateConnection } from '@/hooks/useAIStateConnection';
import { useMouseParallax } from '@/hooks/useMouseParallax';
import { useThinkingSound } from '@/hooks/useThinkingSound';
import { fetchSettings } from '@/services/settingsApi';
import { configureSfx, playSfx } from '@/services/sfxPlayer';
import { usePowerStore } from '@/stores/powerStore';

// WebGL yalnızca istemcide anlamlı — SSR sırasında render edilmiyor.
const Scene = dynamic(() => import('@/three/Scene').then((mod) => mod.Scene), {
  ssr: false,
});

// Açılış Animasyonu: "Panels" adımı — BootOverlay'in
// logosu kalktıktan, 3D sahne (Energy Core/Nodes/Electricity) belirmeye
// başladıktan SONRA gelir. Sabit gecikmeler three/reveal.ts'teki 3D zaman
// çizelgesiyle aynı mount anını (t=0) paylaşıyor.
const PANEL_REVEAL_BASE_DELAY = 5.0;
const PANEL_REVEAL_STEP = 0.12;

const panelVariants: Variants = {
  hidden: { opacity: 0, y: 10 },
  visible: (delay: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, ease: 'easeOut', delay },
  }),
};

// Alt kenara YAPIŞIK paneller (zaman çizelgesi, sohbet dock'u) için yalnızca
// opacity — `y` bir transform yaratır, transform ise "containing block" kurar
// ve içindeki `bottom-7` konumlu kartlar sahnenin altına değil sarmalayıcının
// tepesine hizalanır. Yerleşim sessizce bozulurdu.
const fadeOnlyVariants: Variants = {
  hidden: { opacity: 0 },
  visible: (delay: number) => ({
    opacity: 1,
    transition: { duration: 0.5, ease: 'easeOut', delay },
  }),
};

export function AppShell() {
  // backend'in WebSocket'ine bağlanır; bağlanamazsa
  // (main.py kapalıysa) otomatik olarak demo döngüye düşer (bkz. useAIStateConnection.ts).
  useAIStateConnection();
  // `SFX/Think.mp3` — Aıron düşündüğü sürece çalan arka plan dokusu.
  useThinkingSound();

  // Ses efektleri açılışta bir kez yapılandırılır (kullanıcı ayarlar panelini
  // hiç açmasa bile geçerli olmalı) ve açılış sesi çalınır — Tkinter sürümündeki
  // _play_startup_sfx_once davranışının karşılığı.
  useEffect(() => {
    void fetchSettings().then((settings) => {
      if (!settings) return;
      configureSfx({ enabled: settings.sfxEnabled, volume: settings.sfxVolume });
      playSfx('startup');
    });
  }, []);

  // Mouse Interaction: Depth, Parallax. Parallax ve
  // boot-giriş animasyonu AYRI DOM düğümlerinde çalışıyor (ikisi de `transform`
  // kullanıyor, aynı elemanda çakışırlardı) — bkz. aşağıdaki iç içe motion.div + ref yapısı.
  const sidebarParallax = useMouseParallax<HTMLDivElement>(3);

  // Aıron uyurken HUD tamamen çekiliyor: geriye sadece karanlık ve çekirdeğin
  // sönük nefesi kalıyor (bkz. components/SleepVeil.tsx). Panelleri yalnızca
  // perdenin altında karartmak yetmezdi — cam yüzeyler blur'ları yüzünden
  // karanlıkta bile "açık pencere" gibi okunuyor.
  //
  // DİKKAT — bu sınıf motion.div'lerin KENDİSİNE verilemez: framer-motion
  // `opacity`yi satır içi stil olarak yazıyor ve satır içi stil, Tailwind'in
  // `opacity-0` sınıfını her zaman ezer (ilk denemede HUD hiç sönmedi, yalnızca
  // perdenin altında karardı). Bu yüzden açılış animasyonu dış motion.div'de,
  // uyku sönmesi İÇ div'de: iki kütüphane aynı özellik için yarışmıyor.
  const isAsleep = usePowerStore((state) => state.powerState === 'asleep');
  const hudClass = `transition-opacity duration-[900ms] ${
    isAsleep ? 'pointer-events-none opacity-0' : 'opacity-100'
  }`;

  return (
    <div className="app-shell">
      <motion.div
        variants={panelVariants}
        custom={PANEL_REVEAL_BASE_DELAY}
        initial="hidden"
        animate="visible"
        className="app-shell__sidebar z-20"
      >
        {/* Parallax yalnızca `transform` yazıyor (bkz. useMouseParallax), bu
            yüzden uyku sönmesi aynı elemanda güvenle durabiliyor. */}
        <div ref={sidebarParallax} className={`h-full w-full ${hudClass}`}>
          <Sidebar />
        </div>
      </motion.div>

      <motion.div
        variants={panelVariants}
        custom={PANEL_REVEAL_BASE_DELAY + PANEL_REVEAL_STEP}
        initial="hidden"
        animate="visible"
      >
        <div className={hudClass}>
          <BrandBadge />
        </div>
      </motion.div>

      {/* ── Sağ kolon: duyular ve sistem kontrolleri ──
          Tepsi düğmesi, Vision paneli ve düğüm odak kartı ÜSTTEN ALTA tek bir
          yığında. Önceden her biri kendini `absolute right-7` ile
          konumlandırıyordu ve üst üste biniyorlardı; kolon hem çakışmayı
          tamamen bitiriyor hem de yeni bir panel eklemeyi tek satıra indiriyor. */}
      <motion.div
        variants={panelVariants}
        custom={PANEL_REVEAL_BASE_DELAY + PANEL_REVEAL_STEP * 2}
        initial="hidden"
        animate="visible"
        className="absolute top-7 right-7 z-30 w-[286px]"
      >
        <div className={`flex flex-col items-end gap-3 ${hudClass}`}>
          {/* Telemetri ve tepsi TEK SATIR: ikisi de sistem kontrolü, ikisi de
              tek satırlık (kullanıcı isteği, 2026-07-31). */}
          <div className="flex items-center gap-2.5">
            <TelemetryCard />
            <TrayControl />
          </div>
          <VisionPanel />
          <NodeFocusCard />
        </div>
      </motion.div>

      <div className="app-shell__scene overflow-hidden">
        <Scene />
        {/* Sahne perdenin ALTINDA görünmeye devam ediyor; yalnızca üstündeki
            paneller sönüyor. Sarmalayıcı `position` almıyor — içindeki mutlak
            konumlu kartlar hâlâ .app-shell__scene'e göre yerleşiyor. */}
        <div className={hudClass}>
          <LeftPanel />
          {/* Zaman çizelgesi ve sohbet dock'u SÜREKLİ görünür olduğu için
              açılış sahnelemesine dahil — önceden ilk kareden itibaren tam
              görünürlerdi ve logo daha çıkmadan ekranda duruyorlardı.
              (LeftPanel/NodeFocusCard yalnızca kullanıcı açınca geldiği için
              sahnelemeye girmiyor.) */}
          <motion.div
            variants={fadeOnlyVariants}
            custom={PANEL_REVEAL_BASE_DELAY + PANEL_REVEAL_STEP * 3}
            initial="hidden"
            animate="visible"
          >
            <Timeline />
          </motion.div>
          <motion.div
            variants={fadeOnlyVariants}
            custom={PANEL_REVEAL_BASE_DELAY + PANEL_REVEAL_STEP * 4}
            initial="hidden"
            animate="visible"
          >
            <AssistantDock />
          </motion.div>
        </div>
      </div>

      {/* Ajan Ofisi — "Ajanlar" modülü tam ekran açılır (bkz. components/office). */}
      <OfficeView />
      <SleepVeil />
      <BootOverlay />
    </div>
  );
}
