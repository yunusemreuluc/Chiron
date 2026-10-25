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
}

export interface PanoRepo {
  name: string;
  path: string;
  test_cmd: string;
}

/** Ajanların şu anki durumu — Terra'nın (Codex) kotası dolunca `available: false`. */
export interface PanoAgents {
  codex?: { available: boolean; until: number | null };
}

export const fetchPano = () => fetchData<{ cards: PanoCard[]; agents?: PanoAgents }>('/api/pano');

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
