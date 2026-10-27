import { create } from 'zustand';

// CHIRON alt zaman çizelgesi — Notes/Tasarim-Kurallari.md § Panel yerleşimi
// (Timeline / Reasoning / Tasks / Progress / Logs). Kullanıcı isteğiyle
// (2026-07-30) sıfırdan yazıldı.
//
// TEK AKIŞ, ÜÇ KAYNAK: araç çağrıları (`task_started`/`task_finished`),
// geliştirici günlüğü (`debug`) ve muhakeme durumu (`energy_state` → thinking).
// Ayrı sekmeler yapmak yerine tek kronolojik akış: kullanıcının cevabını aradığı
// soru "Chiron şu an ne yapıyor / az önce ne yaptı" — bu tek bir zaman ekseninde
// okunur, üç ayrı listede değil.

export type TimelineKind = 'task' | 'log' | 'reasoning';
export type TaskStatus = 'running' | 'done' | 'failed';

export interface TimelineEntry {
  id: number;
  kind: TimelineKind;
  /** Araç adı, log seviyesi ya da muhakeme etiketi. */
  title: string;
  /** Argüman özeti, log metni ya da sonuç mesajı. */
  detail: string;
  /** Yalnızca `kind === 'task'` için anlamlı. */
  status: TaskStatus | null;
  at: number;
}

// Uzun oturumlarda bellek sınırsız büyümesin. Panelde bir seferde 5-6 satır
// görünüyor; 120 kayıt kaydırma için fazlasıyla yeterli.
const MAX_ENTRIES = 120;

interface TimelineStore {
  entries: TimelineEntry[];
  /** Şu an çalışan araç sayısı — ilerleme göstergesi bunu okuyor. */
  runningCount: number;
  /**
   * En son DOKUNULAN kaydın id'si — şeridin tek satırında bu gösteriliyor.
   *
   * Neden dizinin sonu değil: bir görev bittiğinde kendi ESKİ satırı
   * güncelleniyor (yeni satır açılmıyor), dolayısıyla en yeni olay dizinin
   * sonunda olmayabiliyor. Sonu göstermek, tamamlanan görevi şeritte hiç
   * duyurmamak anlamına geliyordu.
   */
  lastTouchedId: number | null;

  taskStarted: (name: string, args: string, at?: number) => void;
  taskFinished: (name: string, success: boolean, message: string, at?: number) => void;
  appendDebug: (text: string, level: string, at?: number) => void;
  appendReasoning: (text: string, at?: number) => void;
  clear: () => void;
}

let nextId = 0;

function trim(entries: TimelineEntry[]): TimelineEntry[] {
  return entries.length > MAX_ENTRIES ? entries.slice(-MAX_ENTRIES) : entries;
}

function seconds(at?: number): number {
  // Backend saniye cinsinden `time.time()` gönderiyor; arayüzde her şey ms.
  return at ? at * 1000 : Date.now();
}

export const useTimelineStore = create<TimelineStore>((set) => ({
  entries: [],
  runningCount: 0,
  lastTouchedId: null,

  taskStarted: (name, args, at) =>
    set((state) => {
      const id = nextId++;
      return {
        entries: trim([
          ...state.entries,
          { id, kind: 'task', title: name, detail: args, status: 'running', at: seconds(at) },
        ]),
        runningCount: state.runningCount + 1,
        lastTouchedId: id,
      };
    }),

  taskFinished: (name, success, message, at) =>
    set((state) => {
      // AYNI kaydı güncelliyor, yeni satır eklemiyor: bir araç çağrısı bir olay,
      // iki satır olarak görünmesi akışı iki katına çıkarıp okunmaz hâle getirir.
      // Sondan başa doğru aranıyor — aynı araç üst üste çağrılmış olabilir,
      // kapatılması gereken EN SON çalışan olan.
      const index = state.entries.findLastIndex(
        (entry) => entry.kind === 'task' && entry.title === name && entry.status === 'running',
      );

      if (index === -1) {
        // Başlangıcı kaçırdıysak (ör. arayüz araç çalışırken bağlandı) kaydı
        // yine de göster — sessizce yutmak akışta boşluk bırakırdı.
        const id = nextId++;
        return {
          entries: trim([
            ...state.entries,
            {
              id,
              kind: 'task',
              title: name,
              detail: message,
              status: success ? 'done' : 'failed',
              at: seconds(at),
            },
          ]),
          lastTouchedId: id,
        };
      }

      const entries = [...state.entries];
      entries[index] = {
        ...entries[index],
        status: success ? 'done' : 'failed',
        detail: message || entries[index].detail,
        at: seconds(at),
      };
      return {
        entries,
        runningCount: Math.max(0, state.runningCount - 1),
        lastTouchedId: entries[index].id,
      };
    }),

  appendDebug: (text, level, at) =>
    set((state) => {
      const clean = text.trim();
      if (!clean) return state;
      const id = nextId++;
      return {
        entries: trim([
          ...state.entries,
          {
            id,
            kind: 'log',
            title: level.toUpperCase(),
            detail: clean,
            status: null,
            at: seconds(at),
          },
        ]),
        lastTouchedId: id,
      };
    }),

  appendReasoning: (text, at) =>
    set((state) => {
      const clean = text.trim();
      if (!clean) return state;
      const id = nextId++;
      return {
        entries: trim([
          ...state.entries,
          {
            id,
            kind: 'reasoning',
            // Muhakeme satırında başlık tekrar etmiyor: her satırın üstünde
            // "Muhakeme" yazmak akışı ikiye katlar. Ayrımı ikon taşıyor.
            title: '',
            detail: clean,
            status: null,
            at: seconds(at),
          },
        ]),
        lastTouchedId: id,
      };
    }),

  clear: () => set({ entries: [], runningCount: 0, lastTouchedId: null }),
}));
