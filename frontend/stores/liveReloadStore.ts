import { create } from 'zustand';

// Canlı yükleme (2026-11-04) — backend/core/canli_yukleme.py. Backend kodu yeniden başlatmadan
// yamalar (`code_reload`), arayüz yeniden derlenince `ui_updated` gelir ve sayfa kendini yeniler
// (components/canli/CanliYukleme.tsx — açık pencere / yazılan metin varken bekler).

export interface CodeReload {
  module: string;
  path: string;
  ok: boolean;
  applied: string[];
  restart: string[];
  error: string;
  at: number;
}

interface LiveReloadState {
  /** Yeni derleme geldi, sayfa uygun ilk anda yenilenecek. */
  uiPending: boolean;
  /** Son kod yamaları (en yeni başta, en çok 5). */
  reloads: CodeReload[];
  markUiUpdated: () => void;
  pushReload: (r: CodeReload) => void;
  dismiss: (at: number, module: string) => void;
}

export const useLiveReloadStore = create<LiveReloadState>((set) => ({
  uiPending: false,
  reloads: [],
  markUiUpdated: () => set({ uiPending: true }),
  pushReload: (r) => set((s) => ({ reloads: [r, ...s.reloads.filter((x) => x.module !== r.module)].slice(0, 5) })),
  dismiss: (at, module) => set((s) => ({ reloads: s.reloads.filter((x) => !(x.at === at && x.module === module)) })),
}));
