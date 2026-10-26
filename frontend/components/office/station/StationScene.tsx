'use client';

import { useEffect, useRef, type MouseEvent } from 'react';
import { fetchPano } from '@/services/panoApi';
import { useOfficeStore, type OfficeSnapshot, type WorkerStatus } from '@/stores/officeStore';
import {
  AISLE_Z,
  DESKS,
  H,
  PX,
  PZ,
  TERM,
  W,
  drawAisleLights,
  drawChair,
  drawConsole,
  drawFigure,
  drawTerminal,
  drawWindow,
  paintBackground,
  paintPlanet,
  rectOf,
  seat,
  type Figure,
  type Look,
  type Point,
  type Pose,
  type Screen,
} from './stationArt';

// Ajan İstasyonu sahnesi (adım 5, 2026-10-26) — 3D hologram ofisin yerine.
// Karakterler ofisin GERÇEK verisinden yürür (backend/core/ofis.py masaları):
//   Jarvis ← claude · Terra ← sol/astra (Codex) · Gemini ← gemini · Alt ajan ← subagents
// Masa çalışıyorsa konsoluna gider ve yazar, onay bekliyorsa onay terminaline gider,
// boşta ise dinlenme kapsülüne döner. Terra'nın kotası doluyken kapsülde uyur.
//
// Performans (Faz 0 hedefi, kullanıcı kararı "2D daha az GPU"): 224×160 tuval, saniyede
// 15 kare, sekme gizliyken / pano açıkken hiç çizilmez. Etiketler React'e değil doğrudan
// DOM'a yazılır — kare başına yeniden render yok.

const FPS = 15;
const SPEED = 2.3;
const RECENT_DONE = 60; // sn — bitince konsol bu kadar yeşil kalır
const RECENT_FAIL = 180;

interface Member {
  id: keyof typeof DESKS;
  name: string;
  look: Look;
  color: string;
  desks: string[];
  home: Point;
}

// Ev konumları dinlenme kapsülünün önünde, dikeyde ≥1,5 birim aralıklı: isim etiketleri
// (22 px yukarıda) üst üste binmesin (ilk ekran görüntüsünde biniyordu).
const CREW: Member[] = [
  { id: 'jarvis', name: 'Jarvis', look: 'captain', color: '#7aa2ff', desks: ['claude'], home: seat('jarvis') },
  { id: 'terra', name: 'Terra', look: 'robot', color: '#4fd1c5', desks: ['sol', 'astra'], home: { x: -5.4, z: -1.9 } },
  { id: 'gemini', name: 'Gemini', look: 'alien', color: '#b794f6', desks: ['gemini'], home: { x: -6.1, z: -0.4 } },
  { id: 'alt', name: 'Alt ajan', look: 'astro', color: '#f0a6e8', desks: ['subagents'], home: { x: -6.0, z: 1.2 } },
];

type Mood = 'work' | 'wait' | 'fail' | 'done' | 'idle' | 'sleep';

interface Goal {
  mood: Mood;
  desk: string;
  text: string;
}

/** Ekibin bir üyesi şu an ne yapıyor — masaların ve işçilerin gerçek durumundan. */
function goalOf(m: Member, snap: OfficeSnapshot | null, codexBlocked: boolean): Goal {
  const fallback = m.desks[0];
  if (!snap) return { mood: m.id === 'terra' && codexBlocked ? 'sleep' : 'idle', desk: fallback, text: '' };
  const workers = snap.workers.filter((w) => m.desks.includes(w.desk));
  const pick = (statuses: WorkerStatus[]) =>
    workers.filter((w) => statuses.includes(w.status)).sort((a, b) => b.last_ts - a.last_ts)[0];
  const waiting = pick(['onay_bekliyor']);
  if (waiting) return { mood: 'wait', desk: waiting.desk, text: 'Onayın bekleniyor' };
  const busy = pick(['calisiyor']);
  if (busy) return { mood: 'work', desk: busy.desk, text: busy.current || busy.title };
  const failed = pick(['hata']);
  if (failed && snap.now - (failed.ended ?? failed.last_ts) < RECENT_FAIL) return { mood: 'fail', desk: failed.desk, text: 'Hata' };
  const done = pick(['bitti']);
  if (done && snap.now - (done.ended ?? done.last_ts) < RECENT_DONE) return { mood: 'done', desk: done.desk, text: 'Bitti ✓' };
  return { mood: m.id === 'terra' && codexBlocked ? 'sleep' : 'idle', desk: fallback, text: '' };
}

interface Actor extends Figure {
  path: Point[];
  target: Point | null;
  rest: Pose;
  goal: Goal;
}

function targetOf(m: Member, goal: Goal, waitSlot: number): { at: Point; pose: Pose } {
  if (goal.mood === 'wait') return { at: { x: TERM.x - 0.5 - waitSlot * 0.7, z: TERM.z + 0.8 }, pose: 'waiting' };
  if (goal.mood === 'work') return { at: seat(m.id), pose: 'typing' };
  if (goal.mood === 'fail' || goal.mood === 'done') return { at: seat(m.id), pose: 'idle' };
  return { at: m.home, pose: goal.mood === 'sleep' ? 'sleep' : 'idle' };
}

function pathTo(from: Point, to: Point): Point[] {
  const pts: Point[] = [];
  if (Math.abs(from.x - to.x) > 0.3) pts.push({ x: from.x, z: AISLE_Z }, { x: to.x, z: AISLE_Z });
  pts.push({ x: to.x, z: to.z });
  return pts;
}

function step(a: Actor, m: Member, waitSlot: number, dt: number): void {
  const { at, pose } = targetOf(m, a.goal, waitSlot);
  if (!a.target || Math.hypot(a.target.x - at.x, a.target.z - at.z) > 0.05) {
    a.target = at;
    a.path = Math.hypot(a.x - at.x, a.z - at.z) > 0.05 ? pathTo(a, at) : [];
  }
  a.rest = pose;
  if (!a.path.length) {
    a.pose = pose;
    return;
  }
  a.pose = 'walk';
  let left = SPEED * dt;
  while (left > 0 && a.path.length) {
    const p = a.path[0];
    const dx = p.x - a.x;
    const dz = p.z - a.z;
    const dist = Math.hypot(dx, dz);
    if (dist < 1e-3) {
      a.path.shift();
      continue;
    }
    a.face = Math.atan2(dx, dz);
    const mv = Math.min(left, dist);
    a.x += (dx / dist) * mv;
    a.z += (dz / dist) * mv;
    left -= mv;
    if (mv === dist) a.path.shift();
  }
  a.walkPhase += dt * 9;
  if (!a.path.length) {
    a.pose = pose;
    a.face = Math.PI;
  }
}

function screenOf(goal: Goal): Screen {
  return goal.mood === 'work' ? 'on' : goal.mood === 'fail' ? 'err' : goal.mood === 'done' ? 'ok' : 'off';
}

export function StationScene({ paused }: { paused: boolean }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const labelRefs = useRef<Record<string, { tag: HTMLDivElement | null; bub: HTMLDivElement | null }>>({});
  const codexBlocked = useRef(false);
  const selectDesk = useOfficeStore((s) => s.selectDesk);

  // Terra'nın kotası (pano biliyor) — seyrek sorulur, sahne için yeterli.
  useEffect(() => {
    if (paused) return;
    let cancelled = false;
    const load = () =>
      void fetchPano().then((data) => {
        if (!cancelled && data?.agents?.codex) codexBlocked.current = !data.agents.codex.available;
      });
    load();
    const id = setInterval(load, 30_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [paused]);

  // Tuvali tam sayı katla büyüt: pikseller keskin kalsın.
  useEffect(() => {
    const wrap = wrapRef.current;
    const box = boxRef.current;
    if (!wrap || !box) return;
    const fit = () => {
      const avail = Math.min(wrap.clientWidth / W, wrap.clientHeight / H);
      const scale = avail >= 2 ? Math.floor(avail) : Math.max(1, avail);
      box.style.width = `${W * scale}px`;
      box.style.height = `${H * scale}px`;
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(wrap);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (paused) return;
    const canvas = canvasRef.current;
    const box = boxRef.current;
    if (!canvas || !box) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.imageSmoothingEnabled = false;
    const bg = document.createElement('canvas');
    bg.width = W;
    bg.height = H;
    paintBackground(bg.getContext('2d')!);
    const planet = document.createElement('canvas');
    planet.width = 44;
    planet.height = 26;
    paintPlanet(planet.getContext('2d')!);
    const R = rectOf(ctx);

    const actors = new Map<string, Actor>(
      CREW.map((m) => [
        m.id,
        {
          id: m.id,
          look: m.look,
          color: m.color,
          x: m.home.x,
          z: m.home.z,
          face: Math.PI,
          pose: 'idle' as Pose,
          walkPhase: 0,
          path: [],
          target: null,
          rest: 'idle' as Pose,
          goal: { mood: 'idle' as Mood, desk: m.desks[0], text: '' },
        },
      ]),
    );

    let raf = 0;
    let last = performance.now();
    let acc = 0;
    let t = 0;
    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      const dt = Math.min(0.2, (now - last) / 1000);
      last = now;
      acc += dt;
      if (acc < 1 / FPS || document.hidden) return;
      const tick = acc;
      acc = 0;
      t += tick;

      const snap = useOfficeStore.getState().snapshot;
      let waitSlot = 0;
      for (const m of CREW) {
        const a = actors.get(m.id)!;
        a.goal = goalOf(m, snap, codexBlocked.current);
        step(a, m, a.goal.mood === 'wait' ? waitSlot++ : 0, tick);
      }

      ctx.drawImage(bg, 0, 0);
      drawWindow(ctx, planet, t);
      drawAisleLights(R, t);
      drawTerminal(R, CREW.some((m) => actors.get(m.id)!.goal.mood === 'wait'), t);
      const items: { z: number; draw: () => void }[] = [];
      for (const id of Object.keys(DESKS)) {
        const m = CREW.find((c) => c.id === id);
        const a = m && actors.get(m.id);
        const atDesk = a && Math.hypot(a.x - seat(id).x, a.z - seat(id).z) < 0.4;
        const screen: Screen = a && atDesk ? screenOf(a.goal) : 'off';
        items.push({ z: DESKS[id].z + 0.2, draw: () => drawConsole(ctx, id, m?.color ?? '#3d4a70', screen, t) });
        items.push({ z: seat(id).z - 0.05, draw: () => drawChair(R, id) });
      }
      for (const a of actors.values()) items.push({ z: a.z + 0.01, draw: () => drawFigure(R, a, PX(a.x), PZ(a.z), t) });
      items.sort((p, q) => p.z - q.z).forEach((i) => i.draw());

      // Etiketler: doğrudan DOM — React'i her karede render ettirme.
      const s = box.clientWidth / W;
      for (const m of CREW) {
        const a = actors.get(m.id)!;
        const el = labelRefs.current[m.id];
        if (!el?.tag || !el.bub) continue;
        const x = PX(a.x) * s;
        const top = (PZ(a.z) - 22) * s;
        el.tag.style.transform = `translate(${x}px, ${top}px) translate(-50%, -100%)`;
        const text = a.pose === 'walk' ? '' : a.goal.text;
        if (text) {
          if (el.bub.textContent !== text) el.bub.textContent = text.length > 48 ? `${text.slice(0, 47)}…` : text;
          el.bub.dataset.mood = a.goal.mood;
          el.bub.style.transform = `translate(${x}px, ${top - 14 * Math.max(1, s / 3)}px) translate(-50%, -100%)`;
          el.bub.hidden = false;
        } else {
          el.bub.hidden = true;
        }
      }
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [paused]);

  // Karaktere ya da konsoluna tıkla → o masanın ajan kartı (canlı akış).
  const onClick = (e: MouseEvent<HTMLDivElement>) => {
    const box = boxRef.current;
    if (!box) return;
    const r = box.getBoundingClientRect();
    const wx = ((e.clientX - r.left) / r.width) * W;
    const wy = ((e.clientY - r.top) / r.height) * H;
    let best: { m: Member; d: number } | null = null;
    for (const m of CREW) {
      for (const p of [seat(m.id), m.home]) {
        const d = Math.hypot(PX(p.x) - wx, PZ(p.z) - 8 - wy);
        if (d < 18 && (!best || d < best.d)) best = { m, d };
      }
    }
    if (!best) {
      selectDesk(null);
      return;
    }
    const snap = useOfficeStore.getState().snapshot;
    selectDesk(goalOf(best.m, snap, codexBlocked.current).desk);
  };

  return (
    <div ref={wrapRef} className="station">
      <div ref={boxRef} className="station__box" onClick={onClick}>
        <canvas ref={canvasRef} width={W} height={H} className="station__canvas" aria-label="Ajan İstasyonu" />
        {CREW.map((m) => (
          <div key={m.id}>
            <div
              ref={(el) => {
                labelRefs.current[m.id] = { ...labelRefs.current[m.id], tag: el };
              }}
              className="station__tag"
            >
              {m.name}
            </div>
            <div
              ref={(el) => {
                labelRefs.current[m.id] = { ...labelRefs.current[m.id], bub: el };
              }}
              className="station__bub"
              hidden
            />
          </div>
        ))}
      </div>
    </div>
  );
}
