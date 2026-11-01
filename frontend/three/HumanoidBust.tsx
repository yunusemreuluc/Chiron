'use client';

import { useEffect, useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import { useAIStateStore } from '@/stores/aiStateStore';
import { humanoidProgress, useHumanoidStore } from '@/stores/humanoidStore';
import { useMicStore } from '@/stores/micStore';
import { FACE_CENTER, HEAD_PIVOT_Y, buildBustGeometry, buildRangeGeometry } from './humanoidGeometry';
import {
  GLOW_FRAGMENT_SHADER,
  GLOW_VERTEX_SHADER,
  HUMANOID_FRAGMENT_SHADER,
  HUMANOID_VERTEX_SHADER,
  RANGE_VERTEX_SHADER,
} from './shaders/humanoid';

// İnsan görünümü (2026-11-01, kullanıcı isteği — Instagram'daki "Humanoid view"
// referansı): çift şıklatınca çekirdek bir parçacık kuyruklu yıldızına çözülüyor,
// parçacıklar aşağıdan yukarı kontur çizgili bir büste toplanıyor, iki yanda
// parçacık dağları yükseliyor. Büst canlı: kafa imleci izliyor, Chiron
// konuşurken konturlar dalgalanıyor ve hale halkaları nabız atıyor.

/** Açılış süresi (s). Kapanış daha kısa: geri çekilmek beklemekten hızlı hissettirmeli. */
const OPEN_SECONDS = 2.8;
const CLOSE_SECONDS = 1.8;
const BUST_OFFSET_Y = -0.55;
/** Büst kadrajı dolduruyor (referanstaki gibi göğüsten kesik). */
const BUST_SCALE = 1.12;
const DAMPING = 3;
const MAX_YAW = 0.5;
const MAX_PITCH = 0.22;

const BLUE = new THREE.Color('#2f8cff');
const ICE = new THREE.Color('#bfe6ff');
const EMBER = new THREE.Color('#ff7a1f');
const GOLD = new THREE.Color('#ffb547');

export function HumanoidBust() {
  const bustMaterial = useRef<THREE.ShaderMaterial>(null);
  const rangeMaterial = useRef<THREE.ShaderMaterial>(null);
  const glowMaterial = useRef<THREE.ShaderMaterial>(null);
  const rootRef = useRef<THREE.Group>(null);
  const headRef = useRef<THREE.Group>(null);
  const pointer = useRef({ x: 0, y: 0, movedAt: -1e9 });
  const look = useRef({ yaw: 0, pitch: 0, speak: 0, listen: 0 });
  const pixelRatio = useThree((state) => state.viewport.dpr);

  const bustGeometry = useMemo(() => buildBustGeometry(), []);
  const rangeGeometry = useMemo(() => buildRangeGeometry(), []);
  useEffect(
    () => () => {
      bustGeometry.dispose();
      rangeGeometry.dispose();
    },
    [bustGeometry, rangeGeometry],
  );

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

  const bustUniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uMorph: { value: 0 },
      uSpeak: { value: 0 },
      uListen: { value: 0 },
      uYaw: { value: 0 },
      uPitch: { value: 0 },
      uPivotY: { value: HEAD_PIVOT_Y },
      uSize: { value: 2.1 },
      uMaxSize: { value: 5 },
      uPixelRatio: { value: 1 },
      uBlue: { value: BLUE },
      uIce: { value: ICE },
      uEmber: { value: EMBER },
      uGold: { value: GOLD },
    }),
    [],
  );
  const rangeUniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uReveal: { value: 0 },
      uSize: { value: 1.9 },
      uMaxSize: { value: 4 },
      uPixelRatio: { value: 1 },
      uBlue: { value: BLUE },
      uEmber: { value: EMBER },
    }),
    [],
  );
  const glowUniforms = useMemo(
    () => ({
      uColor: { value: EMBER },
      uIntensity: { value: 0 },
      uTime: { value: 0 },
    }),
    [],
  );

  useFrame((state, delta) => {
    const bust = bustMaterial.current;
    const range = rangeMaterial.current;
    const glow = glowMaterial.current;
    const root = rootRef.current;
    if (!bust || !range || !glow || !root) return;

    // Sabit hızlı rampa + shader'daki smoothstep: üstel sönüm burada sonlara
    // doğru sürünürdü, dönüşüm "bitti mi bitmedi mi" diye asılı kalırdı.
    const active = useHumanoidStore.getState().active;
    const step = Math.min(delta, 0.05) / (active ? OPEN_SECONDS : CLOSE_SECONDS);
    const morph = THREE.MathUtils.clamp(humanoidProgress.value + (active ? step : -step), 0, 1);
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
    const idle = performance.now() - pointer.current.movedAt > 4000;
    const targetYaw = idle ? Math.sin(t * 0.25) * 0.18 : pointer.current.x * MAX_YAW;
    const targetPitch = idle ? Math.sin(t * 0.18) * 0.05 : -pointer.current.y * MAX_PITCH;
    l.yaw = THREE.MathUtils.damp(l.yaw, targetYaw, DAMPING, delta);
    l.pitch = THREE.MathUtils.damp(l.pitch, targetPitch, DAMPING, delta);

    const u = bust.uniforms;
    u.uTime.value = t;
    u.uMorph.value = morph;
    u.uSpeak.value = l.speak;
    u.uListen.value = l.listen;
    u.uYaw.value = l.yaw;
    u.uPitch.value = l.pitch;
    u.uPixelRatio.value = pixelRatio;

    range.uniforms.uTime.value = t;
    range.uniforms.uReveal.value = THREE.MathUtils.smoothstep(morph, 0.45, 1);
    range.uniforms.uPixelRatio.value = pixelRatio;

    // Yüz parıltısı kafayla birlikte dönüyor (shader'daki eksenle aynı pivot).
    const head = headRef.current;
    // Shader önce yaw sonra pitch uyguluyor: R = Rx(pitch)·Ry(yaw) → Euler 'XYZ'.
    if (head) head.rotation.set(l.pitch, l.yaw, 0, 'XYZ');
    glow.uniforms.uTime.value = t;
    glow.uniforms.uIntensity.value =
      THREE.MathUtils.smoothstep(morph, 0.7, 1) * (0.75 + 0.12 * Math.sin(t * 1.6) + l.speak * 0.4);
  });

  return (
    <group ref={rootRef} visible={false}>
      <group position={[0, BUST_OFFSET_Y, 0]} scale={BUST_SCALE}>
        <points geometry={bustGeometry} frustumCulled={false}>
          <shaderMaterial
            ref={bustMaterial}
            uniforms={bustUniforms}
            vertexShader={HUMANOID_VERTEX_SHADER}
            fragmentShader={HUMANOID_FRAGMENT_SHADER}
            transparent
            depthWrite={false}
            blending={THREE.AdditiveBlending}
          />
        </points>
        <group ref={headRef} position={[0, HEAD_PIVOT_Y, 0]}>
          <mesh position={[FACE_CENTER.x, FACE_CENTER.y - HEAD_PIVOT_Y, FACE_CENTER.z - 0.25]}>
            <planeGeometry args={[2.3, 2.5]} />
            <shaderMaterial
              ref={glowMaterial}
              uniforms={glowUniforms}
              vertexShader={GLOW_VERTEX_SHADER}
              fragmentShader={GLOW_FRAGMENT_SHADER}
              transparent
              depthWrite={false}
              blending={THREE.AdditiveBlending}
            />
          </mesh>
        </group>
      </group>
      <points geometry={rangeGeometry} frustumCulled={false}>
        <shaderMaterial
          ref={rangeMaterial}
          uniforms={rangeUniforms}
          vertexShader={RANGE_VERTEX_SHADER}
          fragmentShader={HUMANOID_FRAGMENT_SHADER}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
    </group>
  );
}
