'use client';

import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { useAIStateStore, type AIState } from '@/stores/aiStateStore';
import { usePowerStore } from '@/stores/powerStore';
import { playSfx } from '@/services/sfxPlayer';
import { dampColor, SLEEP_PALETTE, STATE_PALETTE } from './palette';
import { getRevealProgress } from './reveal';
import { ENERGY_CORE_VERTEX_SHADER } from './shaders/energyCore';
import { WIRE_CORE_FRAGMENT_SHADER } from './shaders/wireCore';

// Notes/Tasarim-Kurallari.md § Enerji çekirdeği — "The center of CHIRON is alive... It constantly
// breathes, rotates slowly, emits particles, changes glow."
//
// ── FORM DEĞİŞTİ, DAVRANIŞ DEĞİŞMEDİ (2026-08-06, kullanıcı isteği) ──────────
// Çekirdek 2026-08-06'ya kadar DOLU bir plazma küreydi (icosahedron + yüzey
// shader'ı). Kullanıcı Ultron benzeri bir HOLOGRAM istedi: içi boş, üst üste
// binen tel kafesler ve içeride dönen bir spiral.
//
// Değişen: geometri ve ışık modeli. Değişmeyen: bu dosyanın taşıdığı davranış
// sözleşmesinin TAMAMI — nefes, beş tepki (renk + hız + dalgalanma), uyku modu,
// açılış zamanlaması, fare tepkisi, çekirdeğe tıklayınca uyuma. Bunlar aylardır
// ölçülüp ayarlanmış şeyler (bkz. Notes/Arayuz.md § Beş tepki); yeni formla
// birlikte atılsalardı sahne güzelleşir ama BİLGİ TAŞIMAYI bırakırdı.
//
// Üç katman ve neden üç:
//   1. Dış kafes  — seyrek, büyük üçgenler, SOLUK. Cismin sınırını çiziyor.
//   2. Orta kafes — sık, ters yönde döner. Dalgalanmayı (uDistortion) o taşıyor.
//   3. Çekirdek   — küçük ve YOĞUN. Kafesin içinde bir şey OLDUĞUNU söyler.
// Tek kafese indirilseydi orb bir tel yumağı gibi düz okunurdu; derinlik hissi
// katmanların birbirine göre ters dönmesinden ve yoğunluk farkından çıkıyor.
//
// İlk denemede 3. katman küre üzerine sarılan bir SPİRAL çizgiydi (Ultron'daki
// gibi). Ekran görüntüsünde çalışmadı: 13 sarımlı bir spiral önden bakınca
// spiral değil, YATAY ÇİZGİ YIĞINI gibi okunuyor — bir bobin gibi, akan enerji
// gibi değil. Yerine küçük ve sık bir kafes küre kondu; aynı işi ("içeride bir
// şey var") kalabalık yapmadan yapıyor.
const ROTATION_SPEED = 0.08; // rad/sn
const FLOAT_AMPLITUDE = 0.18;
const FLOAT_SPEED = 0.6;
const BREATH_SPEED = 0.7;
const REACT_DAMPING = 4;
const BASE_DISTORTION = 0.16;
// Notes/Tasarim-Kurallari.md § Hareket (fare) — "Energy core follows the cursor subtly". Kameranın
// takibi CameraRig'de; burada çekirdeğin kendisi üzerine gelince hafifçe tepki veriyor.
const HOVER_INTENSITY_BOOST = 0.22;
const HOVER_SCALE_BOOST = 0.05;
// Açılış Animasyonu: Energy Core, BootOverlay'in
// logosu solmaya başladığı sırada büyüyerek belirir.
// 2026-07-31: açılış yavaşlatıldı ve sıralama değişti — önce korona
// (EnergyTendrils, 2.5 sn) beliriyor, çekirdek ondan sonra geliyor.
const REVEAL_DELAY = 3.4;
const REVEAL_DURATION = 0.9;
// Kullanıcı isteğiyle (2026-07-27) — aşırı parlaklık/beyaz kırpılmayı önlemek için
// nihai yoğunluk her zaman bu tavanın altında tutuluyor (fragment shader'daki
// çarpanlarla birlikte).
const MAX_INTENSITY = 1.5;

// ── Katman geometrisi ────────────────────────────────────────────────────────
// Detay seviyesi tel kafeste dolu küredekinin TERSİ mantıkla seçiliyor. Dolu
// küre detail=5 kullanıyordu (20480 üçgen) çünkü orada üçgenler görünmüyor,
// yalnızca yüzey pürüzsüzleşiyordu. Kafeste her üçgen ÇİZİLİYOR: aynı detayla
// orb, deseni okunmayan gri bir topağa dönerdi.
const OUTER_RADIUS = 1.62;
const OUTER_DETAIL = 1; // 80 üçgen — okunabilir, geometrik bir kafes
const MID_RADIUS = 1.24;
const MID_DETAIL = 2; // 320 üçgen — sık ama hâlâ desen olarak okunuyor
const CORE_RADIUS = 0.58;
const CORE_DETAIL = 3; // 1280 üçgen ama YARIÇAPI küçük: ekranda yoğun bir küme

// Dalgalanma payları. Dış kafes az alıyor: cismin sınırını çizen katman fazla
// kıvranırsa orb'un bir ÇAPI olduğu hissi kayboluyor. Çekirdek fazla alıyor —
// içerideki şey en canlı, en huzursuz olanı.
const OUTER_DISTORTION_SCALE = 0.4;
const MID_DISTORTION_SCALE = 1;
const CORE_DISTORTION_SCALE = 1.5;

// Opaklıklar: dışarıdan içeri artıyor. İlk denemede dış kafes 0.5'ti ve orb'un
// beyaz bir çokgen silüeti vardı — kafes değil, tel bir top gibi. Sınırı çizen
// katman GÖRÜNMELİ ama BAKILAN şey olmamalı.
const OUTER_OPACITY = 0.32;
const MID_OPACITY = 0.44;
const CORE_OPACITY = 0.8;

// Katmanların birbirine göre dönüş hızları. Orta kafes TERS yönde ve daha hızlı —
// tek yönde dönen iki kafes tek bir kalın kafes gibi okunuyordu.
const OUTER_SPIN = 0.55;
const MID_SPIN = -1.35;
const CORE_SPIN = 2.1;
// Eğik duruyorlar: hepsi aynı eksende dönseydi kesişim çizgileri sabit kalır ve
// moiré deseni oluştururdu.
const MID_TILT = 0.46;
const CORE_TILT = -0.32;

// ── Uyku (kullanıcı isteği, 2026-07-30) ─────────────────────────────────────
// Çekirdeğe tıklayınca Chiron uyuyor (bkz. stores/powerStore.ts). Değerler
// "sönmüş" değil "dinlenen" bir cisim hedefliyor: nefes çok yavaşlıyor, kafes
// neredeyse düzleşiyor, ışıma dibe iniyor ama SIFIR OLMUYOR — sıfır olsa
// uygulama çökmüş gibi görünürdü.
// Tel kafeste bu risk daha büyük: dolu kürenin siluetı sönükken bile bir kütle
// gösteriyordu, kafes sönünce geriye HİÇBİR ŞEY kalmıyor. Uyku opaklığı bu
// yüzden yoğunluktan ayrı bir değer olarak tutuluyor.
const SLEEP_INTENSITY = 0.32;
const SLEEP_SCALE = 0.87;
const SLEEP_DISTORTION = 0.035;
const SLEEP_ROTATION_MULTIPLIER = 0.16;
const SLEEP_BREATH_MULTIPLIER = 0.32;
const SLEEP_OPACITY_SCALE = 0.55;

// ── Beş tepki (2026-07-31, Notes/Arayuz.md § Beş tepki) ────────────────────────────────
// `automation` ve `memory` sahnede BİRBİRİNİN ZITTI olacak şekilde ayarlandı:
// otomasyon hızlı/sıkı/pürüzsüz (bir makine dönüyor), hafıza yavaş/geniş/
// dalgalı (derinden bir şey yüzeye çıkıyor). Tek başına renk yetmezdi — renk
// körlüğünde ya da göz ucuyla bakıldığında ayrımı taşıyan şey HAREKET.

function getBreathSpeedMultiplier(state: AIState): number {
  if (state === 'listening') return 1.7;
  if (state === 'thinking') return 0.6;
  if (state === 'automation') return 1.25; // iş temposu — telaşlı değil, kararlı
  if (state === 'memory') return 0.42; // derin ve yavaş nefes
  return 1;
}

function getExtraIntensity(state: AIState): number {
  // Konuşma yeşile döndüğünden beri 0.45 yerine 0.32: yeşil, gözün en duyarlı
  // olduğu dalga boyu: aynı sayısal yoğunlukta maviden belirgin şekilde daha
  // parlak görünüyor ve bloom'la birlikte fosforlu kaleme dönüyordu.
  if (state === 'speaking') return 0.32;
  // Kehribar da sıcak ve parlak algılanıyor; yeşille aynı gerekçeyle frenli.
  if (state === 'automation') return 0.24;
  if (state === 'vision') return 0.18;
  if (state === 'thinking') return -0.15;
  // Hatırlamak parlamak değil: çekirdek hafifçe kısılıyor, ışık dışarı değil
  // içeri gidiyor gibi okunsun.
  if (state === 'memory') return -0.08;
  return 0;
}

function getTargetDistortion(state: AIState): number {
  if (state === 'vision') return 0.32; // veri akışı — daha türbülanslı kafes
  if (state === 'memory') return 0.26; // derinden yüzeye çıkan bir şey
  if (state === 'thinking') return 0.08; // sakin, az dalgalı
  if (state === 'automation') return 0.07; // makine yüzeyi: pürüzsüz, kararlı
  return BASE_DISTORTION;
}

function getExtraScale(state: AIState): number {
  if (state === 'speaking') return 0.14;
  if (state === 'automation') return -0.05; // sıkışmış, odaklanmış
  if (state === 'memory') return 0.06; // hatırlarken hafifçe açılıyor
  return 0;
}

// Dönüş hızı: otomasyonun asıl imzası. Renk "bir şey değişti" der, HIZ "Chiron
// şu an senin makinende çalışıyor" der — kullanıcı ekrana bakmıyorken bile göz
// ucuyla yakalanan sinyal bu. Tel kafeste bu sinyal DAHA güçlü okunuyor: dolu
// kürede dönüşü yalnızca yüzey deseni ele veriyordu, kafeste çizgilerin kendisi
// akıyor.
function getRotationMultiplier(state: AIState): number {
  if (state === 'automation') return 2.4;
  if (state === 'memory') return 0.4;
  if (state === 'thinking') return 0.7;
  return 1;
}

function createShellUniforms(distortion: number) {
  return {
    uTime: { value: 0 },
    uDistortion: { value: distortion },
    uIntensity: { value: 1 },
    uOpacity: { value: 0 }, // açılışta görünmez — reveal ile yükseliyor
    // Platin + Buz Mavisi palet (2026-07-28): gövde derin mavi → buz mavisi
    // gradyanı, silüet/kenar ise platin (bkz. three/palette.ts).
    uColorA: { value: new THREE.Color('#3f6db8') },
    uColorB: { value: new THREE.Color('#7fb2ff') },
    uRimColor: { value: new THREE.Color('#e8eef7') },
  };
}

export function EnergyCore() {
  const groupRef = useRef<THREE.Group>(null);
  const outerRef = useRef<THREE.Mesh>(null);
  const midRef = useRef<THREE.Mesh>(null);
  const coreRef = useRef<THREE.Mesh>(null);
  const outerMaterialRef = useRef<THREE.ShaderMaterial>(null);
  const midMaterialRef = useRef<THREE.ShaderMaterial>(null);
  const coreMaterialRef = useRef<THREE.ShaderMaterial>(null);
  const breathPhaseRef = useRef(0);
  const hoveredRef = useRef(false);
  // Dönüş hızı da sönümleniyor, doğrudan atanmıyor: 1×'ten 2.4×'e ANINDA
  // geçmek kafesi bir motor gibi tekletiyor. "Never use linear movement"
  // (Notes/Tasarim-Kurallari.md § Animasyon) hız değişimi için de geçerli.
  const rotationMultiplierRef = useRef(1);

  useFrame((state, delta) => {
    const group = groupRef.current;
    const outer = outerRef.current;
    const mid = midRef.current;
    const core = coreRef.current;
    const outerMaterial = outerMaterialRef.current;
    const midMaterial = midMaterialRef.current;
    const coreMaterial = coreMaterialRef.current;
    if (!group || !outer || !mid || !core) return;
    if (!outerMaterial || !midMaterial || !coreMaterial) return;

    const aiState = useAIStateStore.getState().aiState;
    const isAsleep = usePowerStore.getState().powerState === 'asleep';
    const t = state.clock.elapsedTime;

    // Nefes alma fazı biriktirilerek ilerliyor (ham elapsedTime değil) — böylece
    // AI durumu değişince nefes hızı sıçrama yapmadan, yumuşakça değişiyor.
    const breathMultiplier = isAsleep ? SLEEP_BREATH_MULTIPLIER : getBreathSpeedMultiplier(aiState);
    breathPhaseRef.current += delta * BREATH_SPEED * breathMultiplier;
    const breath = Math.sin(breathPhaseRef.current);

    const reveal = getRevealProgress(t, REVEAL_DELAY, REVEAL_DURATION);

    // Renk: uykuda soğuk çeliğe, konuşurken yeşil-limon plazmaya. Üç uniform da
    // aynı paletten besleniyor (bkz. three/palette.ts) ve yumuşakça geçiyor —
    // anlık renk sıçraması "durum değişti" yerine "hata oldu" gibi okunuyor.
    const palette = isAsleep ? SLEEP_PALETTE : STATE_PALETTE[aiState];
    for (const material of [outerMaterial, midMaterial, coreMaterial]) {
      dampColor(material.uniforms.uColorA.value, palette.bodyDeep, delta);
      dampColor(material.uniforms.uColorB.value, palette.bodyLight, delta);
      dampColor(material.uniforms.uRimColor.value, palette.rim, delta);
      material.uniforms.uTime.value = t;
    }

    // Uykuda fare etkileşimi susuyor: uyuyan bir cisim imlece tepki vermemeli.
    const hoverBoost = hoveredRef.current && !isAsleep ? HOVER_INTENSITY_BOOST : 0;
    const targetIntensity = isAsleep
      ? SLEEP_INTENSITY * reveal
      : Math.min(1 + breath * 0.25 + getExtraIntensity(aiState) + hoverBoost, MAX_INTENSITY) *
        reveal;
    const targetDistortion = isAsleep ? SLEEP_DISTORTION : getTargetDistortion(aiState);
    const opacityScale = (isAsleep ? SLEEP_OPACITY_SCALE : 1) * reveal;

    for (const [material, baseOpacity, distortionScale] of [
      [outerMaterial, OUTER_OPACITY, OUTER_DISTORTION_SCALE],
      [midMaterial, MID_OPACITY, MID_DISTORTION_SCALE],
      [coreMaterial, CORE_OPACITY, CORE_DISTORTION_SCALE],
    ] as const) {
      material.uniforms.uIntensity.value = THREE.MathUtils.damp(
        material.uniforms.uIntensity.value,
        targetIntensity,
        REACT_DAMPING,
        delta,
      );
      material.uniforms.uDistortion.value = THREE.MathUtils.damp(
        material.uniforms.uDistortion.value,
        targetDistortion * distortionScale,
        REACT_DAMPING,
        delta,
      );
      material.uniforms.uOpacity.value = THREE.MathUtils.damp(
        material.uniforms.uOpacity.value,
        baseOpacity * opacityScale,
        REACT_DAMPING,
        delta,
      );
    }
    rotationMultiplierRef.current = THREE.MathUtils.damp(
      rotationMultiplierRef.current,
      isAsleep ? SLEEP_ROTATION_MULTIPLIER : getRotationMultiplier(aiState),
      REACT_DAMPING,
      delta,
    );
    const spin = delta * ROTATION_SPEED * rotationMultiplierRef.current;
    outer.rotation.y += spin * OUTER_SPIN;
    mid.rotation.y += spin * MID_SPIN;
    core.rotation.y += spin * CORE_SPIN;

    // Süzülme uykuda da sürüyor (sadece nefes yavaşlıyor): tamamen durursa
    // çekirdek canlı bir cisim değil, donmuş bir kare gibi görünüyor.
    group.position.y = Math.sin(t * FLOAT_SPEED) * FLOAT_AMPLITUDE;
    const targetScale = isAsleep
      ? (SLEEP_SCALE + breath * 0.012) * reveal
      : (1 +
          breath * 0.03 +
          getExtraScale(aiState) +
          (hoveredRef.current ? HOVER_SCALE_BOOST : 0)) *
        reveal;
    group.scale.setScalar(THREE.MathUtils.damp(group.scale.x, targetScale, REACT_DAMPING, delta));
  });

  return (
    <group ref={groupRef}>
      <mesh
        ref={outerRef}
        // Çekirdeğe tıklamak Chiron'u uyutuyor (kullanıcı isteği, 2026-07-30).
        // Tıklama hedefi DIŞ KAFES: `wireframe` yalnızca ÇİZİMİ değiştiriyor,
        // ışın-kesişimi (raycast) hâlâ üçgenlerin tamamına bakıyor — yani
        // kullanıcı çizgiyi nişan almak zorunda değil, orb'un herhangi bir
        // yerine tıklaması yetiyor.
        // Uyandırma burada DEĞİL: uykuda ekranı SleepVeil kaplıyor ve her yere
        // tıklamak uyandırıyor (bkz. components/SleepVeil.tsx).
        onClick={(e) => {
          e.stopPropagation();
          usePowerStore.getState().toggle();
          playSfx('hud');
        }}
        onPointerOver={(e) => {
          e.stopPropagation();
          hoveredRef.current = true;
          document.body.style.cursor = 'pointer';
        }}
        onPointerOut={() => {
          hoveredRef.current = false;
          document.body.style.cursor = 'auto';
        }}
      >
        <icosahedronGeometry args={[OUTER_RADIUS, OUTER_DETAIL]} />
        <shaderMaterial
          ref={outerMaterialRef}
          uniforms={createShellUniforms(BASE_DISTORTION * OUTER_DISTORTION_SCALE)}
          vertexShader={ENERGY_CORE_VERTEX_SHADER}
          fragmentShader={WIRE_CORE_FRAGMENT_SHADER}
          wireframe
          transparent
          // depthWrite kapalı: açık olsaydı kafesin ön çizgileri arkadakileri
          // ve içerideki spirali derinlik tamponundan siler, içi boş bir cisim
          // yerine kesik kesik bir kabuk görürdük.
          depthWrite={false}
          side={THREE.DoubleSide}
          blending={THREE.AdditiveBlending}
        />
      </mesh>

      <mesh ref={midRef} rotation={[MID_TILT, 0, MID_TILT * 0.5]}>
        <icosahedronGeometry args={[MID_RADIUS, MID_DETAIL]} />
        <shaderMaterial
          ref={midMaterialRef}
          uniforms={createShellUniforms(BASE_DISTORTION * MID_DISTORTION_SCALE)}
          vertexShader={ENERGY_CORE_VERTEX_SHADER}
          fragmentShader={WIRE_CORE_FRAGMENT_SHADER}
          wireframe
          transparent
          depthWrite={false}
          side={THREE.DoubleSide}
          blending={THREE.AdditiveBlending}
        />
      </mesh>

      <mesh ref={coreRef} rotation={[CORE_TILT, 0, CORE_TILT * 0.5]}>
        <icosahedronGeometry args={[CORE_RADIUS, CORE_DETAIL]} />
        <shaderMaterial
          ref={coreMaterialRef}
          uniforms={createShellUniforms(BASE_DISTORTION * CORE_DISTORTION_SCALE)}
          vertexShader={ENERGY_CORE_VERTEX_SHADER}
          fragmentShader={WIRE_CORE_FRAGMENT_SHADER}
          wireframe
          transparent
          depthWrite={false}
          side={THREE.DoubleSide}
          blending={THREE.AdditiveBlending}
        />
      </mesh>
    </group>
  );
}
