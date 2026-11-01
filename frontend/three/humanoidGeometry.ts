import * as THREE from 'three';

// İnsan görünümünün parçacık hedefleri — açılışta BİR KEZ hesaplanıyor, sonra
// yalnızca shader hareket ettiriyor (three/shaders/humanoid.ts).
//
// Büst bir model dosyası değil, matematik: her yükseklikte (y) bir elips
// kesit (yarı genişlik a, yarı derinlik b, öne kayma cz). Parçacıklar bu
// kesitlerin ÇEVRESİNE diziliyor; önden bakınca yüzün üstünden geçen yatay
// kontur çizgileri oluşturuyor. Burun, kaş ve çene, ön yüzeye eklenen küçük
// Gauss tümsekleri. Model dosyası olmadığı için lisans, indirme ve yükleme
// süresi de yok.

// Deterministik sözde-rastgele — DustField/EnergyTendrils ile aynı desen.
function hash(seed: number): number {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

const smoothstep = (e0: number, e1: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - e0) / (e1 - e0)));
  return t * t * (3 - 2 * t);
};

// Kesitleri dikişsiz birleştiren yumuşak maksimum (polinom smax).
function smax(a: number, b: number, k: number): number {
  const h = Math.max(k - Math.abs(a - b), 0) / k;
  return Math.max(a, b) + h * h * k * 0.25;
}

export const BUST_Y_MIN = -2.7;
export const BUST_Y_MAX = 3.04;
/** Kafanın dönme ekseni — boyun ortası. Shader ve yüz parıltısı aynı noktayı kullanıyor. */
export const HEAD_PIVOT_Y = 0.6;
/** Yüzün turuncu çekirdeğinin merkezi. */
export const FACE_CENTER = new THREE.Vector3(0, 1.62, 0.75);

interface Section {
  a: number;
  b: number;
  cz: number;
}

function section(y: number): Section {
  // Kafa: hafif basık bir elipsoit, alta doğru (çene) daralıyor.
  const th = (y - 1.75) / 1.3;
  const base = Math.abs(th) < 1 ? Math.sqrt(1 - th * th) : 0;
  const headA = 0.94 * base * (th < 0 ? 1 - 0.3 * th * th : 1);
  const headB = 1.08 * base;

  // Boyun: iki ucu yumuşakça sönen silindir.
  const neckMask = smoothstep(-0.75, -0.35, y) * (1 - smoothstep(0.75, 1.05, y));
  const neckA = 0.42 * neckMask;
  const neckB = 0.44 * neckMask;

  // Omuzlar/göğüs: boyun dibinden üstel bir eğriyle açılan kubbe.
  // Omuzlar hızlı açılıyor (geniş, eğimli), sonra göğüs neredeyse dik iniyor.
  // Trapez kası: boyundan omuz ucuna eğimli iniş (üstel), omuz başında yuvarlanma.
  const f = y < 0.05 ? 1 - Math.exp(-(0.05 - y) / 0.62) : 0;
  const torsoA = 2.95 * f;
  const torsoB = f > 0 ? 0.32 + 0.78 * f : 0;

  return {
    a: smax(smax(headA, neckA, 0.12), torsoA, 0.2),
    b: smax(smax(headB, neckB, 0.12), torsoB, 0.2),
    cz: 0.1 * smoothstep(0.6, 1.0, y) - 0.05 * f,
  };
}

const gauss = (v: number, s: number) => Math.exp(-(v * v) / (s * s));

/** Ön yüzeydeki yüz hatları (yalnız kafa bölgesinde, önden bakan noktalarda). */
function faceRelief(x: number, y: number): number {
  const nose = 0.19 * gauss(x, 0.11) * gauss(y - 1.52, 0.23);
  const brow = 0.07 * gauss(y - 1.95, 0.09) * gauss(x, 0.54);
  const eyes = -0.08 * gauss(Math.abs(x) - 0.32, 0.15) * gauss(y - 1.8, 0.1);
  const lips = 0.05 * gauss(x, 0.24) * gauss(y - 1.2, 0.07);
  const chin = 0.06 * gauss(x, 0.26) * gauss(y - 0.93, 0.12);
  return nose + brow + eyes + lips + chin;
}

/** Göğsün ön yüzeyindeki z (damarların yüzeye yapışması için). */
function frontSurfaceZ(x: number, y: number): number {
  const s = section(y);
  const u = s.a > 0 ? Math.min(1, Math.abs(x) / s.a) : 1;
  return s.cz + s.b * Math.sqrt(Math.max(0, 1 - u * u));
}

// Parçacık türleri (aKind): shader her birine farklı davranıyor.
export const KIND_SURFACE = 0;
export const KIND_VEIN = 1;
export const KIND_HALO = 2;

const RING_STEP = 0.042;
const DENSITY = 58; // çevre birimi başına parçacık

export function buildBustGeometry(): THREE.BufferGeometry {
  const pos: number[] = [];
  const seed: number[] = [];
  const tint: number[] = [];
  const delay: number[] = [];
  const kind: number[] = [];
  let n = 0;

  const push = (x: number, y: number, z: number, t: number, k: number, d?: number) => {
    pos.push(x, y, z);
    seed.push(hash(n * 3.1 + 0.7), hash(n * 3.1 + 1.9), hash(n * 3.1 + 2.7));
    tint.push(t);
    kind.push(k);
    // Aşağıdan yukarı toplanıyor: önce göğüs, en son kafanın tepesi.
    const rise = (y - BUST_Y_MIN) / (BUST_Y_MAX - BUST_Y_MIN);
    delay.push(d ?? Math.min(1, rise * 0.75 + hash(n * 7.7 + 0.3) * 0.25));
    n += 1;
  };

  // ── Yüzey konturları ──
  for (let y = BUST_Y_MIN; y <= BUST_Y_MAX; y += RING_STEP) {
    const s = section(y);
    if (s.a < 0.02) continue;
    const perimeter = 2 * Math.PI * Math.sqrt((s.a * s.a + s.b * s.b) / 2);
    // Gövde kadrajın altına doğru zaten sönüyor — daha seyrek.
    const density = y < -0.2 ? DENSITY * 0.72 : DENSITY;
    const count = Math.max(24, Math.round(perimeter * density));
    const inHead = y > 0.7;
    for (let j = 0; j < count; j++) {
      const theta = ((j + hash(n * 1.3 + j) * 0.5) / count) * Math.PI * 2;
      const x = Math.cos(theta) * s.a;
      const front = Math.max(0, Math.sin(theta));
      let z = Math.sin(theta) * s.b + s.cz;
      if (inHead) z += faceRelief(x, y) * front * front;
      // Yüzün turuncu çekirdeği: önden bakan, yüz merkezine yakın konturlar.
      const faceMask = Math.pow(front, 1.5) * gauss(x, 0.62) * gauss(y - 1.62, 0.62);
      push(x, y, z, smoothstep(0.15, 0.75, faceMask), KIND_SURFACE);
    }
  }

  // ── Boyun damarları: göğüsten yukarı tırmanan altın iplikler ──
  for (let v = 0; v < 7; v++) {
    let x = (hash(v * 9.1 + 4.2) - 0.5) * 0.9;
    for (let y = -1.1 + hash(v * 3.7) * 0.4; y <= 1.05; y += 0.02) {
      // İplikler boyuna doğru toplanıyor, boynun genişliğinde dolanıyor.
      const pull = smoothstep(-0.8, 0.0, y);
      x = x * (1 - 0.04 * pull) + (hash(v * 31.7 + y * 97.1) - 0.5) * 0.035;
      const z = frontSurfaceZ(x, y) + 0.025;
      push(x, y, z, 0.9, KIND_VEIN);
      if (hash(v * 5.3 + y * 41.9) > 0.55) {
        push(x + (hash(y * 13.1 + v) - 0.5) * 0.08, y, z + 0.01, 0.75, KIND_VEIN);
      }
    }
  }

  // ── Hale: kafanın arkasında eş merkezli halkalar (konuşurken dalgalanır) ──
  const HALO_RINGS = 7;
  for (let r = 0; r < HALO_RINGS; r++) {
    const radius = 1.8 + r * 0.32;
    const count = Math.round(radius * 2 * Math.PI * 34);
    for (let j = 0; j < count; j++) {
      const theta = (j / count) * Math.PI * 2;
      const x = Math.cos(theta) * radius;
      const y = 1.65 + Math.sin(theta) * radius;
      push(x, y, -0.45, 0, KIND_HALO, 0.55 + r * 0.06);
      // aSeed.z halka sırası olsun: shader dalgayı halkadan halkaya yürütüyor.
      seed[seed.length - 1] = r / (HALO_RINGS - 1);
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geometry.setAttribute('aSeed', new THREE.Float32BufferAttribute(seed, 3));
  geometry.setAttribute('aTint', new THREE.Float32BufferAttribute(tint, 1));
  geometry.setAttribute('aDelay', new THREE.Float32BufferAttribute(delay, 1));
  geometry.setAttribute('aKind', new THREE.Float32BufferAttribute(kind, 1));
  // Parçacıklar sürü hâlindeyken sınır kutusunun çok dışına çıkıyor —
  // frustum culling büstü yanlışlıkla gizlemesin.
  geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0, 0), 30);
  return geometry;
}

// ── Arka plan: iki yanda parçacık dağları ─────────────────────────────────
function valueNoise(x: number, z: number): number {
  const ix = Math.floor(x);
  const iz = Math.floor(z);
  const fx = x - ix;
  const fz = z - iz;
  const h = (a: number, b: number) => hash(a * 127.1 + b * 311.7);
  const u = fx * fx * (3 - 2 * fx);
  const v = fz * fz * (3 - 2 * fz);
  const top = h(ix, iz) * (1 - u) + h(ix + 1, iz) * u;
  const bottom = h(ix, iz + 1) * (1 - u) + h(ix + 1, iz + 1) * u;
  return top * (1 - v) + bottom * v;
}

function fbm(x: number, z: number): number {
  let sum = 0;
  let amp = 0.5;
  let freq = 1;
  for (let o = 0; o < 5; o++) {
    sum += valueNoise(x * freq, z * freq) * amp;
    freq *= 2.03;
    amp *= 0.5;
  }
  return sum / 0.97;
}

export function buildRangeGeometry(): THREE.BufferGeometry {
  const pos: number[] = [];
  const seed: number[] = [];
  const tint: number[] = [];
  const delay: number[] = [];
  let n = 0;

  for (let x = -17; x <= 17; x += 0.1) {
    // Ortası boş: dağlar büstün iki yanında yükseliyor, arkasında değil.
    const side = smoothstep(2.4, 8, Math.abs(x));
    if (side < 0.02) continue;
    for (let z = -13; z <= -3; z += 0.11) {
      const jx = x + (hash(n * 2.1 + 0.4) - 0.5) * 0.08;
      const jz = z + (hash(n * 2.1 + 1.2) - 0.5) * 0.1;
      const ridge = Math.pow(fbm(jx * 0.28 + 3.1, jz * 0.28), 1.6);
      const height = ridge * 6.2 * side;
      const y = -3.2 + height;
      // Turuncu "lav" çizgileri: ikinci bir gürültünün eş-değer eğrisi.
      const flow = fbm(jx * 0.35 + 10, jz * 0.35 - 4);
      const line = 1 - smoothstep(0, 0.035, Math.abs(flow - 0.5));
      const sparkle = hash(n * 4.7 + 2.2) > 0.985 ? 0.8 : 0;
      pos.push(jx, y, jz);
      seed.push(hash(n * 3.3 + 0.1), hash(n * 3.3 + 1.7), Math.min(1, height / 6.2));
      tint.push(Math.max(line * smoothstep(0.1, 0.45, height / 6.2), sparkle));
      delay.push(Math.min(1, ((Math.abs(x) - 2.6) / 14) * 0.6 + hash(n * 6.1) * 0.3));
      n += 1;
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geometry.setAttribute('aSeed', new THREE.Float32BufferAttribute(seed, 3));
  geometry.setAttribute('aTint', new THREE.Float32BufferAttribute(tint, 1));
  geometry.setAttribute('aDelay', new THREE.Float32BufferAttribute(delay, 1));
  return geometry;
}
