'use client';

import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Stars } from '@react-three/drei';
import * as THREE from 'three';
import { DustField } from './DustField';

// Kullanıcı isteğiyle (2026-07-27) — "arka plana yavaşça dönen/süzülen 3D yıldız
// parçacık alanı" için tüm atmosfer grubuna (nebula + yıldızlar + sparkles) çok
// yavaş, sabit bir dönüş uygulanıyor.
const BACKGROUND_ROTATION_SPEED = 0.006; // rad/sn

// Deterministik sözde-rastgele (GLSL tarzı sin-hash) — render sırasında Math.random()
// gibi saf olmayan bir çağrı kullanmamak için (react-hooks/purity).
function hash(seed: number): number {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

// Büyük, ters çevrilmiş, dokusuz bir ikosahedron — vertex-renk gradyanıyla ucuz bir
// "nebula" arka planı. Doku/HDR indirmeye gerek yok, düşük poligon (subdivision 3).
function NebulaBackdrop() {
  const geometry = useMemo(() => {
    const radius = 40;
    const geo = new THREE.IcosahedronGeometry(radius, 3);
    const position = geo.attributes.position;
    const colors = new Float32Array(position.count * 3);
    // Kullanıcı isteğiyle (2026-07-28) — gece gökyüzü, Platin + Buz Mavisi palet.
    // Neredeyse siyah; tepeye doğru çok hafif soğuk bir mavi yükseliyor. Amaç
    // "renk" değil derinlik: tamamen düz siyah bir küre, üzerindeki yıldız
    // alanını sahnenin geri kalanından kopuk gösteriyordu.
    // 2026-11-02, kullanıcı isteği: arka plan tamamen siyah — gradyan kapatıldı.
    const bottom = new THREE.Color('#000000');
    const top = new THREE.Color('#000000');
    const accent = new THREE.Color('#000000');
    const tmp = new THREE.Color();

    for (let i = 0; i < position.count; i++) {
      const t = (position.getY(i) / radius + 1) / 2;
      tmp
        .copy(bottom)
        .lerp(top, t)
        .lerp(accent, hash(i) * 0.1);
      colors[i * 3] = tmp.r;
      colors[i * 3 + 1] = tmp.g;
      colors[i * 3 + 2] = tmp.b;
    }

    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    return geo;
  }, []);

  return (
    <mesh geometry={geometry}>
      <meshBasicMaterial vertexColors side={THREE.BackSide} fog={false} />
    </mesh>
  );
}

export function Background() {
  const groupRef = useRef<THREE.Group>(null);

  useFrame((_, delta) => {
    if (groupRef.current) {
      groupRef.current.rotation.y += delta * BACKGROUND_ROTATION_SPEED;
    }
  });

  return (
    <group ref={groupRef}>
      <NebulaBackdrop />
      {/* Koyu zeminde gökyüzü hissi yıldızlardan geliyor. */}
      <Stars radius={70} depth={50} count={6000} factor={3} saturation={0} fade speed={0.4} />
      {/* İki katman toz: yakın/seyrek buz mavisi + uzak/yoğun platin. Opaklıklar
          bilerek düşük — "parıltı" değil, çekirdeğin etrafındaki atmosferin
          ışığı yakalayan zerreleri gibi okunmalı.
          drei'nin <Sparkles> bileşeni kullanıcı isteğiyle (2026-07-29) kaldırıldı:
          kameraya yaklaşan bir parçacık sahneyi karartan dev bir kareye dönüşüyordu
          — ayrıntı için bkz. shaders/dustField.ts. */}
      <DustField
        count={55}
        scale={[20, 12, 20]}
        size={1.8}
        speed={0.18}
        opacity={0.3}
        color="#7fb2ff"
      />
      <DustField
        count={40}
        scale={[16, 9, 16]}
        size={1.2}
        speed={0.13}
        opacity={0.26}
        color="#e8eef7"
      />
    </group>
  );
}
