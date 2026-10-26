import { fetchData, post, request } from './apiClient';

// Görev panosu uçları (backend/api/pano.py). Kart durumu backend'de iş kuyruğundan
// türetiliyor; arayüz yalnızca gösterir ve düğmeye basar.

export type CardStatus =
  | 'bekliyor'
  | 'calisiyor'
  | 'duraklatildi'
  | 'onay'
  | 'dogrulaniyor'
  | 'birlestir'
  | 'bitti'
  | 'iptal'
  | 'hata'
  | 'planlaniyor'
  | 'bolundu';

// Kartı kim yapar: claude (her iş) · codex (Terra, mekanik kod) · gemini (yalnız okur).
export type CardAgent = 'claude' | 'codex' | 'gemini';

export interface CardTest {
  ok: boolean;
  code: number | null;
  tail: string;
  cmd: string;
  at: number;
}

export interface PanoCard {
  id: string;
  title: string;
  detail: string;
  status: CardStatus;
  created: number;
  updated: number;
  job_id: string | null;
  summary: string;
  approval: string;
  error: string;
  steps: number;
  last_step: string;
  cost_usd: number;
  queue_position?: number | null;
  stopping: boolean;
  can_resume: boolean;
  history: { job_id: string; kind: string; at: number }[];
  // Proje kartı (adım 3): iş ayrı worktree'de, test Aıron'da, birleştirme onayla.
  repo?: string | null;
  test_cmd?: string;
  worktree?: string | null;
  branch?: string | null;
  base_branch?: string | null;
  test?: CardTest | null;
  diff?: string;
  merged?: string | null;
  // Lider ajan (adım 4)
  agent?: CardAgent;
  parent?: string | null;
  children?: string[];
  after?: string[];
  planning?: boolean;
  plan_summary?: string;
  // Bekçi (adım 7): Claude'un takıldığı kurallar (katman "arac") + birleştirme öncesi diff taraması ("diff").
  bekci?: BekciHit[];
}

export interface BekciHit {
  kural: string;
  seviye: 'yuksek' | 'orta';
  ad: string;
  arac: string;
  girdi: string;
  engellendi: boolean;
  at: number | null;
  katman: 'arac' | 'diff';
  job_id?: string;
}

/** uyar: yalnız kaydeder · engelle: yüksek seviyeli adımı reddeder (yalnız PC'den değişir). */
export type BekciMode = 'uyar' | 'engelle';
export interface BekciState {
  mod: BekciMode;
  modes: BekciMode[];
}

export interface PanoRepo {
  name: string;
  path: string;
  test_cmd: string;
}

/** Ajanların şu anki durumu — Terra'nın (Codex) kotası dolunca `available: false`. */
export interface QuotaWindowState {
  used: number; // 0..1
  resets_at: number | null;
}

export interface ClaudeQuota {
  five_hour?: QuotaWindowState;
  seven_day?: QuotaWindowState;
  level: 'ok' | 'info' | 'warn' | 'stop'; // %50 bilgi · %75 uyarı · %90 dur
  reason: string;
  seen: number | null;
}

export interface PanoAgents {
  codex?: { available: boolean; until: number | null };
  claude?: ClaudeQuota;
}

// 7/24 döngü (adım 8): bekleyen kartları sırayla kendisi başlatır, kotada uyur, sabah rapor yazar.
export type LoopStatus = 'kapali' | 'bekliyor' | 'calisiyor' | 'uyuyor' | 'sinir';

export interface ReportLine {
  id: string;
  baslik: string;
  not: string;
  durum: CardStatus;
}

export interface MorningReport {
  at: number;
  since: number;
  bitti: ReportLine[];
  bekliyor_yunus: ReportLine[];
  hata: ReportLine[];
  sirada: number;
  bekci: { kart: string; ad: string; engellendi: boolean }[];
  maliyet_usd: number;
  kota: string;
}

export interface LoopState {
  acik: boolean;
  durum: LoopStatus;
  neden: string;
  baslatilan: number;
  gunluk_sinir: number;
  son_rapor: number;
  sonraki_rapor: number;
  rapor: MorningReport | null;
  olaylar: { at: number; metin: string }[];
}

export type PanoSnapshot = { cards: PanoCard[]; agents?: PanoAgents; bekci?: BekciState; dongu?: LoopState };

export const switchLoop = (acik: boolean) => post<{ dongu: LoopState }>('/api/pano/dongu', { acik });

export const fetchPano = () => fetchData<PanoSnapshot>('/api/pano');

export const setBekciMode = (mod: BekciMode) => post<{ mod: BekciMode }>('/api/pano/bekci', { mod });

export const setCardAgent = (id: string, agent: CardAgent) =>
  request<{ card: PanoCard }>(`/api/pano/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify({ agent }) });

export const fetchRepos = () => fetchData<{ repos: PanoRepo[] }>('/api/pano/repos');

export const createCard = (title: string, detail: string, repo?: string, testCmd?: string, agent: CardAgent = 'claude') =>
  post<{ card: PanoCard }>('/api/pano', { title, detail, repo: repo || null, test_cmd: testCmd || null, agent });

export const planCard = (id: string) => post<{ card: PanoCard }>(`/api/pano/${encodeURIComponent(id)}/plan`);

export const cardAction = (id: string, action: 'start' | 'pause' | 'stop') =>
  post<{ card: PanoCard }>(`/api/pano/${encodeURIComponent(id)}/${action}`);

export const answerCard = (id: string, approved: boolean) =>
  post<{ card: PanoCard }>(`/api/pano/${encodeURIComponent(id)}/answer`, { approved });

export const mergeCard = (id: string, approved: boolean) =>
  post<{ card: PanoCard }>(`/api/pano/${encodeURIComponent(id)}/merge`, { approved });

export const deleteCard = (id: string) =>
  request<{ id: string }>(`/api/pano/${encodeURIComponent(id)}`, { method: 'DELETE' });
