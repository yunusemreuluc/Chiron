'use client';

import { memo, useEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Grid, OrthographicCamera, QuadraticBezierLine, Sparkles } from '@react-three/drei';
import { Bloom, EffectComposer } from '@react-three/postprocessing';
import * as THREE from 'three';
import { isActive, useOfficeStore, type WorkerSummary } from '@/stores/officeStore';
import { CHIEF_ID, deskPosition } from './layout';
import { OfficeDesk } from './OfficeDesk';

// Ajan Ofisi sahnesi — izometrik hologram ofis (plan § A.3).
//
// Ana sahneden (three/Scene.tsx) AYRI bir Canvas: ofis açıkken ana sahnenin
// frameloop'u durduruluyor (bkz. Scene.tsx), yani GPU aynı anda iki sahne
// çizmiyor. Ortografik kamera: izometride uzaklık bozulması olmasın, masalar
// eşit boyda okunsun.

const ISO_POSITION = new THREE.Vector3(13, 12, 13);

function IsoCamera() {
  // Yakınlık pencereye göre: ofisin tamamı her boyutta kadraja sığsın.
  const size = useThree((s) => s.size);
  return (
    <OrthographicCamera
      makeDefault
      position={ISO_POSITION.toArray()}
      zoom={Math.min(size.width, size.height) / 15.5}
      near={0.1}
      far={100}
    />
  );
}

const driftTarget = new THREE.Vector3();

function CameraDrift() {
  // Fareyle hafif kayma — parallax derinliği (Tasarım Kuralları § Hareket).
  // Abartı yok: en fazla ~0.8 birim. Kamera `state`ten alınır (CameraRig ile aynı desen).
  useFrame((state, delta) => {
    const { camera, pointer } = state;
    driftTarget.set(pointer.x * 0.8, pointer.y * 0.4, -pointer.x * 0.8).add(ISO_POSITION);
    camera.position.x = THREE.MathUtils.damp(camera.position.x, driftTarget.x, 2, delta);
    camera.position.y = THREE.MathUtils.damp(camera.position.y, driftTarget.y, 2, delta);
    camera.position.z = THREE.MathUtils.damp(camera.position.z, driftTarget.z, 2, delta);
    camera.lookAt(0, 0.6, 0);
  });
  return null;
}

function deskOf(workerId: string, byId: Map<string, WorkerSummary>): string {
  if (workerId.startsWith('claude:')) return CHIEF_ID;
  return byId.get(workerId)?.desk ?? CHIEF_ID;
}

function arcMid(from: THREE.Vector3, to: THREE.Vector3, lift = 2.4): THREE.Vector3 {
  return from.clone().lerp(to, 0.5).setY(lift);
}

interface Beam {
  key: string;
  from: THREE.Vector3;
  to: THREE.Vector3;
  color: string;
  born: number;
}

const BEAM_SECONDS = 1.3;

function BeamPulse({ beam, onDone }: { beam: Beam; onDone: (key: string) => void }) {
  const mesh = useRef<THREE.Mesh>(null);
  const curve = useMemo(
    () => new THREE.QuadraticBezierCurve3(beam.from, arcMid(beam.from, beam.to, 3), beam.to),
    [beam],
  );
  useFrame((state) => {
    const t = (state.clock.elapsedTime - beam.born) / BEAM_SECONDS;
    if (t >= 1) {
      onDone(beam.key);
      return;
    }
    if (!mesh.current) return;
    // ease-out-quint — ışık çıkışta hızlı, varışta yumuşak.
    const e = 1 - Math.pow(1 - Math.max(0, t), 5);
    mesh.current.position.copy(curve.getPoint(e));
    const s = 0.12 + 0.1 * Math.sin(t * Math.PI);
    mesh.current.scale.setScalar(s / 0.12);
  });
  return (
    <mesh ref={mesh} position={beam.from}>
      <sphereGeometry args={[0.12, 16, 16]} />
      <meshBasicMaterial color={beam.color} toneMapped={false} />
    </mesh>
  );
}

/**
 * İş devri ışınları: şef bir işi bir masaya verince ışık oradan oraya uçar;
 * iş bitince sonuç yeşil bir ışıkla geri döner. Yalnız ofis AÇIKKEN olan
 * devirler çizilir — açılışta geçmiş devirlerin hepsi birden uçuşmasın.
 */
function HandoffBeams() {
  const clock = useThree((s) => s.clock);
  const [beams, setBeams] = useState<Beam[]>([]);

  useEffect(() => {
    // Açılış anındaki işçiler "zaten görülmüş" sayılır — geçmiş devirler uçuşmasın.
    const seen = new Map((useOfficeStore.getState().snapshot?.workers ?? []).map((w) => [w.id, w.status]));
    return useOfficeStore.subscribe((state, prevState) => {
      if (state.snapshot === prevState.snapshot) return;
      const fresh = diffBeams(state.snapshot?.workers ?? [], seen, clock.elapsedTime);
      if (fresh.length) setBeams((b) => [...b, ...fresh].slice(-24));
    });
  }, [clock]);

  return (
    <>
      {beams.map((beam) => (
        <BeamPulse key={beam.key} beam={beam} onDone={(k) => setBeams((b) => b.filter((x) => x.key !== k))} />
      ))}
    </>
  );
}

function diffBeams(workers: WorkerSummary[], seen: Map<string, string>, now: number): Beam[] {
  const byId = new Map(workers.map((w) => [w.id, w]));
  const fresh: Beam[] = [];
  {
    for (const w of workers) {
      if (w.kind === 'chief') continue;
      const prev = seen.get(w.id);
      const from = new THREE.Vector3(...deskPosition(deskOf(w.given_by, byId))).setY(1.2);
      const to = new THREE.Vector3(...deskPosition(w.desk)).setY(1.2);
      if (prev === undefined) {
        fresh.push({ key: `${w.id}:out`, from, to, color: '#a9cbff', born: now });
      } else if (isActive(prev as WorkerSummary['status']) && (w.status === 'bitti' || w.status === 'hata')) {
        fresh.push({
          key: `${w.id}:back`,
          from: to,
          to: from,
          color: w.status === 'bitti' ? '#7ee0b5' : '#ff5d6c',
          born: now,
        });
      }
      seen.set(w.id, w.status);
    }
  }
  return fresh;
}

/** Şu an süren her devir için şef masasından iş alan masaya kesik, akan bir yay. */
function DelegationLinks({ workers }: { workers: WorkerSummary[] }) {
  const links = useMemo(() => {
    const byId = new Map(workers.map((w) => [w.id, w]));
    const seen = new Set<string>();
    const out: { key: string; from: THREE.Vector3; to: THREE.Vector3; color: string }[] = [];
    for (const w of workers) {
      if (w.kind === 'chief' || !isActive(w.status)) continue;
      const fromDesk = deskOf(w.given_by, byId);
      if (fromDesk === w.desk) continue;
      const key = `${fromDesk}->${w.desk}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({
        key,
        from: new THREE.Vector3(...deskPosition(fromDesk)).setY(0.04),
        to: new THREE.Vector3(...deskPosition(w.desk)).setY(0.04),
        color: w.status === 'onay_bekliyor' ? '#ffb020' : '#7fb2ff',
      });
    }
    return out;
  }, [workers]);

  return (
    <>
      {links.map(({ key, from, to, color }) => (
        <FlowingLink key={key} from={from} to={to} color={color} />
      ))}
    </>
  );
}

function FlowingLink({ from, to, color }: { from: THREE.Vector3; to: THREE.Vector3; color: string }) {
  const ref = useRef<{ material: { dashOffset: number } } | null>(null);
  const mid = useMemo(() => arcMid(from, to, 1.6), [from, to]);
  useFrame((_, delta) => {
    if (ref.current) ref.current.material.dashOffset -= delta * 0.9;
  });
  return (
    <QuadraticBezierLine
      // drei'nin Line2 tipi burada gereksiz ayrıntı; yalnız dashOffset'e dokunuluyor.
      ref={ref as never}
      start={from}
      end={to}
      mid={mid}
      color={color}
      lineWidth={1.4}
      dashed
      dashScale={6}
      dashSize={0.5}
      gapSize={0.6}
      transparent
      opacity={0.75}
    />
  );
}

function Floor() {
  return (
    <>
      <mesh rotation-x={-Math.PI / 2} position-y={-0.01}>
        <circleGeometry args={[9.5, 96]} />
        <meshStandardMaterial color="#070b13" metalness={0.7} roughness={0.45} />
      </mesh>
      <Grid
        position={[0, 0, 0]}
        args={[24, 24]}
        cellSize={0.6}
        cellThickness={0.6}
        cellColor="#14233d"
        sectionSize={3}
        sectionThickness={1}
        sectionColor="#24426e"
        fadeDistance={22}
        fadeStrength={1.6}
        infiniteGrid
      />
      <mesh rotation-x={-Math.PI / 2} position-y={0.004}>
        <ringGeometry args={[9.35, 9.5, 128]} />
        <meshBasicMaterial color="#7fb2ff" transparent opacity={0.22} toneMapped={false} />
      </mesh>
    </>
  );
}

const SPARKLE_SCALE: [number, number, number] = [18, 5, 18];
const SPARKLE_POSITION: [number, number, number] = [0, 2.5, 0];
const FOG_ARGS: [string, number, number] = ['#05070c', 22, 40];
const NO_WORKERS: WorkerSummary[] = [];

/**
 * Sahnenin hiç değişmeyen kısmı: ışık, zemin, toz, bloom. `memo` + prop yok =
 * anlık görüntü her geldiğinde yeniden render EDİLMEZ.
 *
 * Neden önemli (2026-10-02): EffectComposer çocukları her ebeveyn render'ında
 * yeni kimlikle geldiği için efekt geçişlerini söküp yeniden kuruyor; ofis
 * sahnesi bir masa seçilince ya da bir olay gelince tamamen siyaha düşüyordu.
 * Ayrıca saniyede bir gelen güncellemede zemini/ışığı yeniden kurmak israf.
 */
const StaticStage = memo(function StaticStage() {
  return (
    <>
      <color attach="background" args={['#05070c']} />
      <fog attach="fog" args={FOG_ARGS} />
      <IsoCamera />
      <CameraDrift />

      <ambientLight intensity={0.35} color="#9fb8e0" />
      <directionalLight position={[6, 12, 4]} intensity={0.7} color="#cfe0ff" />
      <pointLight position={[0, 4, 0]} intensity={14} distance={14} color="#7fb2ff" />

      <Floor />
      <Sparkles count={70} scale={SPARKLE_SCALE} position={SPARKLE_POSITION} size={2.2} speed={0.25} opacity={0.35} color="#a9cbff" />

      <EffectComposer multisampling={0}>
        <Bloom mipmapBlur luminanceThreshold={0.35} luminanceSmoothing={0.2} intensity={0.85} radius={0.7} />
      </EffectComposer>
    </>
  );
});

/** Değişen kısım: masalar, devir yayları, ışınlar — yalnız anlık görüntüye bağlı. */
function LiveOffice() {
  const snapshot = useOfficeStore((s) => s.snapshot);
  const selectDesk = useOfficeStore((s) => s.selectDesk);

  const desks = snapshot?.desks ?? [];
  const workers = useMemo(() => snapshot?.workers ?? NO_WORKERS, [snapshot]);
  const activeByDesk = useMemo(() => {
    const map = new Map<string, WorkerSummary[]>();
    for (const w of workers) {
      if (!isActive(w.status)) continue;
      map.set(w.desk, [...(map.get(w.desk) ?? []), w]);
    }
    return map;
  }, [workers]);

  return (
    <>
      {desks.map((desk) => (
        <OfficeDesk
          key={desk.id}
          desk={desk}
          workers={activeByDesk.get(desk.id) ?? NO_WORKERS}
          position={deskPosition(desk.id)}
          onSelect={selectDesk}
        />
      ))}
      <DelegationLinks workers={workers} />
      <HandoffBeams />
    </>
  );
}

export function OfficeScene({ paused = false }: { paused?: boolean }) {
  const selectDesk = useOfficeStore((s) => s.selectDesk);
  return (
    <Canvas
      frameloop={paused ? 'never' : 'always'}
      dpr={[1, 1.5]}
      gl={{ antialias: true, alpha: false }}
      onPointerMissed={() => selectDesk(null)}
    >
      <StaticStage />
      <LiveOffice />
    </Canvas>
  );
}
