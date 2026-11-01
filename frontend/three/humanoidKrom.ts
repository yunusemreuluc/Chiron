import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { MeshSurfaceSampler } from 'three/examples/jsm/math/MeshSurfaceSampler.js';

// İnsan görünümünün "Krom" biçimi (2026-11-02, Yunus üç tur taslaktan bunu seçti;
// taslak sayfası: claude.ai/artifact/SnG67xU7wjc5PxP5gp3v9s).
//
// Kafa elle çizilmiyor: gerçek bir kafa taraması (Lee Perry-Smith, CC BY 3.0 —
// public/models/head-scan-LICENSE.txt) yüzeyinden rastgele örnekleniyor. İlk
// denemedeki elips büst manken gibi duruyordu; tarama burun, dudak, kulak ve
// omuzları kendiliğinden getiriyor.
//
// Koordinatlar taramanın kendi birimlerinde (y −4..4, yüz +z'ye bakıyor);
// HumanoidBust grubu ölçekliyor. Göz/çene sabitleri o birimlerde ölçüldü
// (önden derinlik haritasıyla, 2026-11-02).

export const HEAD_SCAN_URL = '/models/head-scan.glb';
export const EYE_X = 0.62;
export const EYE_Y = 1.62;
/** Kafa ve boyun bu noktanın etrafında dönüyor; omuzlar sabit. */
export const NECK_PIVOT_Y = -1.3;

export const PART_SURFACE = 0;
export const PART_SEAM = 1;
export const PART_EYE = 2;
export const PART_CORE = 3;

const SAMPLES = 150_000;

let seed = 11;
const rnd = () => {
  seed = (seed * 16807) % 2147483647;
  return (seed - 1) / 2147483646;
};

function sampleScan(mesh: THREE.Mesh) {
  const sampler = new MeshSurfaceSampler(mesh).build();
  const P = new Float32Array(SAMPLES * 3);
  const N = new Float32Array(SAMPLES * 3);
  const v = new THREE.Vector3();
  const n = new THREE.Vector3();
  for (let i = 0; i < SAMPLES; i++) {
    sampler.sample(v, n);
    P[i * 3] = v.x;
    P[i * 3 + 1] = v.y;
    P[i * 3 + 2] = v.z;
    N[i * 3] = n.x;
    N[i * 3 + 1] = n.y;
    N[i * 3 + 2] = n.z;
  }

  // Taramada ağız boşluğu gibi iç yüzeyler var; ışıkla toplanınca ağzın çevresinde
  // parlak bir kutu gibi görünüyorlardı. Önden bakan ızgarada dış yüzeyin (o
  // hücrenin en öndeki noktası) belirgin biçimde gerisinde kalanlar atılıyor.
  const cell = 0.06;
  const key = (x: number, y: number) => `${Math.round(x / cell)}:${Math.round(y / cell)}`;
  const front = new Map<string, number>();
  for (let i = 0; i < SAMPLES; i++) {
    const k = key(P[i * 3], P[i * 3 + 1]);
    const z = P[i * 3 + 2];
    if (!(front.get(k)! > z)) front.set(k, z);
  }
  let m = 0;
  for (let i = 0; i < SAMPLES; i++) {
    const x = P[i * 3];
    const y = P[i * 3 + 1];
    const z = P[i * 3 + 2];
    const inner = Math.abs(x) < 0.95 && y > -0.45 && y < 2.05 && z > 0.3 && z < front.get(key(x, y))! - 0.12;
    if (inner) continue;
    for (let d = 0; d < 3; d++) {
      P[m * 3 + d] = P[i * 3 + d];
      N[m * 3 + d] = N[i * 3 + d];
    }
    m++;
  }

  // Göz yüzeyinin derinliği: göz merkezine yakın örneklerin en öndekisi.
  const eyeZ = [-1, 1].map((sx) => {
    let best = 0;
    for (let i = 0; i < m; i++) {
      const dx = P[i * 3] - sx * EYE_X;
      const dy = P[i * 3 + 1] - EYE_Y;
      if (dx * dx + dy * dy < 0.02 && P[i * 3 + 2] > best) best = P[i * 3 + 2];
    }
    return best;
  });
  return { P, N, count: m, eyeZ };
}

function buildKrom(scan: ReturnType<typeof sampleScan>): THREE.BufferGeometry {
  const pos: number[] = [];
  const part: number[] = [];
  const tint: number[] = [];
  const alpha: number[] = [];
  const add = (x: number, y: number, z: number, p: number, t: number, a: number) => {
    pos.push(x, y, z);
    part.push(p);
    tint.push(t);
    alpha.push(a);
  };

  // Sol üst önden gelen ışık — gümüşün heykel gibi okunmasını sağlayan şey bu gölgeleme.
  const L = new THREE.Vector3(0.45, 0.55, 0.7).normalize();
  const { P, N, count, eyeZ } = scan;
  for (let i = 0; i < count; i++) {
    const x = P[i * 3];
    const y = P[i * 3 + 1];
    const z = P[i * 3 + 2];
    const lit = Math.max(0, N[i * 3] * L.x + N[i * 3 + 1] * L.y + N[i * 3 + 2] * L.z);
    const back = z < -0.2 ? 0.55 : 1;
    const r = rnd();
    // Panel dikişleri: alnın ortası, alın bandı, çene hattı, boyun halkaları.
    const seam =
      (y > 0.6 && Math.abs(x) < 0.025) ||
      Math.abs(y - 2.75) < 0.025 ||
      Math.abs(y) < 0.02 ||
      (y < -0.5 && y > -2.2 && Math.abs(y / 0.28 - Math.round(y / 0.28)) < 0.05);
    if (seam && r < 0.9) add(x, y, z, PART_SEAM, 1, 0.95);
    else if (r < 0.42) add(x, y, z, PART_SURFACE, 0, (0.18 + 0.82 * lit) * back);
  }

  for (const sx of [-1, 1]) {
    for (let k = 0; k < 260; k++) {
      const t = rnd() * Math.PI * 2;
      const rr = Math.sqrt(rnd()) * 0.17;
      add(sx * EYE_X + Math.cos(t) * rr, EYE_Y + Math.sin(t) * rr * 0.62, eyeZ[sx < 0 ? 0 : 1] + 0.04, PART_EYE, 2, 1);
    }
  }
  for (let k = 0; k < 900; k++) {
    const t = rnd() * Math.PI * 2;
    const rr = Math.sqrt(rnd()) * 0.42;
    add(Math.cos(t) * rr, -3.05 + Math.sin(t) * rr, 1.05, PART_CORE, 3, 1);
  }

  const n = part.length;
  const seeds = new Float32Array(n * 3);
  const delay = new Float32Array(n);
  for (let k = 0; k < n; k++) {
    seeds[k * 3] = rnd();
    seeds[k * 3 + 1] = rnd();
    seeds[k * 3 + 2] = rnd();
    // Aşağıdan yukarı toplanıyor: önce omuzlar, en son kafanın tepesi.
    delay[k] = Math.min(1, ((pos[k * 3 + 1] + 4) / 8) * 0.75 + rnd() * 0.25);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geometry.setAttribute('aSeed', new THREE.BufferAttribute(seeds, 3));
  geometry.setAttribute('aPart', new THREE.Float32BufferAttribute(part, 1));
  geometry.setAttribute('aTint', new THREE.Float32BufferAttribute(tint, 1));
  geometry.setAttribute('aA', new THREE.Float32BufferAttribute(alpha, 1));
  geometry.setAttribute('aDelay', new THREE.BufferAttribute(delay, 1));
  // Sürü hâlindeyken parçacıklar sınır kutusunun çok dışına çıkıyor.
  geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 40);
  return geometry;
}

let cached: Promise<THREE.BufferGeometry> | null = null;

/** Taramayı bir kez indirir, örnekler ve Krom geometrisini kurar (~150 ms). */
export function loadKromGeometry(): Promise<THREE.BufferGeometry> {
  cached ??= new GLTFLoader().loadAsync(HEAD_SCAN_URL).then((gltf) => {
    let mesh: THREE.Mesh | null = null;
    gltf.scene.traverse((child) => {
      if (!mesh && (child as THREE.Mesh).isMesh) mesh = child as THREE.Mesh;
    });
    if (!mesh) throw new Error('Kafa taramasında mesh yok');
    seed = 11;
    return buildKrom(sampleScan(mesh));
  });
  // Ağ hatasında önbellek zehirlenmesin: bir sonraki açılış yeniden denesin.
  cached.catch(() => {
    cached = null;
  });
  return cached;
}
