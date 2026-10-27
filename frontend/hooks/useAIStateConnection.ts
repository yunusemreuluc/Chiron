'use client';

import { useEffect } from 'react';
import { useAIStateStore, type AIState } from '@/stores/aiStateStore';
import { useConversationStore } from '@/stores/conversationStore';
import { useMicStore } from '@/stores/micStore';
import { useOfficeStore, type OfficeSnapshot } from '@/stores/officeStore';
import { useTimelineStore } from '@/stores/timelineStore';
import {
  useVisionStore,
  type Detection,
  type DetectionSource,
  type TextLine,
} from '@/stores/visionStore';
import { playSfx } from '@/services/sfxPlayer';
import { websocketUrl } from '@/services/apiClient';

/** Uzak modda PC hoparlörü susuyor — arayüzün ses efektleri de susmalı. */
const sfxAllowed = () => !useConversationStore.getState().remote;
const RECONNECT_DELAY_MS = 3000;

// Bu küme core/web_ui.py STATE_MAP'in değerleriyle AYNI olmak zorunda: burada
// eksik kalan bir durum sessizce yutulur ve sahne eski hâlinde donar (2026-07-31
// `automation`/`memory` eklenirken bu satır da güncellendi).
const VALID_STATES = new Set<AIState>([
  'idle',
  'listening',
  'thinking',
  'speaking',
  'vision',
  'automation',
  'memory',
]);

// Backend'in tespit sözlüğü (snake_case, bkz. actions/object_recognition.py) →
// arayüzün tipi. Kutu koordinatı gelmezse (eski bir sürüm ya da tespit
// başarısız) null geçiliyor; panel o zaman çerçeve çizmeyip yalnızca etiketi
// gösteriyor — eksik veriyle çizim yapmaya çalışmak yanlış yerde kutu demek.
/** Normalize [x1,y1,x2,y2]; eksik/bozuksa null. Nesne tespiti ve OCR aynı sözleşmeyi paylaşıyor. */
function parseBox(value: unknown): [number, number, number, number] | null {
  if (!Array.isArray(value) || value.length !== 4) return null;
  const numbers = value.map(Number);
  if (!numbers.every((n) => Number.isFinite(n))) return null;
  return [numbers[0], numbers[1], numbers[2], numbers[3]];
}

function parseDetection(raw: unknown): Detection | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const item = raw as Record<string, unknown>;
  const label = typeof item.label === 'string' ? item.label : '';
  if (!label) return null;

  return {
    label,
    displayName: typeof item.display_name === 'string' ? item.display_name : label,
    confidence: typeof item.confidence === 'number' ? item.confidence : 0,
    box: parseBox(item.box),
  };
}

function parseTextLine(raw: unknown): TextLine | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const item = raw as Record<string, unknown>;
  const text = typeof item.text === 'string' ? item.text.trim() : '';
  if (!text) return null;

  return {
    text,
    confidence: typeof item.confidence === 'number' ? item.confidence : 0,
    box: parseBox(item.box),
  };
}

// 'in yerini alan demo döngüsü — burada artık SADECE
// backend'e (dolayısıyla main.py'ye) bağlanamadığımızda devreye giren bir
// yedek. Gerçek bağlantı kurulur kurulmaz durur.
const DEMO_CYCLE: { state: AIState; durationMs: number }[] = [
  { state: 'idle', durationMs: 4000 },
  { state: 'listening', durationMs: 3000 },
  { state: 'thinking', durationMs: 3500 },
  { state: 'speaking', durationMs: 4000 },
  { state: 'vision', durationMs: 3500 },
  { state: 'automation', durationMs: 3000 },
  { state: 'memory', durationMs: 3000 },
];

// AI Bağlantıları. backend/'in WebSocket'ine
// bağlanmaya çalışır; main.py (core/web_bridge.py üzerinden) gerçek bir
// "energy_state" olayı gönderdiğinde store gerçek veriyle güncellenir.
// Backend çalışmıyorsa (veya main.py kapalıysa) sessizce demo döngüye düşer —
// arayüz backend'siz de "ölü" görünmez, sürekli yeniden bağlanmayı dener.
export function useAIStateConnection() {
  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let demoTimer: ReturnType<typeof setTimeout> | null = null;
    let demoIndex = 0;
    let cancelled = false;

    const stopDemo = () => {
      if (demoTimer) {
        clearTimeout(demoTimer);
        demoTimer = null;
      }
    };

    const advanceDemo = () => {
      const step = DEMO_CYCLE[demoIndex % DEMO_CYCLE.length];
      useAIStateStore.getState().setAIState(step.state);
      demoIndex += 1;
      demoTimer = setTimeout(advanceDemo, step.durationMs);
    };

    const startDemo = () => {
      if (demoTimer || cancelled) return;
      advanceDemo();
    };

    const connect = () => {
      if (cancelled) return;
      socket = new WebSocket(websocketUrl());

      socket.onopen = () => {
        stopDemo();
        useConversationStore.getState().setConnected(true);
      };

      // Sesli asistan artık aynı backend üzerinden konuşuyor (bkz. core/web_ui.py)
      // bu tek soket hem 3D sahnenin durumunu hem sohbet akışını taşıyor.
      socket.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          const data = parsed?.data ?? {};

          switch (parsed?.event) {
            case 'energy_state':
              if (VALID_STATES.has(data.state)) {
                stopDemo();
                useAIStateStore.getState().setAIState(data.state);
              }
              break;
            case 'log':
              stopDemo(); // gerçek asistan konuşuyor — demo döngüsünün işi bitti
              if (typeof data.text === 'string') {
                useConversationStore.getState().appendLog(data.text, data.at);
                // Tkinter sürümündeki davranış: hata satırı gelince hata sesi.
                if (data.text.toLowerCase().startsWith('err:') && sfxAllowed()) playSfx('error');
              }
              break;
            case 'sfx':
              // Araç başarıyla bittiğinde ChironLive'ın çaldırdığı ses
              // (bkz. core/web_ui.py play_success_sfx).
              if (data.name === 'success' && sfxAllowed()) playSfx('success');
              break;
            case 'assistant_status':
              useConversationStore.getState().setStatus({
                muted: data.muted,
                paused: data.paused,
                ready: data.ready,
                remote: data.remote,
              });
              break;
            // ── Görü (2026-07-30) ──
            case 'webcam_state':
              useVisionStore.getState().setWebcamActive(Boolean(data.active));
              break;
            case 'webcam_frame':
              // ~8 FPS base64 JPEG. Store yalnızca SON kareyi tutuyor; burada
              // biriktirme yok (bkz. visionStore.ts).
              if (typeof data.jpeg === 'string') useVisionStore.getState().setFrame(data.jpeg);
              break;
            case 'vision_text': {
              const raw = Array.isArray(data.lines) ? data.lines : [];
              const lines: TextLine[] = raw
                .map(parseTextLine)
                .filter((item: TextLine | null): item is TextLine => item !== null);
              const source: DetectionSource = data.source === 'assistant' ? 'assistant' : 'panel';
              useVisionStore.getState().setTextLines(lines, source);
              break;
            }
            case 'vision_detections': {
              const objects = Array.isArray(data.objects) ? data.objects : [];
              const parsed = objects
                .map(parseDetection)
                .filter((item: Detection | null): item is Detection => item !== null);
              const source: DetectionSource = data.source === 'assistant' ? 'assistant' : 'panel';
              useVisionStore.getState().setDetections(parsed, source);
              break;
            }
            // ── Alt zaman çizelgesi (2026-07-30) ──
            case 'task_started':
              if (typeof data.name === 'string') {
                useTimelineStore
                  .getState()
                  .taskStarted(data.name, String(data.args ?? ''), data.at);
              }
              break;
            case 'task_finished':
              if (typeof data.name === 'string') {
                useTimelineStore
                  .getState()
                  .taskFinished(
                    data.name,
                    Boolean(data.success),
                    String(data.message ?? ''),
                    data.at,
                  );
              }
              break;
            case 'debug':
              if (typeof data.text === 'string') {
                useTimelineStore
                  .getState()
                  .appendDebug(data.text, String(data.level ?? 'INFO'), data.at);
              }
              break;
            case 'reasoning':
              if (typeof data.text === 'string') {
                useTimelineStore.getState().appendReasoning(data.text, data.at);
              }
              break;
            case 'mic_level':
              if (typeof data.level === 'number') useMicStore.getState().pushLevel(data.level);
              break;
            // ── Ajan Ofisi (2026-10-02) — backend/core/ofis.py ──
            case 'office_update':
              if (Array.isArray(data.desks)) {
                useOfficeStore.getState().setSnapshot(data as OfficeSnapshot);
              }
              break;
            default:
              // panel_focus/user_activity — henüz arayüzde karşılığı yok.
              break;
          }
        } catch {
          // Beklenmedik mesaj formatı — yok say.
        }
      };

      socket.onclose = () => {
        useConversationStore.getState().setConnected(false);
        startDemo();
        if (!cancelled) {
          reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
        }
      };

      socket.onerror = () => {
        socket?.close();
      };
    };

    startDemo(); // gerçek bağlantı kurulana kadar hemen demo ile başla
    connect();

    return () => {
      cancelled = true;
      stopDemo();
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, []);
}
