'use client';

import { Suspense, useEffect, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { Environment } from '@react-three/drei';
import { Background } from './Background';
import { CAMERA_DISTANCE, CameraRig } from './CameraRig';
import { ElectricArcs } from './ElectricArcs';
import { EnergyCore } from './EnergyCore';
import { EnergyTendrils } from './EnergyTendrils';
import { FrameProbe } from './FrameProbe';
import { Lighting } from './Lighting';
import { NodeConnections } from './NodeConnections';
import { OrbitNodes } from './OrbitNodes';
import { PostProcessing } from './PostProcessing';
import { useNavigationStore } from '@/stores/navigationStore';

// app/globals.css'teki tablet kırılımıyla (1023px) aynı eşik — bkz. .app-shell
// media query. Performans / Mobile Optimization: dar viewport'larda
// piksel yoğunluğu üst sınırı düşürülüyor (daha az GPU yükü).
const TABLET_BREAKPOINT = 1024;

function useAdaptiveMaxDpr(): number {
  const [maxDpr, setMaxDpr] = useState(1.5);

  useEffect(() => {
    const update = () => setMaxDpr(window.innerWidth < TABLET_BREAKPOINT ? 1 : 1.5);
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  return maxDpr;
}

// Perspective Camera, Lights, Environment, HDR.
// dpr üst sınırı ve alpha:false ile GPU maliyeti düşük tutuluyor (CLAUDE.md § PERFORMANCE).
export function Scene() {
  const maxDpr = useAdaptiveMaxDpr();
  // Ajan Ofisi tam ekranken çekirdek görünmüyor: kare üretmeyi tamamen durdur,
  // GPU iki sahneyi birden çizmesin (Faz 0 — Aıron makineyi yormasın).
  const officeOpen = useNavigationStore((state) => state.activeModule === 'agents');

  return (
    <Canvas
      frameloop={officeOpen ? 'never' : 'always'}
      camera={{ position: [0, 0, CAMERA_DISTANCE], fov: 50, near: 0.1, far: 120 }}
      dpr={[1, maxDpr]}
      gl={{ antialias: true, alpha: false }}
    >
      {/* Zemin, CSS'teki --background ile birebir aynı (#05070c) — sahnenin
          kenarı ile HTML katmanı arasında görünür bir dikiş kalmasın diye. */}
      <color attach="background" args={['#05070c']} />
      <fog attach="fog" args={['#05070c', 15, 44]} />

      <Lighting />
      <Background />
      <CameraRig />
      <EnergyCore />
      <EnergyTendrils />
      <ElectricArcs />
      <NodeConnections />
      <OrbitNodes />
      <PostProcessing />
      {/* Kare süresi sondası — `window.__aironFps()` ile okunuyor. Kare başına
          tek bir dizi yazması; sahneyi görsel olarak etkilemiyor. */}
      <FrameProbe />

      <Suspense fallback={null}>
        <Environment preset="night" environmentIntensity={0.25} />
      </Suspense>
    </Canvas>
  );
}
