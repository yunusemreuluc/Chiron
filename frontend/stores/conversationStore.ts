import { create } from 'zustand';

// Sesli asistanın (main.py → ChironLive) sohbet akışı. Satırlar backend'den
// "log" olayı olarak geliyor (bkz. core/web_ui.py write_log).
export type LogKind = 'user' | 'chiron' | 'system' | 'error';

export interface LogLine {
  id: number;
  kind: LogKind;
  text: string;
  at: number;
  /** Önekli ham satır — geçmiş birleştirmede tekilleştirme anahtarının parçası. */
  raw: string;
}

// ChironUI'nin (ui.py) yıllardır kullandığı önek sözleşmesi — kaynak metni
// değiştirmeden burada tipe çevriliyor.
const PREFIXES: { prefix: string; kind: LogKind }[] = [
  { prefix: 'siz:', kind: 'user' },
  { prefix: 'you:', kind: 'user' },
  { prefix: 'chiron:', kind: 'chiron' },
  // Kadın seste asistanın adı Daphne (bkz. app_config.assistant_name).
  { prefix: 'daphne:', kind: 'chiron' },
  { prefix: 'sys:', kind: 'system' },
  { prefix: 'err:', kind: 'error' },
];

function parseLogLine(raw: string): { kind: LogKind; text: string } {
  const lowered = raw.toLowerCase();
  for (const { prefix, kind } of PREFIXES) {
    if (lowered.startsWith(prefix)) {
      return { kind, text: raw.slice(prefix.length).trim() };
    }
  }
  return { kind: 'system', text: raw };
}

// Uzun oturumlarda bellek sınırsız büyümesin — panelde görünenden fazlası
// zaten okunmuyor.
const MAX_LINES = 200;

interface ConversationStore {
  lines: LogLine[];
  connected: boolean;
  /** Gemini Live oturumu kuruldu mu? Kurulmadan gönderilen komut kaybolur —
   *  bu yüzden yazma kutusu bu bayrağa bakıyor (bkz. backend/api/voice.py). */
  ready: boolean;
  muted: boolean;
  paused: boolean;
  /** Uzak mod — kullanıcı evde değil, telefondan konuşuyor (bkz. core/web_ui.py).
   *  PC hoparlörü kapalı; masaüstü arayüzü de ses efekti çalmıyor. */
  remote: boolean;
  appendLog: (raw: string, at?: number) => void;
  /** Sunucudaki geçmişle birleştirir (telefon, bkz. hooks/useRemoteConnection.ts).
   *  Anahtar `at`+ham metin: aynı satır hem geçmişten hem canlı akıştan gelirse
   *  bir kez görünür. */
  mergeHistory: (entries: { text: string; at: number }[]) => void;
  setConnected: (connected: boolean) => void;
  setStatus: (status: {
    muted?: boolean;
    paused?: boolean;
    ready?: boolean;
    remote?: boolean;
  }) => void;
  clear: () => void;
}

let nextId = 0;

export const useConversationStore = create<ConversationStore>((set) => ({
  lines: [],
  connected: false,
  ready: false,
  muted: false,
  paused: false,
  remote: false,
  appendLog: (raw, at) =>
    set((state) => {
      const { kind, text } = parseLogLine(raw);
      if (!text) return state;
      const line: LogLine = { id: nextId++, kind, text, at: at ?? Date.now() / 1000, raw };
      const lines = [...state.lines, line];
      return { lines: lines.length > MAX_LINES ? lines.slice(-MAX_LINES) : lines };
    }),
  mergeHistory: (entries) =>
    set((state) => {
      const key = (at: number, raw: string) => `${at}|${raw}`;
      const seen = new Set(state.lines.map((line) => key(line.at, line.raw)));
      const added: LogLine[] = [];
      for (const entry of entries) {
        if (typeof entry?.text !== 'string' || typeof entry?.at !== 'number') continue;
        if (seen.has(key(entry.at, entry.text))) continue;
        const { kind, text } = parseLogLine(entry.text);
        if (!text) continue;
        seen.add(key(entry.at, entry.text));
        added.push({ id: nextId++, kind, text, at: entry.at, raw: entry.text });
      }
      if (added.length === 0) return state;
      const lines = [...state.lines, ...added].sort((a, b) => a.at - b.at || a.id - b.id);
      return { lines: lines.length > MAX_LINES ? lines.slice(-MAX_LINES) : lines };
    }),
  setConnected: (connected) => set(connected ? { connected } : { connected, ready: false }),
  setStatus: ({ muted, paused, ready, remote }) =>
    set((state) => ({
      muted: muted ?? state.muted,
      paused: paused ?? state.paused,
      ready: ready ?? state.ready,
      remote: remote ?? state.remote,
    })),
  clear: () => set({ lines: [] }),
}));
