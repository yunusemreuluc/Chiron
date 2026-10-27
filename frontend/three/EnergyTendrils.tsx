'use client';

import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { useAIStateStore } from '@/stores/aiStateStore';
import { usePowerStore } from '@/stores/powerStore';
import { dampColor, SLEEP_PALETTE, STATE_PALETTE } from './palette';
import { getRevealProgress } from './reveal';
import {
  ENERGY_TENDRILS_FRAGMENT_SHADER,
  ENERGY_TENDRILS_VERTEX_SHADER,
} from './shaders/energyTendrils';

// CHIRON — çekirdekten dışa doğru yayılan ince enerji parçacıkları (kullanıcı
// isteği, 2026-07-27): "içten dışa doğru yayılan ince parçacıklar / energy
// tendrils". Deterministik sin-hash ile yön/faz üretiliyor (Math.random()
// yerine — render sırasında saf olmayan çağrı olmasın diye, bkz. Background.tsx'teki
// NebulaBackdrop'ta kullanılan aynı desen).
const PARTICLE_COUNT = 220;
const CORE_RADIUS = 1.55;
// Çekirdeğe yakın, sıkı bir "korona" — yörünge yarıçapları kısaltıldığı için
// (4.2+) parçacık bulutu da daraltıldı, düğümler bulutun içinde kalmasın diye.
const MAX_DISTANCE = 1.4;
const CYCLE_SPEED = 0.12; // döngü/sn
const POINT_SIZE = 5.0;
// Uykuda korona hem koyulaşıyor (palet) hem küçülüyor: blending toplamalı
// olduğu için koyu renk zaten görünmez hâle getiriyor, küçülme ise geriye
// kalan tozlanmayı da alıyor.
const SLEEP_POINT_SIZE = 2.2;
const REACT_DAMPING = 3;

// Açılış (kullanıcı isteği, 2026-07-31): korona artık ilk kareden itibaren tam
// güçte DEĞİL. Perde merkezden delinirken (BootOverlay, 2.7 sn) belirmeye
// başlıyor — açılan delikten önce ısı yayan parçacıklar görünüyor, çekirdeğin
// kendisi (3.4 sn) ondan sonra geliyor.
const REVEAL_DELAY = 2.5;
const REVEAL_DURATION = 1.0;

function hash(seed: number): number {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

function buildGeometry(): THREE.BufferGeometry {
  const positions = new Float32Array(PARTICLE_COUNT * 3);
  const directions = new Float32Array(PARTICLE_COUNT * 3);
  const offsets = new Float32Array(PARTICLE_COUNT);

  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const u = hash(i * 2.0 + 0.15);
    const v = hash(i * 2.0 + 0.85);
    const theta = 2 * Math.PI * u;
    const phi = Math.acos(2 * v - 1);
    const dx = Math.sin(phi) * Math.cos(theta);
    const dy = Math.sin(phi) * Math.sin(theta);
    const dz = Math.cos(phi);

    directions[i * 3] = dx;
    directions[i * 3 + 1] = dy;
    directions[i * 3 + 2] = dz;

    positions[i * 3] = dx * CORE_RADIUS;
    positions[i * 3 + 1] = dy * CORE_RADIUS;
    positions[i * 3 + 2] = dz * CORE_RADIUS;

    offsets[i] = hash(i * 3.7 + 1.31);
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('aDirection', new THREE.BufferAttribute(directions, 3));
  geometry.setAttribute('aOffset', new THREE.BufferAttribute(offsets, 1));
  return geometry;
}

export function EnergyTendrils() {
  const materialRef = useRef<THREE.ShaderMaterial>(null);
  // Açılış çarpanından BAĞIMSIZ, sönümlenen taban boyut (bkz. useFrame).
  const baseSizeRef = useRef(POINT_SIZE);
  const geometry = useMemo(() => buildGeometry(), []);

  const uniforms = {
    uTime: { value: 0 },
    uSpeed: { value: CYCLE_SPEED },
    uCoreRadius: { value: CORE_RADIUS },
    uMaxDistance: { value: MAX_DISTANCE },
    uPointSize: { value: POINT_SIZE },
    uColor: { value: new THREE.Color(STATE_PALETTE.idle.corona) },
  };

  useFrame((state, delta) => {
    const material = materialRef.current;
    if (!material) return;

    material.uniforms.uTime.value = state.clock.elapsedTime;

    // Korona çekirdeğe yapışık: rengi ONUN paletinden geliyor (three/palette.ts),
    // yoksa Chiron konuşurken yeşil bir çekirdeğin etrafında mavi bir toz bulutu
    // dönerdi.
    const isAsleep = usePowerStore.getState().powerState === 'asleep';
    const palette = isAsleep ? SLEEP_PALETTE : STATE_PALETTE[useAIStateStore.getState().aiState];
    dampColor(material.uniforms.uColor.value, palette.corona, delta);

    // Uyku sönümlemesi ile açılış AYRI tutuluyor: sönümleme kendi hedefine
    // yaklaşırken açılış onu bir çarpan olarak ölçekliyor. Tek uniform üzerinde
    // birleştirilseydi açılış sırasında sönümleme geriye doğru çalışır ve
    // korona titreyerek belirirdi.
    baseSizeRef.current = THREE.MathUtils.damp(
      baseSizeRef.current,
      isAsleep ? SLEEP_POINT_SIZE : POINT_SIZE,
      REACT_DAMPING,
      delta,
    );
    const reveal = getRevealProgress(state.clock.elapsedTime, REVEAL_DELAY, REVEAL_DURATION);
    material.uniforms.uPointSize.value = baseSizeRef.current * reveal;
  });

  return (
    <points geometry={geometry}>
      <shaderMaterial
        ref={materialRef}
        uniforms={uniforms}
        vertexShader={ENERGY_TENDRILS_VERTEX_SHADER}
        fragmentShader={ENERGY_TENDRILS_FRAGMENT_SHADER}
        transparent
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}
