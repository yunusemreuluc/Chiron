import { create } from 'zustand';

// Araştırma panosu (2026-11-01) — actions/arastirma_panosu.py. Backend araştırmayı arka planda yapıp
// `research_update` ile ilerlemeyi ve bitince blokları yayınlıyor; `research_show` panoyu açıp kapatıyor.
// Bloklar backend'de temizlenmiş halde geliyor (tip beyaz listesi, uzunluk sınırı), burada yeniden doğrulanmıyor
// ama tipi bilinmeyen blok çizilmiyor (ResearchBoard).

export interface TextBlock {
  type: 'text';
  title: string;
  body: string;
  source: number | null;
}
export interface StatBlock {
  type: 'stat';
  value: string;
  label: string;
  note: string;
  source: number | null;
}
export interface ChartBlock {
  type: 'chart';
  title: string;
  unit: string;
  note: string;
  items: { label: string; value: number }[];
  source: number | null;
}
export interface VideoBlock {
  type: 'video';
  video_id: string;
  title: string;
  channel: string;
  duration: number | null;
  source: null;
}
export type ResearchBlock = TextBlock | StatBlock | ChartBlock | VideoBlock;

export type ResearchStatus = 'running' | 'done' | 'error';
export type ResearchPhase = 'searching' | 'building';

export interface ResearchRun {
  id: string;
  topic: string;
  status: ResearchStatus;
  phase?: ResearchPhase;
  searches?: number;
  reads?: number;
  step?: string;
  error?: string;
  started_at: number;
  finished_at?: number;
  title?: string;
  summary?: string;
  blocks?: ResearchBlock[];
  sources?: { title: string; url: string }[];
}

interface ResearchState {
  run: ResearchRun | null;
  open: boolean;
  /** Kullanıcı bu araştırmanın ilerleme kartını kapattı mı (aynı id için yeniden açılmaz). */
  dismissedId: string | null;
  update: (run: ResearchRun) => void;
  setOpen: (open: boolean) => void;
  dismiss: () => void;
}

export const useResearchStore = create<ResearchState>((set) => ({
  run: null,
  open: false,
  dismissedId: null,
  // İlerleme olayları yalnız sayaç taşır; bitmiş panoyu (bloklarıyla) aynı id'nin geç gelen
  // bir ilerleme olayı ezmesin.
  update: (run) =>
    set((state) =>
      state.run && state.run.id === run.id && state.run.status === 'done' && run.status === 'running'
        ? state
        : { run },
    ),
  setOpen: (open) => set({ open }),
  dismiss: () => set((state) => ({ dismissedId: state.run?.id ?? null })),
}));
