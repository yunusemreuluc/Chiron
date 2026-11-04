'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import * as THREE from 'three';
import { fetchOfficeState } from '@/services/officeApi';
import { CAT_COLOR, hueMap, type OrbitExtras, type Runaway } from '@/services/gozetimApi';
import { holdOrbitPoll, useOrbitStore } from '@/stores/orbitStore';
import { corePresence } from '@/stores/humanoidStore';
import { useNavigationStore } from '@/stores/navigationStore';
import { isActive, useOfficeStore, type WorkerStatus } from '@/stores/officeStore';
import { usePowerStore } from '@/stores/powerStore';
import { playSfx } from '@/services/sfxPlayer';
import { ENERGY_CORE_VERTEX_SHADER } from './shaders/energyCore';
import { WIRE_CORE_FRAGMENT_SHADER } from './shaders/wireCore';

// Oturum yörüngeleri (2026-11-04, kullanıcı isteği): "şu anki yörüngeme, o animasyonuma
// dokunma; yanlarına onun gibi küçük ve farklı renkte yörüngeleri diz."
//
// Her canlı Claude Code oturumu ana çekirdeğin etrafında dönen KÜÇÜK bir çekirdek:
// aynı tel kafes dili (ENERGY_CORE_VERTEX_SHADER + WIRE_CORE_FRAGMENT_SHADER), iki katman,
// oturumun kendi tonunda. Ana çekirdek (EnergyCore.tsx) değişmedi — bu ayrı bir bileşen.
//
// Durum renkte DEĞİL harekette okunuyor, çünkü renk zaten "hangi oturum" bilgisini taşıyor:
//   çalışıyor     → tam parlak, normal dönüş
//   onay bekliyor → nabız (parlaklık + ölçek), kehribar uyarı halkası — "sıra sende"
//   boşta         → kısık, yavaş dönüş
// Alt ajanlar küçük çekirdeğin uyduları. Tıklayınca Ofis › Gözetim o oturumla açılır.
//
// Veri: officeStore (WebSocket `office_update`). Yeni bir şey uydurulmaz — oturum yoksa yörünge boş.

const MINI_OUTER = 0.3;
const MINI_INNER = 0.13;
const MAX_MINIS = 8;
const BASE_RADIUS = 3.15;
const RING_STEP = 0.42;
const REACT_DAMPING = 4;
const STALE_S = 6 * 3600;
// Yörünge ekran düzleminde bir elips: dikey eksen bu oranda basık. İlk denemede yörünge
// derinlikteydi (xz) ve küçük çekirdek ana çekirdeğin TAM ÖNÜNDEN geçip onu örtüyordu —
// "animasyonumu bozma" isteğine aykırı. Düzlemde kalınca ana çekirdeğin koronasının dışında kalıyor.
const ORBIT_SQUASH = 0.74;

interface MiniDef {
  id: string;
  label: string;
  /** Şu an / en son ne yaptığı — etiketin ikinci satırı. */
  activity: string;
  status: WorkerStatus;
  subs: number;
  hue: string;
  index: number;
  total: number;
}

// Hepsi AYNI açısal hızla, eşit aralıklı döner (bir çark gibi). İlk denemede her biri kendi
// hızındaydı; farklı hızlar ara ara iki çekirdeği üst üste bindiriyordu (ekran görüntüsünde
// yakalandı). Ortak açı modül düzeyinde — her MiniCore aynı saati okusun.
const WHEEL_SPEED = 0.07; // rad/sn
// Saat performance.now(): ana sahne ile Gözetim'in küçük sahnesinin kendi saatleri farklı;
// ikisi aynı çarkı okuduğu için ortak, duvar saatine bağlı bir kaynak lazım. dt kırpılıyor —
// sekme uyuyup geri gelince çark tek karede fırlamasın.
const wheel = { angle: 0, last: -1 };
function wheelAngle(asleep: boolean): number {
  const t = performance.now() / 1000;
  if (wheel.last !== t) {
    const dt = wheel.last < 0 ? 0 : Math.min(0.1, Math.max(0, t - wheel.last));
    wheel.angle += dt * WHEEL_SPEED * (asleep ? 0.2 : 1);
    wheel.last = t;
  }
  return wheel.angle;
}

/** Store'dan tek bir dize: yalnız bu bilgiler değişince React yeniden çizer (her karede değil). */
function selectKey(s: ReturnType<typeof useOfficeStore.getState>): string {
  const workers = s.snapshot?.workers ?? [];
  // 6 saattir olay yoksa oturum kapanmış say (SessionEnd gelmeyebiliyor — backend/core/gozetim.py STALE_S).
  const horizon = (s.snapshot?.now ?? Date.now() / 1000) - STALE_S;
  const chiefs = workers
    .filter((w) => w.kind === 'chief' && isActive(w.status) && (w.last_ts || w.started) > horizon)
    .sort((a, b) => a.started - b.started)
    .slice(0, MAX_MINIS);
  const approvals = s.snapshot?.approvals ?? [];
  return chiefs
    .map((c) => {
      const mine = workers.filter((w) => w.given_by === c.id);
      const subs = mine.filter(
        (w) => w.status === 'calisiyor' || w.status === 'onay_bekliyor',
      ).length;
      return [
        c.id,
        c.status,
        Math.min(subs, 4),
        c.project || c.title,
        doing(c, mine, approvals),
      ].join('\u0001');
    })
    .join('\u0002');
}

const DOING_MAX = 38;

/** Etiketin ikinci satırı (kullanıcı isteği, 2026-11-04): "bu küçük şeyler ne?" — oturumun şu an / en son
 *  ne yaptığı. Onay bekliyorsa hangi araç için; değilse ofisin `current` satırı (son araç ya da "Turu bitirdi…"). */
function doing(
  chief: { id: string; status: WorkerStatus; current: string },
  mine: { id: string; current: string; status: WorkerStatus; name: string }[],
  approvals: { worker_id: string; tool: string }[],
): string {
  let text = chief.current || '';
  if (chief.status === 'onay_bekliyor') {
    const ids = new Set([chief.id, ...mine.map((m) => m.id)]);
    const a = approvals.find((x) => ids.has(x.worker_id));
    text = a ? `onay bekliyor · ${a.tool}` : 'onay bekliyor';
  } else if (chief.status === 'calisiyor') {
    // Şef alt ajanını bekliyorsa asıl iş alt ajandadır.
    const sub = mine.find((m) => m.status === 'calisiyor' && m.current);
    if (sub && /alt ajana iş verdi/i.test(text)) text = `${sub.name}: ${sub.current}`;
  }
  text = text.replace(/[\u0001\u0002\s]+/g, ' ').trim();
  return text.length > DOING_MAX ? `${text.slice(0, DOING_MAX - 1)}…` : text;
}

// Araç kıvılcımları (2026-11-04): oturum (şef + alt ajanları) her araç kullandığında küçük çekirdekten
// Chiron'a bir ışık akar. Sayaç her karede store'dan aranmasın diye anlık görüntü değişince burada toplanır.
const toolStats = new Map<string, { count: number; cat: string | null }>();
function syncToolStats(snapshot: ReturnType<typeof useOfficeStore.getState>['snapshot']) {
  const workers = snapshot?.workers ?? [];
  const sums = new Map<string, { count: number; cat: string | null; ts: number }>();
  for (const w of workers) {
    const owner = w.kind === 'chief' ? w.id : w.given_by;
    if (!owner) continue;
    const cur = sums.get(owner) ?? { count: 0, cat: null, ts: -1 };
    cur.count += w.tool_count || 0;
    if (w.last_ts >= cur.ts && w.last_cat) {
      cur.cat = w.last_cat;
      cur.ts = w.last_ts;
    }
    sums.set(owner, cur);
  }
  for (const [k, v] of sums)
    toolStats.set(k, { count: v.count, cat: v.cat ?? toolStats.get(k)?.cat ?? null });
}

// İlk oturum sağ üst çapraza otursun (tam sağda değil — sağ panellerin altında kalmasın).
const WHEEL_PHASE = Math.PI * 0.2;

export function SessionOrbits() {
  const key = useOfficeStore(selectKey);

  const extras = useOrbitStore((s) => s.extras);

  // Uygulama açılır açılmaz yörünge dolsun: WebSocket yalnız DEĞİŞİKLİKTE yayınlıyor.
  useEffect(() => {
    if (!useOfficeStore.getState().snapshot) {
      void fetchOfficeState().then((s) => s && useOfficeStore.getState().setSnapshot(s));
    }
    syncToolStats(useOfficeStore.getState().snapshot);
    const unsub = useOfficeStore.subscribe((st) => syncToolStats(st.snapshot));
    const release = holdOrbitPoll();
    return () => {
      unsub();
      release();
    };
  }, []);

  const minis = useMemo<MiniDef[]>(() => {
    if (!key) return [];
    const rows = key.split('\u0002').map((r) => r.split('\u0001'));
    const hues = hueMap(rows.map((r) => r[0]));
    return rows.map(([id, status, subs, label, activity], index) => ({
      id,
      status: status as WorkerStatus,
      subs: Number(subs) || 0,
      label,
      activity: activity ?? '',
      hue: hues[id],
      index,
      total: rows.length,
    }));
  }, [key]);

  return (
    <group>
      {minis.map((m) => (
        <MiniCore key={m.id} def={m} extras={extras} />
      ))}
      {(extras?.runaways ?? []).slice(0, 4).map((r, i) => (
        <Meteor key={`${r.pid}-${r.create_time}`} r={r} index={i} />
      ))}
    </group>
  );
}

function shellUniforms(hue: string, deepMix: number, rimMix: number) {
  const base = new THREE.Color(hue);
  return {
    uTime: { value: 0 },
    uDistortion: { value: 0.12 },
    uIntensity: { value: 0 },
    uOpacity: { value: 0 },
    uColorA: { value: base.clone().lerp(new THREE.Color('#000000'), deepMix) },
    uColorB: { value: base.clone() },
    uRimColor: { value: base.clone().lerp(new THREE.Color('#ffffff'), rimMix) },
  };
}

const SPARKS = 36;
const TMP_COLOR = new THREE.Color();
const SPARK_LIFE = 0.95; // sn
const SAT_RADIUS = 0.74;

interface Sat {
  key: string;
  label: string;
  kind: 'bg' | 'dev' | 'bitti' | 'hata';
}

function satsFor(id: string, extras: OrbitExtras | null): Sat[] {
  if (!extras) return [];
  const out: Sat[] = [];
  for (const d of extras.dev)
    if (d.session === id)
      out.push({ key: `d${d.pid}`, label: `:${d.ports.join(' :')}`, kind: 'dev' });
  for (const b of extras.bg)
    if (b.session === id)
      out.push({
        key: `b${b.id}`,
        label: b.label,
        kind: b.status === 'calisiyor' ? 'bg' : b.status === 'hata' ? 'hata' : 'bitti',
      });
  return out.slice(0, 5);
}

function MiniCore({ def, extras }: { def: MiniDef; extras: OrbitExtras | null }) {
  const orbitRef = useRef<THREE.Group>(null);
  const bodyRef = useRef<THREE.Group>(null);
  const outerRef = useRef<THREE.Mesh>(null);
  const innerRef = useRef<THREE.Mesh>(null);
  const ringRef = useRef<THREE.Mesh>(null);
  const moonsRef = useRef<THREE.Group>(null);
  const outerMat = useRef<THREE.ShaderMaterial>(null);
  const innerMat = useRef<THREE.ShaderMaterial>(null);
  const ringMat = useRef<THREE.MeshBasicMaterial>(null);
  const ctxRef = useRef<THREE.Group>(null);
  const satsRef = useRef<THREE.Group>(null);
  // Kıvılcım havuzu (React Compiler kuralı: kare döngüsünde değişen her şey ref'te; geometri JSX'te,
  // tamponlara points ref'i üzerinden yazılır). Sabit boyut — kare başına ayırma yok.
  const sparkRef = useRef<THREE.Points>(null);
  const [sparkInit] = useState(() => {
    const p0 = new Float32Array(SPARKS * 3);
    for (let i = 0; i < SPARKS; i += 1) p0[i * 3 + 2] = -999;
    return { pos: p0, col: new Float32Array(SPARKS * 3) };
  });
  const sim = useRef({
    age: new Float32Array(SPARKS).fill(-1),
    from: new Float32Array(SPARKS * 3),
    bend: new Float32Array(SPARKS),
    next: 0,
    queued: 0,
    seen: -1,
    cat: '',
  });
  // Çarktaki yeri: eşit aralık. Oturum sayısı değişince yeni yerine SÖNÜMLE kayar, sıçramaz.
  const slot = (def.index / Math.max(def.total, 1)) * Math.PI * 2;
  const offset = useRef(slot);
  const spinMul = useRef(1);
  const hovered = useRef(false);
  const [hover, setHover] = useState(false);

  // Yarıçap sırayla hafif değişiyor (iç/dış) — tam bir halka gibi değil, dizilmiş gibi okunsun.
  const radius = BASE_RADIUS + (def.index % 2) * RING_STEP;
  const tilt = (def.index % 2 === 0 ? 1 : -1) * 0.22;

  // Bağlam halkası: doluluk yayı, %2 adımla (her yoklamada yeni geometri kurulmasın). %80'de kehribar.
  const ctx = extras?.ctx[def.id];
  const ctxFrac = ctx ? Math.min(1, Math.round((ctx.used / ctx.window) * 50) / 50) : 0;
  const ctxHot = ctxFrac >= 0.8;
  const sats = satsFor(def.id, extras);

  const outerUniforms = useMemo(() => shellUniforms(def.hue, 0.6, 0.55), [def.hue]);
  const innerUniforms = useMemo(() => shellUniforms(def.hue, 0.35, 0.75), [def.hue]);

  useFrame((state, delta) => {
    const orbit = orbitRef.current;
    const body = bodyRef.current;
    if (
      !orbit ||
      !body ||
      !outerMat.current ||
      !innerMat.current ||
      !outerRef.current ||
      !innerRef.current
    )
      return;
    const t = state.clock.elapsedTime;
    const asleep = usePowerStore.getState().powerState === 'asleep';
    const waiting = def.status === 'onay_bekliyor';
    const idle = def.status === 'bosta';

    // En kısa yoldan yeni yerine kay (−π..π farkı), sonra ortak çarkın açısını ekle.
    let diff = slot - offset.current;
    diff = Math.atan2(Math.sin(diff), Math.cos(diff));
    offset.current += diff * (1 - Math.exp(-1.6 * delta));
    const a = wheelAngle(asleep) + offset.current + WHEEL_PHASE;
    // Hafif eğim (tilt) yalnız derinlikte: arkaya geçerken biraz küçülüp sisle sönsün, ama ekranda çekirdeği örtmesin.
    orbit.position.set(
      Math.cos(a) * radius,
      Math.sin(a) * radius * ORBIT_SQUASH,
      Math.sin(a) * tilt * 2,
    );

    const pulse = waiting ? 0.5 + 0.5 * Math.sin(t * 3.2) : 0;
    const targetIntensity = asleep ? 0.22 : idle ? 0.5 : waiting ? 0.85 + pulse * 0.55 : 1.05;
    const targetOpacityScale = asleep ? 0.4 : idle ? 0.55 : 1;
    spinMul.current = THREE.MathUtils.damp(
      spinMul.current,
      asleep ? 0.15 : idle ? 0.35 : 1,
      REACT_DAMPING,
      delta,
    );

    for (const [mat, base] of [
      [outerMat.current, 0.42],
      [innerMat.current, 0.85],
    ] as const) {
      mat.uniforms.uTime.value = t + def.index * 3.1;
      mat.uniforms.uIntensity.value = THREE.MathUtils.damp(
        mat.uniforms.uIntensity.value,
        targetIntensity + (hovered.current ? 0.3 : 0),
        REACT_DAMPING,
        delta,
      );
      mat.uniforms.uOpacity.value = THREE.MathUtils.damp(
        mat.uniforms.uOpacity.value,
        base * targetOpacityScale,
        2.2, // doğuşta yavaş belirsin
        delta,
      );
    }
    outerRef.current.rotation.y += delta * 0.6 * spinMul.current;
    innerRef.current.rotation.y -= delta * 1.6 * spinMul.current;
    innerRef.current.rotation.x += delta * 0.4 * spinMul.current;

    // İnsan görünümünde ana çekirdekle birlikte çekil; üzerine gelince hafif büyü.
    const presence = corePresence();
    orbit.visible = presence > 0.001;
    const scale = (1 + pulse * 0.12 + (hovered.current ? 0.18 : 0)) * presence;
    body.scale.setScalar(
      THREE.MathUtils.damp(body.scale.x || 0.001, Math.max(scale, 1e-4), REACT_DAMPING, delta),
    );

    if (ringRef.current && ringMat.current) {
      ringRef.current.visible = waiting && !asleep;
      ringRef.current.scale.setScalar(1 + pulse * 0.35);
      ringMat.current.opacity = 0.25 + pulse * 0.45;
      ringRef.current.lookAt(state.camera.position);
    }
    if (moonsRef.current) moonsRef.current.rotation.y += delta * 1.2 * spinMul.current;
    if (ctxRef.current) ctxRef.current.lookAt(state.camera.position);
    if (satsRef.current) satsRef.current.rotation.z += delta * 0.35;

    // ── Kıvılcımlar ──
    const sp = sim.current;
    const stat = toolStats.get(def.id);
    if (stat) {
      if (sp.seen < 0)
        sp.seen = stat.count; // ilk kare: geçmiş araçlar için patlama olmasın
      else if (stat.count > sp.seen) {
        sp.queued = Math.min(sp.queued + (stat.count - sp.seen), 8);
        sp.seen = stat.count;
      }
      sp.cat = stat.cat ?? sp.cat;
    }
    const geo = sparkRef.current?.geometry;
    if (!geo) return;
    const pos = geo.attributes.position as THREE.BufferAttribute;
    const col = geo.attributes.color as THREE.BufferAttribute;
    if (sp.queued > 0 && !asleep && presence > 0.5 && Math.random() < delta * 9) {
      // Kuyruktakileri aralıkla bırak: aynı anda 5 araç tek ışık topu değil, dizi gibi aksın.
      const i = sp.next;
      sp.next = (sp.next + 1) % SPARKS;
      sp.queued -= 1;
      sp.age[i] = 0;
      sp.from[i * 3] = orbit.position.x;
      sp.from[i * 3 + 1] = orbit.position.y;
      sp.from[i * 3 + 2] = orbit.position.z;
      sp.bend[i] = (Math.random() - 0.5) * 1.6;
      TMP_COLOR.set(CAT_COLOR[sp.cat] ?? def.hue);
      col.setXYZ(i, TMP_COLOR.r, TMP_COLOR.g, TMP_COLOR.b);
      col.needsUpdate = true;
    }
    let live = false;
    for (let i = 0; i < SPARKS; i += 1) {
      if (sp.age[i] < 0) continue;
      live = true;
      sp.age[i] += delta;
      const k = sp.age[i] / SPARK_LIFE;
      if (k >= 1) {
        sp.age[i] = -1;
        pos.setXYZ(i, 0, 0, -999);
        continue;
      }
      // Kavisli yol: çıkıştan merkeze, yana eğilerek; sona doğru hızlanır (çekirdek çekiyor).
      const e = k * k * (3 - 2 * k);
      const fx = sp.from[i * 3];
      const fy = sp.from[i * 3 + 1];
      const fz = sp.from[i * 3 + 2];
      const m = 4 * e * (1 - e) * 0.35 * sp.bend[i];
      pos.setXYZ(i, fx * (1 - e) - fy * m, fy * (1 - e) + fx * m, fz * (1 - e));
    }
    if (live) pos.needsUpdate = true;
  });

  const open = () => {
    const office = useOfficeStore.getState();
    office.setFocusSession(def.id);
    office.setTab('gozetim');
    if (useNavigationStore.getState().activeModule !== 'agents')
      useNavigationStore.getState().toggleModule('agents');
    playSfx('hud');
  };

  return (
    <>
      <points ref={sparkRef} frustumCulled={false}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[sparkInit.pos, 3]} />
          <bufferAttribute attach="attributes-color" args={[sparkInit.col, 3]} />
        </bufferGeometry>
        <pointsMaterial
          size={0.15}
          sizeAttenuation
          vertexColors
          transparent
          opacity={0.95}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
      <group ref={orbitRef}>
        <group ref={bodyRef}>
          <mesh
            ref={outerRef}
            onClick={(e) => {
              e.stopPropagation();
              // Gözetim'de yörünge fareyle döndürülüyor: sürükleme küçük çekirdeğin üstünde biterse tıklama sayılmasın.
              if (e.delta > 4) return;
              open();
            }}
            onPointerOver={(e) => {
              e.stopPropagation();
              hovered.current = true;
              setHover(true);
              document.body.style.cursor = 'pointer';
            }}
            onPointerOut={() => {
              hovered.current = false;
              setHover(false);
              document.body.style.cursor = 'auto';
            }}
          >
            <icosahedronGeometry args={[MINI_OUTER, 1]} />
            <shaderMaterial
              ref={outerMat}
              uniforms={outerUniforms}
              vertexShader={ENERGY_CORE_VERTEX_SHADER}
              fragmentShader={WIRE_CORE_FRAGMENT_SHADER}
              wireframe
              transparent
              depthWrite={false}
              side={THREE.DoubleSide}
              blending={THREE.AdditiveBlending}
            />
          </mesh>
          <mesh ref={innerRef} rotation={[0.4, 0, 0.2]}>
            <icosahedronGeometry args={[MINI_INNER, 2]} />
            <shaderMaterial
              ref={innerMat}
              uniforms={innerUniforms}
              vertexShader={ENERGY_CORE_VERTEX_SHADER}
              fragmentShader={WIRE_CORE_FRAGMENT_SHADER}
              wireframe
              transparent
              depthWrite={false}
              side={THREE.DoubleSide}
              blending={THREE.AdditiveBlending}
            />
          </mesh>
          {/* Onay bekliyor: kehribar halka — çekirdeğin "otomasyon" kehribarıyla aynı aile: dikkat. */}
          <mesh ref={ringRef} visible={false}>
            <ringGeometry args={[MINI_OUTER * 1.45, MINI_OUTER * 1.58, 48]} />
            <meshBasicMaterial
              ref={ringMat}
              color="#e0a355"
              transparent
              opacity={0.4}
              depthWrite={false}
              blending={THREE.AdditiveBlending}
              side={THREE.DoubleSide}
            />
          </mesh>
          {/* Bağlam halkası: soluk iz + dolu yay (saat 12'den saat yönüne). */}
          {ctx && (
            <group ref={ctxRef}>
              <mesh>
                <ringGeometry args={[MINI_OUTER * 1.22, MINI_OUTER * 1.3, 64]} />
                <meshBasicMaterial
                  color="#ffffff"
                  transparent
                  opacity={0.07}
                  depthWrite={false}
                  side={THREE.DoubleSide}
                />
              </mesh>
              {ctxFrac > 0 && (
                <mesh rotation={[0, 0, Math.PI / 2]} scale={[-1, 1, 1]}>
                  <ringGeometry
                    key={ctxFrac}
                    args={[MINI_OUTER * 1.2, MINI_OUTER * 1.32, 64, 1, 0, ctxFrac * Math.PI * 2]}
                  />
                  <meshBasicMaterial
                    color={ctxHot ? '#e0a355' : def.hue}
                    transparent
                    opacity={ctxHot ? 0.95 : 0.7}
                    depthWrite={false}
                    side={THREE.DoubleSide}
                    blending={THREE.AdditiveBlending}
                  />
                </mesh>
              )}
            </group>
          )}
          {/* Arka plan işleri ve dev sunucular: oturumun etrafında dönen küçük elmaslar. */}
          {sats.length > 0 && (
            <group ref={satsRef}>
              {sats.map((sat, i) => {
                const a = (i / sats.length) * Math.PI * 2;
                const color =
                  sat.kind === 'dev'
                    ? '#7ee0b5'
                    : sat.kind === 'hata'
                      ? '#ff5d6c'
                      : sat.kind === 'bitti'
                        ? '#8a9ab0'
                        : '#e8eef7';
                return (
                  <group
                    key={sat.key}
                    position={[Math.cos(a) * SAT_RADIUS, Math.sin(a) * SAT_RADIUS, 0]}
                  >
                    <mesh rotation={[0.6, 0.6, 0]}>
                      <octahedronGeometry args={[sat.kind === 'dev' ? 0.075 : 0.06, 0]} />
                      <meshBasicMaterial
                        color={color}
                        wireframe={sat.kind !== 'dev'}
                        transparent
                        opacity={0.95}
                      />
                    </mesh>
                    <Html
                      center
                      position={[Math.cos(a) * 0.24, Math.sin(a) * 0.24, 0]} // dışa doğru: oturum etiketinin üstüne binmesin
                      zIndexRange={[4, 0]}
                      style={{ pointerEvents: 'none' }}
                    >
                      <span className={`session-orb-sat is-${sat.kind}`}>{sat.label}</span>
                    </Html>
                  </group>
                );
              })}
            </group>
          )}
          <group ref={moonsRef} rotation={[0.5, 0, 0]}>
            {Array.from({ length: def.subs }, (_, i) => {
              const a = (i / Math.max(def.subs, 1)) * Math.PI * 2;
              return (
                <mesh key={i} position={[Math.cos(a) * 0.52, 0, Math.sin(a) * 0.52]}>
                  <sphereGeometry args={[0.035, 10, 10]} />
                  <meshBasicMaterial
                    color={def.hue}
                    transparent
                    opacity={0.9}
                    blending={THREE.AdditiveBlending}
                  />
                </mesh>
              );
            })}
          </group>
        </group>
        <Html
          center
          position={[0, -0.55, 0]}
          zIndexRange={[5, 0]}
          style={{ pointerEvents: 'none' }}
        >
          <div
            className={`session-orb-label ${hover ? 'is-hover' : ''} is-${def.status}`}
            style={{ color: def.hue }}
          >
            <span className="session-orb-label__name">{def.label}</span>
            {def.activity && <span className="session-orb-label__doing">{def.activity}</span>}
          </div>
        </Html>
      </group>
    </>
  );
}

// Kaçak süreç meteoru (2026-11-04): sahibi kapanmış ama CPU yakan ya da port tutan süreç dış yörüngede
// kızıl, kuyruklu bir taş olarak döner. Tıklama Gözetim'i açar — "Sonlandır" orada, aynı pid+başlangıç
// doğrulamasıyla (backend/core/gozetim.py RunawayWatch.end). Sahneden doğrudan öldürmek yok.
const TRAIL = 22;
const METEOR_RADIUS = 5.3;

function Meteor({ r, index }: { r: Runaway; index: number }) {
  const head = useRef<THREE.Group>(null);
  const angle = useRef(index * 2.1 + (r.pid % 17) * 0.3);
  const trailRef = useRef<THREE.Points>(null);
  const [trailInit] = useState(() => {
    const p = new Float32Array(TRAIL * 3);
    const c = new Float32Array(TRAIL * 3);
    for (let i = 0; i < TRAIL; i += 1) {
      const f = 1 - i / TRAIL;
      c[i * 3] = 1 * f;
      c[i * 3 + 1] = 0.42 * f * f;
      c[i * 3 + 2] = 0.2 * f * f;
      p[i * 3 + 2] = -999;
    }
    return { pos: p, col: c };
  });
  const burning = r.kind === 'yakiyor';

  useFrame((state, delta) => {
    angle.current += delta * (burning ? 0.22 : 0.12);
    const geo = trailRef.current?.geometry;
    if (!geo) return;
    const pos = geo.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < TRAIL; i += 1) {
      const a = angle.current - i * 0.025;
      pos.setXYZ(
        i,
        Math.cos(a) * METEOR_RADIUS,
        Math.sin(a) * METEOR_RADIUS * 0.62,
        Math.sin(a) * -0.8,
      );
    }
    pos.needsUpdate = true;
    if (head.current) {
      head.current.position.set(pos.getX(0), pos.getY(0), pos.getZ(0));
      const flick = 1 + Math.sin(state.clock.elapsedTime * 13 + index) * 0.12;
      head.current.scale.setScalar(flick * corePresence());
    }
  });

  const open = () => {
    const office = useOfficeStore.getState();
    office.setFocusSession(null);
    office.setTab('gozetim');
    if (useNavigationStore.getState().activeModule !== 'agents')
      useNavigationStore.getState().toggleModule('agents');
    playSfx('hud');
  };

  return (
    <>
      <points ref={trailRef} frustumCulled={false}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[trailInit.pos, 3]} />
          <bufferAttribute attach="attributes-color" args={[trailInit.col, 3]} />
        </bufferGeometry>
        <pointsMaterial
          size={0.11}
          sizeAttenuation
          vertexColors
          transparent
          opacity={0.9}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
      <group ref={head}>
        <mesh
          onClick={(e) => {
            e.stopPropagation();
            if (e.delta > 4) return;
            open();
          }}
          onPointerOver={() => (document.body.style.cursor = 'pointer')}
          onPointerOut={() => (document.body.style.cursor = 'auto')}
        >
          <icosahedronGeometry args={[0.14, 0]} />
          <meshBasicMaterial color={burning ? '#ff6a3d' : '#ff9e5e'} />
        </mesh>
        <mesh>
          <sphereGeometry args={[0.26, 16, 16]} />
          <meshBasicMaterial
            color="#ff4a2a"
            transparent
            opacity={0.18}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
          />
        </mesh>
        <Html
          center
          position={[0, -0.36, 0]}
          zIndexRange={[5, 0]}
          style={{ pointerEvents: 'none' }}
        >
          <span className="session-orb-meteor">
            kaçak · {r.name}
            {r.ports.length ? ` :${r.ports.join(' :')}` : ''}
            {burning ? ` · %${Math.round(r.cpu)}` : ''}
          </span>
        </Html>
      </group>
    </>
  );
}
