import { fetchData, post } from './apiClient';
import type { WorkerStatus } from '@/stores/officeStore';

// Gözetim (2026-11-04) — backend/core/gozetim.py. Hepsi salt-okunur, tek istisna
// kaçak süreci sonlandırma (yalnız kullanıcının tıklamasıyla, pid + başlangıç zamanı doğrulanır).

export type MarkCat = 'okuma' | 'duzenle' | 'shell' | 'web' | 'ajan' | 'mcp' | 'diger' | 'onay' | 'hata';
export type Mark = [number, MarkCat];

export interface GozetimSub {
  id: string;
  name: string;
  title: string;
  status: WorkerStatus;
  tool_count: number;
  started: number;
  ended: number | null;
  current: string;
  kind: 'subagent' | 'lane';
  marks: Mark[];
}

export interface GozetimApproval {
  id: string;
  ts: number;
  worker_id: string;
  tool: string;
  what: string;
  project?: string;
}

export interface GozetimSession {
  id: string;
  session_id: string | null;
  project: string;
  cwd: string | null;
  title: string;
  status: WorkerStatus;
  current: string;
  started: number;
  last_ts: number;
  tool_count: number;
  files_written: string[];
  files_written_count: number;
  marks: Mark[];
  subagents: GozetimSub[];
  approvals: GozetimApproval[];
  model: string | null;
  model_short: string;
  effort?: string | null;
  ctx: { used: number; window: number } | null;
  tokens: { input: number; cache_write: number; cache_read: number; output: number } | null;
  /** null = fiyatı bilinmeyen model var (uydurulmaz). */
  cost: number | null;
  cost_partial?: number;
}

export interface Runaway {
  pid: number;
  name: string;
  create_time: number;
  cpu: number;
  since: number | null;
  ports: number[];
  kind: 'yakiyor' | 'sahipsiz_sunucu';
  command: string;
  cwd: string | null;
}

export interface GozetimView {
  now: number;
  last_event_ts: number | null;
  sessions: GozetimSession[];
  totals: {
    sessions_live: number;
    subagents_running: number;
    subagents_today: number;
    tools_per_min: number;
    tokens_per_min: number;
    cost_today: number;
    cost_known: boolean;
    cost_per_hour: number;
    cache_hit: number | null;
    cache_saved: number;
    by_model: Record<string, number>;
  };
  tool_mix: Partial<Record<MarkCat, number>>;
  research: { ts: number; kind: 'ara' | 'oku'; target: string; worker_id: string; session: string; project: string }[];
  files: { path: string; reads: number; writes: number; writers: string[]; collision: boolean }[];
  log: { ts: number; kind: string; text: string; who: string; worker: string }[];
  approvals: GozetimApproval[];
  runaways: Runaway[];
  /** Chiron'dan cevaplanabilen izin soruları (backend/core/onay.py). */
  decisions: Decision[];
}

export const fetchGozetim = () => fetchData<GozetimView>('/api/office/gozetim');

export const fetchLastReply = (workerId: string) =>
  fetchData<{ text: string }>(`/api/office/gozetim/son-cevap/${encodeURIComponent(workerId)}`);

export const endRunaway = (pid: number, createTime: number) =>
  post(`/api/office/gozetim/kacak/${pid}/sonlandir`, { create_time: createTime });

// Oturum kontrolü (2026-11-05, backend/core/oturum_kontrol.py): "ne yapıyorsun?" yan sorgusu,
// Sonlandır (devam: değişiklikler kalır / sil: dosyalar oturum öncesine döner).
export interface AskTurn {
  q: string;
  a: string;
}
export const askSession = (workerId: string, question: string, history: AskTurn[]) =>
  post<{ answer: string }>(`/api/office/gozetim/sor/${encodeURIComponent(workerId)}`, {
    question,
    history: history.slice(-6),
  });

export interface RevertItem {
  path: string;
  /** geri: oturum öncesine döner · sil: oturumun oluşturduğu dosya · ayni: değişmemiş · atla: yedek yok */
  action: 'geri' | 'sil' | 'ayni' | 'atla';
}
export interface RevertPlan {
  ok: boolean;
  why: string;
  alive: boolean;
  items: RevertItem[];
}
export const fetchRevertPlan = (workerId: string) =>
  fetchData<RevertPlan>(`/api/office/gozetim/geri-al/${encodeURIComponent(workerId)}`);

export interface EndResult {
  stopped: boolean;
  geri?: number;
  sil?: number;
  hata?: number;
  skipped?: number;
  undo_dir?: string;
}
export const endSession = (workerId: string, mode: 'devam' | 'sil') =>
  post<EndResult>(`/api/office/gozetim/sonlandir/${encodeURIComponent(workerId)}`, { mode });

/** Oturum rengi — her oturum kendi tonunda (yörüngedeki küçük çekirdek, kart kenarı, şerit adı aynı renk).
 *  Çekirdeğin durum renkleriyle (buz mavisi, turkuaz konuşma, kehribar otomasyon, mor hafıza) çakışmayacak tonlar. */
// Buz mavisine yakın camgöbekleri (#6fd3ff, #a6f0ff) ilk denemede ana çekirdekle karışıyordu — çıkarıldı.
export const SESSION_HUES = ['#ff8fa3', '#7ee0b5', '#ffd27a', '#b59cff', '#c6f26b', '#ffb38a', '#f2a6ff', '#ff7ad9'];

function hashIndex(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i += 1) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return h % SESSION_HUES.length;
}

/** Oturum → renk. Önce kimliğin kendi tonu; o ton başka bir canlı oturumdaysa sıradaki boş ton.
 *  `ids` başlama sırasıyla verilmeli — yeni oturum eskilerin rengini değiştirmesin. */
export function hueMap(ids: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  const used = new Set<number>();
  for (const id of ids) {
    let i = hashIndex(id);
    for (let k = 0; k < SESSION_HUES.length && used.has(i); k += 1) i = (i + 1) % SESSION_HUES.length;
    used.add(i);
    out[id] = SESSION_HUES[i];
  }
  return out;
}

// ── Yörünge ekleri (2026-11-04) ─────────────────────────────────────────────
export interface Decision {
  id: string;
  ts: number;
  session_id: string;
  project: string;
  cwd: string | null;
  tool: string;
  summary: string;
  detail: string;
  can_always: boolean;
  deadline: number;
  state: string;
  worker_id: string | null;
}

export interface OrbitExtras {
  now: number;
  ctx: Record<string, { used: number; window: number }>;
  bg: { id: string; session: string; label: string; started: number; status: string; ended: number | null }[];
  dev: { pid: number; name: string; ports: number[]; cwd: string | null; session: string }[];
  runaways: Runaway[];
  decisions: Decision[];
}

export const fetchOrbitExtras = () => fetchData<OrbitExtras>('/api/office/gozetim/yorunge');

/** Claude Code izin sorusuna Chiron'dan karar (backend/api/onay.py). */
export const decide = (id: string, behavior: 'izin' | 'red' | 'terminal', message = '', always = false) =>
  post(`/api/onay/${encodeURIComponent(id)}/karar`, { behavior, message, always, by: 'ekran' });

/** Araç kategorisi → kıvılcım/şerit rengi (app/gozetim.css --gz-* ile aynı). */
export const CAT_COLOR: Record<string, string> = {
  okuma: '#7fb2ff',
  duzenle: '#5d8fe0',
  shell: '#e8eef7',
  web: '#a9c4e6',
  ajan: '#b59cff',
  mcp: '#7ee0b5',
  diger: '#8a9ab0',
  onay: '#e0a355',
  hata: '#ff5d6c',
};
