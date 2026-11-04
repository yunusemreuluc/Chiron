'use client';

import { useEffect, useMemo, useRef } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import { ENERGY_CORE_VERTEX_SHADER } from '@/three/shaders/energyCore';
import { WIRE_CORE_FRAGMENT_SHADER } from '@/three/shaders/wireCore';
import { SessionOrbits } from '@/three/SessionOrbits';

// Gözetim'in orta paneli: ana sahnenin küçük bir kopyası — ortada Chiron, etrafında oturumlar.
// Ofis açıkken ana sahne durduğu için (Scene.tsx frameloop) aynı anda tek WebGL sahnesi çizilir.
// Ortadaki çekirdek EnergyCore DEĞİL: o bileşenin tıklaması Chiron'u uyutuyor ve açılış
// sahnelemesi var; burada yalnız aynı tel kafes dilinde sakin bir işaret lazım.

const FPS = 30;

function Governor() {
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    const id = setInterval(() => invalidate(), 1000 / FPS);
    return () => clearInterval(id);
  }, [invalidate]);
  return null;
}

function shell(colorA: string, colorB: string, rim: string, opacity: number) {
  return {
    uTime: { value: 0 },
    uDistortion: { value: 0.1 },
    uIntensity: { value: 1 },
    uOpacity: { value: opacity },
    uColorA: { value: new THREE.Color(colorA) },
    uColorB: { value: new THREE.Color(colorB) },
    uRimColor: { value: new THREE.Color(rim) },
  };
}

function CenterCore() {
  const outer = useRef<THREE.Mesh>(null);
  const inner = useRef<THREE.Mesh>(null);
  const outerMat = useRef<THREE.ShaderMaterial>(null);
  const innerMat = useRef<THREE.ShaderMaterial>(null);
  const uOuter = useMemo(() => shell('#3f6db8', '#7fb2ff', '#e8eef7', 0.36), []);
  const uInner = useMemo(() => shell('#3f6db8', '#7fb2ff', '#e8eef7', 0.75), []);
  useFrame((state, delta) => {
    const t = state.clock.elapsedTime;
    const breath = 1 + Math.sin(t * 0.7) * 0.2;
    for (const mat of [outerMat.current, innerMat.current]) {
      if (!mat) continue;
      mat.uniforms.uTime.value = t;
      mat.uniforms.uIntensity.value = breath;
    }
    if (outer.current) outer.current.rotation.y += delta * 0.05;
    if (inner.current) inner.current.rotation.y -= delta * 0.17;
  });
  return (
    <group>
      <mesh ref={outer}>
        <icosahedronGeometry args={[1.25, 1]} />
        <shaderMaterial ref={outerMat} uniforms={uOuter} vertexShader={ENERGY_CORE_VERTEX_SHADER} fragmentShader={WIRE_CORE_FRAGMENT_SHADER}
          wireframe transparent depthWrite={false} side={THREE.DoubleSide} blending={THREE.AdditiveBlending} />
      </mesh>
      <mesh ref={inner} rotation={[-0.32, 0, -0.16]}>
        <icosahedronGeometry args={[0.48, 3]} />
        <shaderMaterial ref={innerMat} uniforms={uInner} vertexShader={ENERGY_CORE_VERTEX_SHADER} fragmentShader={WIRE_CORE_FRAGMENT_SHADER}
          wireframe transparent depthWrite={false} side={THREE.DoubleSide} blending={THREE.AdditiveBlending} />
      </mesh>
    </group>
  );
}

// Yıldız alanı (2026-11-04, kullanıcı isteği: "arka planı siyah, küçük küçük yıldızlar olsun").
// İki katman: çok sayıda sönük toz + az sayıda parlak yıldız. Kabuk yarıçapı kameradan uzak (18–34) —
// döndürürken yıldızlar sahnenin "arkasında" kalsın, çekirdeğin önüne düşmesin. Tohumlu üretim:
// her açılışta aynı gökyüzü (rastgele titreme "bir şey değişti" gibi okunur).
function seeded(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

function starLayer(count: number, seed: number, rMin: number, rMax: number) {
  const rnd = seeded(seed);
  const pos = new Float32Array(count * 3);
  const col = new Float32Array(count * 3);
  const tint = [new THREE.Color('#ffffff'), new THREE.Color('#cfe0ff'), new THREE.Color('#ffe9d6')];
  for (let i = 0; i < count; i += 1) {
    const u = rnd() * 2 - 1;
    const th = rnd() * Math.PI * 2;
    const r = rMin + rnd() * (rMax - rMin);
    const k = Math.sqrt(1 - u * u);
    pos[i * 3] = Math.cos(th) * k * r;
    pos[i * 3 + 1] = u * r;
    pos[i * 3 + 2] = Math.sin(th) * k * r;
    const c = tint[Math.floor(rnd() * tint.length)];
    const b = 0.35 + rnd() * 0.65;
    col[i * 3] = c.r * b;
    col[i * 3 + 1] = c.g * b;
    col[i * 3 + 2] = c.b * b;
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('color', new THREE.BufferAttribute(col, 3));
  return g;
}

function Stars() {
  const group = useRef<THREE.Group>(null);
  const brightMat = useRef<THREE.PointsMaterial>(null);
  const dust = useMemo(() => starLayer(1400, 7, 18, 34), []);
  const bright = useMemo(() => starLayer(160, 41, 20, 32), []);
  useEffect(
    () => () => {
      dust.dispose();
      bright.dispose();
    },
    [dust, bright],
  );
  useFrame((state, delta) => {
    // Çok yavaş kayma + parlakların hafif nabzı: gökyüzü donuk bir resim gibi durmasın.
    if (group.current) group.current.rotation.y += delta * 0.006;
    if (brightMat.current) brightMat.current.opacity = 0.75 + Math.sin(state.clock.elapsedTime * 0.8) * 0.15;
  });
  return (
    <group ref={group}>
      <points geometry={dust}>
        <pointsMaterial size={0.07} sizeAttenuation vertexColors transparent opacity={0.7} depthWrite={false} />
      </points>
      <points geometry={bright}>
        <pointsMaterial ref={brightMat} size={0.16} sizeAttenuation vertexColors transparent opacity={0.85} depthWrite={false} />
      </points>
    </group>
  );
}

export function GozetimOrbit() {
  return (
    <Canvas
      className="gz-orbit__canvas"
      frameloop="demand"
      camera={{ position: [0, 1.2, 11], fov: 46, near: 0.1, far: 80 }}
      dpr={[1, 1.25]}
      gl={{ antialias: true, alpha: false }}
    >
      <color attach="background" args={['#000000']} />
      <Governor />
      <Stars />
      <CenterCore />
      <SessionOrbits />
      {/* Fareyle döndür (kullanıcı isteği): sürükle = döndür, tekerlek = yakınlaş. Kaydırma kapalı —
          merkez hep Chiron. Dikey açı sınırlı: tam tepeden bakınca yörünge çizgiye dönüyor. */}
      <OrbitControls
        makeDefault
        enablePan={false}
        enableDamping
        dampingFactor={0.08}
        rotateSpeed={0.6}
        minDistance={6}
        maxDistance={18}
        minPolarAngle={Math.PI * 0.18}
        maxPolarAngle={Math.PI * 0.82}
      />
    </Canvas>
  );
}
