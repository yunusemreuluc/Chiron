'use client';

import { useMemo, useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { Html, RoundedBox } from '@react-three/drei';
import * as THREE from 'three';
import type { Desk, WorkerStatus, WorkerSummary } from '@/stores/officeStore';
import { STATUS_LABEL, useOfficeStore } from '@/stores/officeStore';
import { CHIEF_ID, STATUS_COLOR } from './layout';

// Bir masa: zemin halkası (durum), cam masa, hologram ekran ve ajan figürü.
//
// Durum dili (plan § A.3): çalışıyor → ekran akar, figür nefes alır, halka
// hızlı nabız; onay bekliyor → kehribar nabız; boşta → soluk; masada kimse
// yoksa figür yerine silik bir hayalet kalır. Renkler masanın kimliği; durum
// rengi yalnızca onay/hata gibi dikkat isteyen hallerde onu bastırır.

const SCREEN_VERTEX = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

// "Kod akan" hologram ekran: kayan satırlar + tarama çizgisi. Doku yok, tek
// küçük shader — 7 masa için maliyeti ihmal edilebilir.
const SCREEN_FRAGMENT = /* glsl */ `
  uniform float uTime;
  uniform float uActivity;
  uniform vec3 uColor;
  varying vec2 vUv;
  float hash(float n) { return fract(sin(n) * 43758.5453); }
  void main() {
    float rows = 14.0;
    float y = vUv.y * rows + uTime * 1.6 * uActivity;
    float row = floor(y);
    float lineLen = 0.25 + 0.65 * hash(row * 3.17);
    float indent = 0.06 + 0.18 * step(0.6, hash(row * 7.31));
    float inLine = step(indent, vUv.x) * step(vUv.x, indent + lineLen * 0.8);
    float thickness = smoothstep(0.15, 0.3, fract(y)) * smoothstep(0.75, 0.6, fract(y));
    float text = inLine * thickness * (0.35 + 0.65 * hash(row + 0.5));
    float scan = smoothstep(0.0, 0.02, abs(fract(vUv.y - uTime * 0.35) - 0.5)) ;
    float edge = smoothstep(0.0, 0.04, vUv.x) * smoothstep(1.0, 0.96, vUv.x)
               * smoothstep(0.0, 0.05, vUv.y) * smoothstep(1.0, 0.95, vUv.y);
    float base = 0.08 + 0.05 * uActivity;
    float a = (base + text * (0.25 + 0.75 * uActivity)) * edge;
    a *= mix(1.0, 0.75 + 0.25 * scan, uActivity);
    gl_FragColor = vec4(uColor * (0.6 + 1.4 * text * uActivity), a);
  }
`;

interface OfficeDeskProps {
  desk: Desk;
  workers: WorkerSummary[];
  position: [number, number, number];
  onSelect: (id: string) => void;
}

// Masa kimliğinden sabit bir faz: masalar aynı anda nefes almasın ama her
// render'da da değişmesin (Math.random render sırasında saf değil).
function seedOf(id: string): number {
  let h = 2166136261;
  for (let i = 0; i < id.length; i += 1) h = Math.imul(h ^ id.charCodeAt(i), 16777619);
  return ((h >>> 0) % 1000) / 1000;
}

function createScreenUniforms(color: string, seed: number) {
  return {
    uTime: { value: seed * 10 },
    uActivity: { value: 0 },
    uColor: { value: new THREE.Color(color) },
  };
}

function statusTint(desk: Desk): THREE.Color {
  const override = STATUS_COLOR[desk.status as keyof typeof STATUS_COLOR];
  return new THREE.Color(override ?? desk.color);
}

export function OfficeDesk({ desk, workers, position, onSelect }: OfficeDeskProps) {
  // Seçim masanın kendisinde okunur: seçim değişince yalnız iki masa yeniden çizilir.
  const selected = useOfficeStore((s) => s.selectedDesk === desk.id);
  const [hovered, setHovered] = useState(false);
  const chief = desk.id === CHIEF_ID;
  const scale = chief ? 1.25 : 1;
  const status: WorkerStatus = desk.status;
  const occupied = workers.length > 0;
  const working = status === 'calisiyor';
  const waiting = status === 'onay_bekliyor';

  const baseColor = useMemo(() => new THREE.Color(desk.color), [desk.color]);
  const tint = useMemo(() => statusTint(desk), [desk]);

  const ringMat = useRef<THREE.MeshBasicMaterial>(null);
  const figure = useRef<THREE.Group>(null);
  const figureMat = useRef<THREE.MeshStandardMaterial>(null);
  const screenMat = useRef<THREE.ShaderMaterial>(null);
  const seed = seedOf(desk.id);
  const phase = seed * Math.PI * 2;
  const initialUniforms = useMemo(() => createScreenUniforms(desk.color, seed), [desk.color, seed]);
  // Durum geçişleri anlık değil, yumuşak (Tasarım Kuralları § Animasyon).
  const activity = useRef(0);

  useFrame((state, delta) => {
    const t = state.clock.elapsedTime;
    const target = working ? 1 : waiting ? 0.55 : occupied ? 0.22 : 0.05;
    activity.current = THREE.MathUtils.damp(activity.current, target, 3, delta);
    const a = activity.current;

    const screen = screenMat.current;
    if (screen) {
      screen.uniforms.uTime.value += delta;
      screen.uniforms.uActivity.value = a;
      screen.uniforms.uColor.value.copy(waiting ? tint : baseColor);
    }

    if (ringMat.current) {
      const speed = working ? 3.2 : waiting ? 5 : 1.2;
      const pulse = 0.5 + 0.5 * Math.sin(t * speed + phase);
      const emphasis = (hovered ? 0.25 : 0) + (selected ? 0.35 : 0);
      ringMat.current.opacity = Math.min(1, 0.12 + a * (0.35 + 0.4 * pulse) + emphasis);
      ringMat.current.color.copy(tint);
    }
    if (figure.current) {
      // Nefes: çalışırken hızlı ve belirgin, boştayken yavaş ve sığ.
      const bob = Math.sin(t * (working ? 2.6 : 1.1) + phase) * (working ? 0.05 : 0.025);
      figure.current.position.y = 0.02 + bob;
      figure.current.rotation.y = Math.sin(t * 0.4 + phase) * 0.12;
    }
    if (figureMat.current) {
      figureMat.current.emissiveIntensity = occupied ? 0.45 + a * 1.1 : 0.08;
      figureMat.current.opacity = occupied ? 0.92 : 0.16;
    }
  });

  const extra = desk.id === 'subagents' ? Math.min(workers.length, 4) : 0;
  const headline = workers.find((w) => w.status === 'onay_bekliyor') ?? workers.find((w) => w.status === 'calisiyor') ?? workers[0];

  return (
    <group
      position={position}
      scale={scale}
      // Her masa izometrik kameraya döner: yerel +z = kameranın yönü (+x+z).
      rotation-y={Math.PI / 4}
      onPointerOver={(e) => {
        e.stopPropagation();
        setHovered(true);
        document.body.style.cursor = 'pointer';
      }}
      onPointerOut={() => {
        setHovered(false);
        document.body.style.cursor = '';
      }}
      onClick={(e) => {
        e.stopPropagation();
        onSelect(desk.id);
      }}
    >
      {/* Zemin plakası + durum halkası */}
      <mesh rotation-x={-Math.PI / 2} position-y={0.005}>
        <circleGeometry args={[1.55, 64]} />
        <meshStandardMaterial color="#0b111c" metalness={0.6} roughness={0.35} transparent opacity={0.9} />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position-y={0.012}>
        <ringGeometry args={[1.48, 1.56, 96]} />
        <meshBasicMaterial ref={ringMat} transparent toneMapped={false} depthWrite={false} />
      </mesh>
      {chief && (
        <mesh rotation-x={-Math.PI / 2} position-y={0.011}>
          <ringGeometry args={[1.7, 1.72, 96]} />
          <meshBasicMaterial color={desk.color} transparent opacity={0.25} toneMapped={false} />
        </mesh>
      )}

      {/* Cam masa — ayaksız, havada asılı bir levha (hologram ofis dili) */}
      <RoundedBox args={[1.5, 0.06, 0.72]} radius={0.03} position={[0, 0.72, -0.12]}>
        <meshPhysicalMaterial
          color="#16233a"
          metalness={0.2}
          roughness={0.15}
          transparent
          opacity={0.55}
          emissive={desk.color}
          emissiveIntensity={0.06}
        />
      </RoundedBox>
      <mesh position={[0, 0.36, -0.12]}>
        <boxGeometry args={[0.05, 0.72, 0.05]} />
        <meshBasicMaterial color={desk.color} transparent opacity={0.18} />
      </mesh>

      {/* Hologram ekran */}
      <mesh position={[0, 1.42, -0.42]} rotation-x={-0.08}>
        <planeGeometry args={[1.1, 0.62]} />
        <shaderMaterial
          ref={screenMat}
          vertexShader={SCREEN_VERTEX}
          fragmentShader={SCREEN_FRAGMENT}
          uniforms={initialUniforms}
          transparent
          depthWrite={false}
          side={THREE.DoubleSide}
          toneMapped={false}
        />
      </mesh>

      {/* Ajan figürü — masanın önünde, sırtı kameraya; ekran başının üstünden görünür */}
      <group ref={figure} position={[0, 0, 0.48]}>
        <mesh position-y={0.62}>
          <capsuleGeometry args={[0.2, 0.42, 6, 16]} />
          <meshStandardMaterial
            ref={figureMat}
            color={desk.color}
            emissive={desk.color}
            transparent
            roughness={0.3}
            metalness={0.1}
          />
        </mesh>
        <mesh position-y={1.12}>
          <sphereGeometry args={[0.16, 24, 24]} />
          <meshStandardMaterial
            color={desk.color}
            emissive={desk.color}
            emissiveIntensity={occupied ? 0.9 : 0.1}
            transparent
            opacity={occupied ? 0.95 : 0.16}
          />
        </mesh>
      </group>

      {/* Alt ajan havuzu: aynı anda çalışan her alt ajan için küçük bir figür */}
      {Array.from({ length: Math.max(0, extra - 1) }, (_, i) => {
        const angle = Math.PI * 0.9 + i * 0.6;
        return (
          <mesh key={i} position={[Math.cos(angle) * 1.05, 0.5, Math.sin(angle) * 1.05]}>
            <capsuleGeometry args={[0.12, 0.26, 4, 12]} />
            <meshStandardMaterial
              color={desk.color}
              emissive={desk.color}
              emissiveIntensity={0.9}
              transparent
              opacity={0.85}
            />
          </mesh>
        );
      })}

      {/* Etiket — ad, durum ve o anki tek satır */}
      <Html position={[0, chief ? 2.05 : 1.95, 0]} center zIndexRange={[20, 0]} style={{ pointerEvents: 'none' }}>
        <div className={`office-tag ${selected ? 'office-tag--selected' : ''}`} style={{ ['--desk' as string]: desk.color }}>
          <div className="office-tag__row">
            <span className={`office-dot office-dot--${status}`} />
            <span className="office-tag__name">{desk.name}</span>
            {workers.length > 1 && <span className="office-tag__count">×{workers.length}</span>}
          </div>
          <div className="office-tag__status">{occupied ? STATUS_LABEL[status] : 'Masa boş'}</div>
          {headline && (working || waiting) && headline.current && (
            <div className="office-tag__bubble">{headline.current}</div>
          )}
        </div>
      </Html>
    </group>
  );
}
