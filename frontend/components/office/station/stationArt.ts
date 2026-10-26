// Ajan İstasyonu — piksel çizimleri (adım 5, 2026-10-26).
//
// Kullanıcı kararı (2026-10-25): ofis 3D hologram yerine 2D pixel-art UZAY İSTASYONU.
// Sebep kaynak: 7/24 açık duran ekran, telefonda okunurluk. Onaylanan taslak:
// Docs/onizleme/ajan-istasyonu.html — çizimler oradan, aynı ölçüyle taşındı.
//
// Dünya: x −7..7, z −5..5 birim; 1 birim = 16 px; tuval 224×160, CSS ile büyütülür
// (image-rendering: pixelated). Her şey dikdörtgenle çizilir, görsel dosya yok.

export const W = 224;
export const H = 160;
export const U = 16;
export const PX = (x: number) => Math.round((x + 7) * U);
export const PZ = (z: number) => Math.round((z + 5) * U);
export const AISLE_Z = 0.7;

export type Look = 'captain' | 'robot' | 'alien' | 'astro';
export type Pose = 'walk' | 'typing' | 'waiting' | 'idle' | 'sleep';
export type Screen = 'off' | 'on' | 'ok' | 'err';

export interface Point {
  x: number;
  z: number;
}

export interface DeskSpot extends Point {
  w: number;
}

export const DESKS: Record<string, DeskSpot> = {
  jarvis: { x: 0, z: -2.9, w: 2.4 },
  terra: { x: -3.6, z: -0.9, w: 1.7 },
  gemini: { x: 3.6, z: -0.9, w: 1.7 },
  alt: { x: -3.6, z: 2.8, w: 1.7 },
  bos: { x: 3.6, z: 2.8, w: 1.7 },
};
export const REST: Point = { x: -6.1, z: -2.6 };
export const TERM: Point = { x: 6.2, z: -2.6 };
export const seat = (id: string): Point => ({ x: DESKS[id].x, z: DESKS[id].z + 0.85 });

export interface Figure {
  id: string;
  look: Look;
  color: string;
  x: number;
  z: number;
  face: number;
  pose: Pose;
  walkPhase: number;
}

type Rect = (x: number, y: number, w: number, h: number, c: string) => void;

const SKIN = '#f1c49c';
const WIN = { x: 8, y: 3, w: 208, h: 22 };

export function rectOf(ctx: CanvasRenderingContext2D): Rect {
  return (x, y, w, h, c) => {
    ctx.fillStyle = c;
    ctx.fillRect(x | 0, y | 0, w | 0, h | 0);
  };
}

// ── Karakterler ────────────────────────────────────────────────────────────
export function drawFigure(R: Rect, a: Figure, x: number, y: number, t: number): void {
  const walking = a.pose === 'walk';
  const f = walking ? Math.floor(a.walkPhase / Math.PI) % 2 : 0;
  const up = walking && Math.cos(a.face) < -0.5;
  const sx = walking && Math.abs(Math.sin(a.face)) > 0.7 ? Math.sign(Math.sin(a.face)) : 0;
  const b = walking ? f : a.pose === 'typing' ? Math.floor(t * 6) % 2 : 0;
  const arm = a.pose === 'typing' ? Math.floor(t * 8) % 2 : walking ? f : 0;
  const blink = Math.floor(t * 2) % 2;
  const eyeX = sx > 0 ? 1 : sx < 0 ? -1 : 0;
  R(x - 4, y, 9, 2, 'rgba(0,0,0,.4)');
  const legs = { captain: '#1c2142', robot: '#6b778f', alien: '#4f3882', astro: '#cfd6e6' }[a.look];
  R(x - 3, y - 4, 2, 4 - (f ? 1 : 0), legs);
  R(x + 1, y - 4, 2, 4 - (f ? 0 : 1), legs);
  if (a.look === 'captain') {
    if (!up) R(x - 5, y - 9 + b, 10, 7, '#7a1f3d');
    R(x - 4, y - 10 + b, 8, 7, '#2f4fa8');
    R(x - 4, y - 10 + b, 2, 1, '#f2c94c');
    R(x + 2, y - 10 + b, 2, 1, '#f2c94c');
    R(x - 4, y - 5 + b, 8, 1, '#f2c94c');
    if (up) R(x - 4, y - 9 + b, 8, 6, '#7a1f3d');
    R(x - 5, y - 9 + b + arm, 1, 4, '#2f4fa8');
    R(x + 4, y - 9 + b + (1 - arm), 1, 4, '#2f4fa8');
    R(x - 3, y - 16 + b, 6, 6, SKIN);
    R(x - 3, y - 17 + b, 6, up ? 6 : 2, '#2a2f45');
    if (!up) {
      R(x - 2 + eyeX, y - 14 + b, 1, 1, '#14163a');
      R(x + 1 + eyeX, y - 14 + b, 1, 1, '#14163a');
    }
  } else if (a.look === 'robot') {
    R(x - 4, y - 10 + b, 8, 7, '#9aa7bd');
    R(x - 4, y - 4 + b, 8, 1, '#6b778f');
    if (!up) R(x - 1, y - 8 + b, 2, 2, blink ? a.color : '#1d3b3a');
    R(x - 5, y - 9 + b + arm, 1, 4, '#7c889f');
    R(x + 4, y - 9 + b + (1 - arm), 1, 4, '#7c889f');
    R(x - 3, y - 16 + b, 6, 5, '#b8c3d6');
    R(x - 3, y - 12 + b, 6, 1, '#8e99ae');
    if (!up) R(x - 2 + eyeX, y - 14 + b, 4, 1, a.pose === 'sleep' ? '#2d3a4a' : a.color);
    R(x, y - 19 + b, 1, 3, '#6b778f');
    R(x, y - 20 + b, 1, 1, blink && a.pose !== 'sleep' ? a.color : '#2d3a4a');
  } else if (a.look === 'alien') {
    R(x - 4, y - 10 + b, 8, 8, '#6d4bb5');
    R(x - 1, y - 10 + b, 2, 8, '#8a68d1');
    R(x - 5, y - 9 + b + arm, 1, 4, '#b794f6');
    R(x + 4, y - 9 + b + (1 - arm), 1, 4, '#b794f6');
    R(x - 4, y - 17 + b, 8, 7, '#b794f6');
    R(x - 3, y - 18 + b, 6, 1, '#b794f6');
    if (!up) {
      R(x - 3 + eyeX, y - 14 + b, 2, 2, '#14101f');
      R(x + 1 + eyeX, y - 14 + b, 2, 2, '#14101f');
      R(x - 3 + eyeX, y - 14 + b, 1, 1, '#ffffff');
    }
    R(x - 3, y - 20 + b, 1, 2, '#9a78e0');
    R(x + 2, y - 20 + b, 1, 2, '#9a78e0');
    R(x - 3, y - 21 + b, 1, 1, '#f0a6e8');
    R(x + 2, y - 21 + b, 1, 1, '#f0a6e8');
  } else {
    if (up) R(x - 3, y - 11 + b, 6, 6, '#b9c1d3');
    R(x - 4, y - 10 + b, 8, 7, '#e8ecf5');
    R(x - 4, y - 7 + b, 8, 1, a.color);
    if (up) R(x - 3, y - 10 + b, 6, 5, '#b9c1d3');
    R(x - 5, y - 9 + b + arm, 1, 4, '#d5dbe8');
    R(x + 4, y - 9 + b + (1 - arm), 1, 4, '#d5dbe8');
    R(x - 4, y - 17 + b, 8, 7, '#f4f6fb');
    R(x - 4, y - 11 + b, 8, 1, '#c3cadb');
    if (!up) {
      R(x - 3 + eyeX, y - 15 + b, 6, 4, '#2a1f4a');
      R(x - 2 + eyeX, y - 15 + b, 2, 1, a.color);
    }
  }
  if (a.pose === 'waiting') {
    R(x + 4, y - 27, 6, 8, '#ffb020');
    R(x + 5, y - 26, 4, 1, '#14163a');
    R(x + 8, y - 25, 1, 2, '#14163a');
    R(x + 6, y - 23, 2, 1, '#14163a');
    R(x + 6, y - 21, 2, 1, '#14163a');
  }
  if (a.pose === 'sleep') {
    const k = Math.floor(t * 1.5) % 3;
    for (let i = 0; i <= k; i++) R(x + 4 + i * 3, y - 22 - i * 3, 2, 2, '#c9d2ea');
  }
}

// ── Sahnenin sabit katmanı (bir kez çizilir) ────────────────────────────────
export function paintBackground(c: CanvasRenderingContext2D): void {
  const B = rectOf(c);
  B(0, 0, W, 30, '#151a33');
  for (let ty = 2; ty < 10; ty++)
    for (let tx = 0; tx < 14; tx++) {
      const X = tx * 16;
      const Y = ty * 16 - 2;
      B(X, Y, 16, 16, (tx + ty) % 2 ? '#262c45' : '#2b324e');
      B(X, Y, 16, 1, '#1c2137');
      B(X, Y, 1, 16, '#1c2137');
      for (const [dx, dy] of [[2, 2], [13, 2], [2, 13], [13, 13]]) B(X + dx, Y + dy, 1, 1, '#465075');
    }
  B(0, 28, W, 2, '#3c4570');
  B(0, 30, W, 1, '#0d1022');
  // Kaptan platformu
  const px = PX(0);
  const pz = PZ(-2.9);
  B(px - 30, pz - 2, 60, 30, '#2e2560');
  B(px - 28, pz, 56, 26, '#3a2f78');
  B(px - 28, pz + 25, 56, 1, '#7a6be0');
  // Dinlenme kapsülü + cam kubbede bitki
  const rx = PX(REST.x);
  const rz = PZ(REST.z);
  B(rx - 10, rz - 12, 16, 20, '#3a4365');
  B(rx - 9, rz - 11, 14, 18, '#4b5680');
  B(rx - 7, rz - 9, 10, 8, '#0c1a2e');
  B(rx - 6, rz - 8, 3, 2, '#7fe3ff');
  B(rx - 7, rz + 1, 4, 3, '#1d2236');
  B(rx - 1, rz + 2, 3, 2, '#ff6b6b');
  B(rx + 8, rz - 2, 10, 9, '#5a6488');
  B(rx + 9, rz - 8, 8, 7, '#1f3d55');
  B(rx + 10, rz - 6, 6, 4, '#3fae62');
  B(rx + 12, rz - 8, 2, 3, '#56cc7a');
  B(rx + 10, rz - 8, 1, 2, '#9fd8ff');
  // Onay terminali
  const tx = PX(TERM.x);
  const tz = PZ(TERM.z);
  B(tx - 6, tz - 14, 14, 22, '#3a4365');
  B(tx - 5, tz - 13, 12, 20, '#4b5680');
  B(tx - 4, tz - 11, 10, 7, '#0c1a2e');
  B(tx - 4, tz - 2, 3, 2, '#ffb020');
  B(tx, tz - 2, 3, 2, '#7ee0b5');
  B(tx + 4, tz - 2, 2, 2, '#ff5d6c');
  for (let x = 4; x < W; x += 16) B(x, PZ(AISLE_Z) + 3, 8, 1, '#1b5f7a');
}

const STARS = Array.from({ length: 70 }, (_, i) => {
  const r = Math.sin(i * 12.9898) * 43758.5453;
  const r2 = Math.sin(i * 78.233) * 12345.678;
  return {
    x: (r - Math.floor(r)) * WIN.w,
    y: (r2 - Math.floor(r2)) * WIN.h,
    s: 2 + (i % 3) * 3,
    c: i % 7 === 0 ? '#ffd9a0' : i % 5 === 0 ? '#a8c8ff' : '#ffffff',
  };
});

export function paintPlanet(c: CanvasRenderingContext2D): void {
  const cx = 22;
  const cy = 13;
  const r = 9;
  for (let y = 0; y < 26; y++)
    for (let x = 0; x < 44; x++) {
      const dx = x - cx;
      const dy = y - cy;
      const d = dx * dx + dy * dy;
      if (d < r * r) {
        let col = ['#e07a5f', '#f2cc8f', '#c9654d'][Math.floor((dy + r) / 3) % 3];
        if (dx > 4 && d > (r - 3) * (r - 3)) col = '#7a3b30';
        if (dx < -3 && dy < -2 && d > (r - 3) * (r - 3)) col = '#ffe1b3';
        c.fillStyle = col;
        c.fillRect(x, y, 1, 1);
      }
      const e = (dx * dx) / 400 + (dy * dy) / 16;
      if (e > 0.82 && e < 1.0 && !(d < r * r && dy < 0)) {
        c.fillStyle = '#d8c3ff';
        c.fillRect(x, y, 1, 1);
      }
    }
}

export function drawWindow(ctx: CanvasRenderingContext2D, planet: HTMLCanvasElement, t: number): void {
  const R = rectOf(ctx);
  R(WIN.x, WIN.y, WIN.w, WIN.h, '#03040c');
  ctx.save();
  ctx.beginPath();
  ctx.rect(WIN.x, WIN.y, WIN.w, WIN.h);
  ctx.clip();
  for (const s of STARS) R(WIN.x + ((((s.x - t * s.s) % WIN.w) + WIN.w) % WIN.w), WIN.y + s.y, 1, 1, s.c);
  ctx.drawImage(planet, Math.round(WIN.x + WIN.w + 10 - ((t * 1.6) % (WIN.w + 60))), WIN.y - 2);
  const cyc = t % 16;
  if (cyc < 5) {
    const sx = WIN.x - 14 + (cyc / 5) * (WIN.w + 28);
    const sy = WIN.y + 15;
    R(sx, sy, 9, 3, '#c9d2ea');
    R(sx + 6, sy - 1, 3, 1, '#c9d2ea');
    R(sx + 3, sy + 1, 3, 1, '#6fd3ff');
    R(sx - 3, sy + 1, 3, 1, Math.floor(t * 10) % 2 ? '#ffb347' : '#ff6b3d');
  }
  ctx.restore();
  R(WIN.x - 3, WIN.y - 2, WIN.w + 6, 2, '#5a6596');
  R(WIN.x - 3, WIN.y + WIN.h, WIN.w + 6, 2, '#5a6596');
  for (let x = WIN.x - 3; x <= WIN.x + WIN.w; x += 52) R(x, WIN.y - 2, 3, WIN.h + 4, '#5a6596');
}

export function drawAisleLights(R: Rect, t: number): void {
  for (let x = 4; x < W; x += 16) if ((Math.floor(t * 2) + x / 16) % 6 === 0) R(x + 3, PZ(AISLE_Z) + 3, 2, 1, '#6fd3ff');
}

export function drawTerminal(R: Rect, waiting: boolean, t: number): void {
  const tx = PX(TERM.x);
  const tz = PZ(TERM.z);
  const on = Math.floor(t * 4) % 2 === 1;
  R(tx - 1, tz - 17, 4, 3, waiting && on ? '#ffb020' : '#5a3d10');
  if (waiting) {
    R(tx - 4, tz - 11, 10, 7, on ? '#ffb020' : '#3a2a08');
  } else {
    R(tx - 3, tz - 10, 2, 1, '#7ee0b5');
    R(tx - 3, tz - 8, 6, 1, '#2c6a55');
  }
}

export function drawConsole(
  ctx: CanvasRenderingContext2D,
  id: string,
  color: string,
  screen: Screen,
  t: number,
): void {
  const R = rectOf(ctx);
  const d = DESKS[id];
  const w = Math.round(d.w * U);
  const x = PX(d.x) - w / 2;
  const y = PZ(d.z) - 6;
  R(x + 2, y + 12, w - 4, 3, 'rgba(0,0,0,.4)');
  R(x, y, w, 12, '#3a4361');
  R(x, y, w, 3, '#5a668f');
  R(x, y + 11, w, 1, '#1e2438');
  for (let i = 0; i < Math.floor((w - 6) / 4); i++) {
    const lit = (Math.floor(t * 3) + i * 7 + id.length) % 4 === 0;
    R(x + 3 + i * 4, y + 6, 2, 1, lit ? ['#ff6b6b', '#7ee0b5', '#ffd166', '#6fd3ff'][i % 4] : '#262d45');
  }
  R(PX(d.x) - 4, y - 1, 8, 1, '#7d8bb3');
  const sw = Math.min(18, w - 6);
  const sx = PX(d.x) - sw / 2;
  const sy = y - 12;
  const on = screen !== 'off';
  const tint = screen === 'err' ? '#ff5d6c' : screen === 'ok' ? '#7ee0b5' : color;
  if (on || id === 'jarvis') {
    ctx.globalAlpha = on ? 0.6 : 0.3;
    R(sx, sy, sw, 10, tint);
    ctx.globalAlpha = on ? 0.9 : 0.4;
    for (let i = 0; i < 3; i++) R(sx + 2, sy + 2 + i * 3, 2 + (((t * 7 + i * 3) % (sw - 5)) | 0), 1, '#ffffff');
    ctx.globalAlpha = 1;
    R(sx, sy + 10, sw, 1, tint);
  } else {
    R(sx + 3, sy + 9, sw - 6, 1, '#2b3550');
  }
}

export function drawChair(R: Rect, id: string): void {
  const s = seat(id);
  const x = PX(s.x);
  const y = PZ(s.z);
  if (id === 'jarvis') {
    R(x - 7, y - 3, 14, 10, '#5b4fa3');
    R(x - 7, y + 6, 14, 2, '#3a2f78');
    R(x - 8, y - 1, 1, 6, '#7a6be0');
    R(x + 7, y - 1, 1, 6, '#7a6be0');
    return;
  }
  R(x - 5, y - 2, 10, 8, '#414a6e');
  R(x - 5, y + 5, 10, 2, '#2a3150');
}
