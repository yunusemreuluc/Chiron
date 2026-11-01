'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import { useAIStateStore } from '@/stores/aiStateStore';
import { humanoidProgress, useHumanoidStore } from '@/stores/humanoidStore';
import { useMicStore } from '@/stores/micStore';
import { EYE_Y, NECK_PIVOT_Y, loadKromGeometry } from './humanoidKrom';
import { HUMANOID_FRAGMENT_SHADER, HUMANOID_VERTEX_SHADER } from './shaders/humanoid';

// İnsan görünümü (2026-11-01, kullanıcı isteği — Instagram'daki "Humanoid view"
// referansı). Çift şıklatınca çekirdek bir parçacık sürüsüne çözülüyor, parçacıklar
// aşağıdan yukarı "Krom" insansı robota toplanıyor (2026-11-02: elips büst yerine
// gerçek kafa taraması — bkz. three/humanoidKrom.ts). Büst canlı: kafa imleci
// izliyor, gözler kırpıyor, Chiron konuşurken çene açılıp gözler ve dikişler
// parlıyor, dinlerken mikrofon seviyesine tepki veriyor.

/** Açılış süresi (s). Kapanış daha kısa: geri çekilmek beklemekten hızlı hissettirmeli. */
const OPEN_SECONDS = 3.0;
const CLOSE_SECONDS = 1.8;
/** Tarama birimleri (y −4..4) sahneye: kadrajı göğüsten kesik dolduruyor. */
const BUST_SCALE = 0.8;
const BUST_OFFSET_Y = -0.35;
const DAMPING = 3;
const MAX_YAW = 0.6;
const MAX_PITCH = 0.28;
const BLINK_SECONDS = 0.18;

// Krom paleti: gümüş gövde, mavi dikiş, buz mavisi gözler, turuncu göğüs çekirdeği.
const PALETTE = ['#c9d6e6', '#4aa3ff', '#bfefff', '#ff9a3d'].map((hex) => new THREE.Color(hex));

export function HumanoidBust() {
  const rootRef = useRef<THREE.Group>(null);
  // Uniform'lar materyal üzerinden yazılıyor; parlama geçişi aynı nesneleri paylaştığı için o da güncelleniyor.
  const materialRef = useRef<THREE.ShaderMaterial>(null);
  const pointer = useRef({ x: 0, y: 0, movedAt: -1e9 });
  const look = useRef({ yaw: 0, pitch: 0, speak: 0, listen: 0, blinkIn: 3 });
  const pixelRatio = useThree((state) => state.viewport.dpr);
  const [geometry, setGeometry] = useState<THREE.BufferGeometry | null>(null);

  // Tarama yalnızca mod ilk kez açılınca indiriliyor — Chiron'un açılışı yavaşlamasın.
  const active = useHumanoidStore((state) => state.active);
  useEffect(() => {
    if (!active || geometry) return;
    let cancelled = false;
    loadKromGeometry()
      .then((geo) => {
        if (!cancelled) setGeometry(geo);
      })
      .catch((error) => console.error('[Chiron] İnsan görünümü taraması yüklenemedi', error));
    return () => {
      cancelled = true;
    };
  }, [active, geometry]);

  // HUD bu modda pointer-events-none — imleci tuvalden değil pencereden oku.
  useEffect(() => {
    const onMove = (event: PointerEvent) => {
      pointer.current.x = (event.clientX / window.innerWidth) * 2 - 1;
      pointer.current.y = -((event.clientY / window.innerHeight) * 2 - 1);
      pointer.current.movedAt = performance.now();
    };
    window.addEventListener('pointermove', onMove, { passive: true });
    return () => window.removeEventListener('pointermove', onMove);
  }, []);

  // Normal geçiş ile parlama geçişi aynı uniform nesnelerini paylaşıyor; yalnız uHalo ayrı.
  const [uniforms, haloUniforms] = useMemo(() => {
    const shared = {
      uTime: { value: 0 },
      uMorph: { value: 0 },
      uSpeak: { value: 0 },
      uListen: { value: 0 },
      uYaw: { value: 0 },
      uPitch: { value: 0 },
      uBlink: { value: 0 },
      uPivotY: { value: NECK_PIVOT_Y },
      uEyeY: { value: EYE_Y },
      uSize: { value: 2.2 },
      uMaxSize: { value: 6 },
      uPixelRatio: { value: 1 },
      uC0: { value: PALETTE[0] },
      uC1: { value: PALETTE[1] },
      uC2: { value: PALETTE[2] },
      uC3: { value: PALETTE[3] },
    };
    return [
      { ...shared, uHalo: { value: 0 } },
      { ...shared, uHalo: { value: 1 } },
    ];
  }, []);

  useFrame((state, delta) => {
    const root = rootRef.current;
    if (!root) return;
    const material = materialRef.current;

    // Sabit hızlı rampa + shader'daki smoothstep: üstel sönüm burada sonlara
    // doğru sürünürdü, dönüşüm "bitti mi bitmedi mi" diye asılı kalırdı.
    // Tarama henüz gelmediyse rampa bekliyor: çekirdek sönüp boşluk kalmasın.
    const isActive = useHumanoidStore.getState().active;
    const dt = Math.min(delta, 0.05);
    const step = dt / (isActive ? OPEN_SECONDS : CLOSE_SECONDS);
    const goingUp = isActive && geometry !== null;
    const morph = THREE.MathUtils.clamp(humanoidProgress.value + (goingUp ? step : -step), 0, 1);
    humanoidProgress.value = morph;
    root.visible = morph > 0.001;
    if (!root.visible) return;

    const t = state.clock.elapsedTime;
    const l = look.current;
    const aiState = useAIStateStore.getState().aiState;
    const levels = useMicStore.getState().levels;
    l.speak = THREE.MathUtils.damp(l.speak, aiState === 'speaking' ? 1 : 0, DAMPING, delta);
    l.listen = THREE.MathUtils.damp(l.listen, Math.min(1, levels[levels.length - 1] * 2.5), 8, delta);

    // İmleç 4 sn kıpırdamazsa kafa kendi kendine hafifçe salınıyor — donmuş bir heykel değil.
    // Pitch işareti: imleç aşağıdaysa (pointer.y < 0) pozitif → shader'da yüz aşağı bakıyor.
    const idle = performance.now() - pointer.current.movedAt > 4000;
    const targetYaw = idle ? Math.sin(t * 0.25) * 0.22 : pointer.current.x * MAX_YAW;
    const targetPitch = idle ? Math.sin(t * 0.18) * 0.05 : -pointer.current.y * MAX_PITCH;
    l.yaw = THREE.MathUtils.damp(l.yaw, targetYaw, DAMPING, delta);
    l.pitch = THREE.MathUtils.damp(l.pitch, targetPitch, DAMPING, delta);

    // Göz kırpma: 2.5–6.5 sn arayla, 0.18 sn süren bir kapanıp açılma.
    l.blinkIn -= dt;
    if (l.blinkIn < -BLINK_SECONDS) l.blinkIn = 2.5 + Math.random() * 4;
    const blink = l.blinkIn < 0 ? Math.sin((-l.blinkIn / BLINK_SECONDS) * Math.PI) : 0;

    if (!material) return;
    const u = material.uniforms;
    u.uTime.value = t;
    u.uMorph.value = morph;
    u.uSpeak.value = l.speak;
    u.uListen.value = l.listen;
    u.uYaw.value = l.yaw;
    u.uPitch.value = l.pitch;
    u.uBlink.value = blink;
    u.uPixelRatio.value = pixelRatio;
  });

  return (
    <group ref={rootRef} visible={false} position={[0, BUST_OFFSET_Y, 0]} scale={BUST_SCALE}>
      {geometry ? (
        <>
          <points geometry={geometry} frustumCulled={false}>
            <shaderMaterial
              uniforms={haloUniforms}
              vertexShader={HUMANOID_VERTEX_SHADER}
              fragmentShader={HUMANOID_FRAGMENT_SHADER}
              transparent
              depthWrite={false}
              blending={THREE.AdditiveBlending}
            />
          </points>
          <points geometry={geometry} frustumCulled={false}>
            <shaderMaterial
              ref={materialRef}
              uniforms={uniforms}
              vertexShader={HUMANOID_VERTEX_SHADER}
              fragmentShader={HUMANOID_FRAGMENT_SHADER}
              transparent
              depthWrite={false}
              blending={THREE.AdditiveBlending}
            />
          </points>
        </>
      ) : null}
    </group>
  );
}
