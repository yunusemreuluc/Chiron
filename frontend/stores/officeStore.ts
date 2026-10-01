import { create } from 'zustand';

// Ajan Ofisi (2026-10-02) — backend/core/ofis.py'nin anlık görüntüsü.
// Veri yalnız iki yerden gelir: WebSocket'teki `office_update` ve ofis açılınca
// bir kez `GET /api/office/state`. Burada hiçbir şey uydurulmaz; backend bir
// şeyi bilmiyorsa (ör. `tracking: 'sinirli'`) arayüz de "bilinmiyor" der.

export type WorkerStatus =
  | 'calisiyor'
  | 'onay_bekliyor'
  | 'bosta'
  | 'bitti'
  | 'hata'
  | 'ayrildi';

export type TaskColumn = 'yurutuluyor' | 'onay' | 'incelemede' | 'bitti' | 'hata' | 'durdu';

export interface DeskStats {
  jobs: number;
  done: number;
  failed: number;
  busy_seconds: number;
  tokens: number;
}

export interface Desk {
  id: string;
  name: string;
  model: string;
  role: string;
  color: string;
  status: WorkerStatus;
  workers: string[];
  stats: DeskStats;
}

export interface WorkerSummary {
  id: string;
  desk: string;
  kind: 'chief' | 'subagent' | 'lane';
  name: string;
  title: string;
  brief: string;
  given_by: string;
  status: WorkerStatus;
  current: string;
  started: number;
  last_ts: number;
  ended: number | null;
  model: string | null;
  sandbox: string | null;
  background: boolean;
  tracking: 'tam' | 'sinirli';
  session_id: string | null;
  project: string;
  task_id: string | null;
  tool_count: number;
  tokens: Record<string, number>;
  files_written: number;
  files_read: number;
}

export interface ActivityItem {
  ts: number;
  kind: string;
  text: string;
}

export interface TaskProof {
  tests: { ts: number; command: string; verdict: 'yesil' | 'kirmizi' | 'bilinmiyor'; by: string }[];
  files_changed: string[];
  delegations: number;
  reviews: number;
  children_done: number;
  children_failed: number;
}

export interface OfficeTask {
  id: string;
  title: string;
  worker_id: string;
  column: TaskColumn;
  parent: string | null;
  created: number;
  updated: number;
  prompt: string;
  result: string;
  proof: TaskProof;
  children: string[];
}

export interface WorkerDetail extends Omit<WorkerSummary, 'files_written' | 'files_read'> {
  cwd: string | null;
  result: string;
  agent_type: string | null;
  files_read: number;
  files_written: number;
  files_read_list: string[];
  files_written_list: string[];
  activity: ActivityItem[];
  task: OfficeTask | null;
  delegated: WorkerSummary[];
}

export interface QuotaWindow {
  used_percent: number;
  window_minutes?: number;
  resets_at?: number;
}

export interface OfficeSnapshot {
  now: number;
  version: number;
  desks: Desk[];
  workers: WorkerSummary[];
  tasks: OfficeTask[];
  approvals: { id: string; ts: number; worker_id: string; tool: string; what: string }[];
  quota: { codex?: { plan?: string; primary?: QuotaWindow; secondary?: QuotaWindow; ts?: number } };
  tracking: { events_seen: number; last_event_ts: number | null };
}

export type OfficeTab = 'ofis' | 'pano';

interface OfficeStore {
  snapshot: OfficeSnapshot | null;
  /** Ofis ekranında seçili masa (kart açık). */
  selectedDesk: string | null;
  /** Kartta odaklanılan işçi — bir masada birden çok işçi olabilir (paralel lane'ler). */
  selectedWorker: string | null;
  tab: OfficeTab;
  setSnapshot: (snapshot: OfficeSnapshot) => void;
  selectDesk: (desk: string | null) => void;
  selectWorker: (worker: string | null) => void;
  setTab: (tab: OfficeTab) => void;
}

export const useOfficeStore = create<OfficeStore>((set) => ({
  snapshot: null,
  selectedDesk: null,
  selectedWorker: null,
  tab: 'ofis',
  // Eski bir görüntü (yeniden bağlanırken gelen HTTP cevabı) yenisini ezmesin.
  setSnapshot: (snapshot) =>
    set((state) =>
      state.snapshot && state.snapshot.version > snapshot.version && state.snapshot.now > snapshot.now
        ? state
        : { snapshot },
    ),
  selectDesk: (selectedDesk) => set({ selectedDesk, selectedWorker: null }),
  selectWorker: (selectedWorker) => set({ selectedWorker }),
  setTab: (tab) => set({ tab }),
}));

export const STATUS_LABEL: Record<WorkerStatus, string> = {
  calisiyor: 'Çalışıyor',
  onay_bekliyor: 'Onay bekliyor',
  bosta: 'Boşta',
  bitti: 'Bitti',
  hata: 'Hata',
  ayrildi: 'Ayrıldı',
};

export const COLUMN_LABEL: Record<TaskColumn, string> = {
  yurutuluyor: 'Yürütülüyor',
  onay: 'Onay bekliyor',
  incelemede: 'İncelemede',
  bitti: 'Bitti',
  hata: 'Hata',
  durdu: 'Durdu',
};

export const isActive = (status: WorkerStatus) =>
  status === 'calisiyor' || status === 'onay_bekliyor' || status === 'bosta';
