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
  | 'hata';

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
}

export interface PanoRepo {
  name: string;
  path: string;
  test_cmd: string;
}

export const fetchPano = () => fetchData<{ cards: PanoCard[] }>('/api/pano');

export const fetchRepos = () => fetchData<{ repos: PanoRepo[] }>('/api/pano/repos');

export const createCard = (title: string, detail: string, repo?: string, testCmd?: string) =>
  post<{ card: PanoCard }>('/api/pano', { title, detail, repo: repo || null, test_cmd: testCmd || null });

export const cardAction = (id: string, action: 'start' | 'pause' | 'stop') =>
  post<{ card: PanoCard }>(`/api/pano/${encodeURIComponent(id)}/${action}`);

export const answerCard = (id: string, approved: boolean) =>
  post<{ card: PanoCard }>(`/api/pano/${encodeURIComponent(id)}/answer`, { approved });

export const mergeCard = (id: string, approved: boolean) =>
  post<{ card: PanoCard }>(`/api/pano/${encodeURIComponent(id)}/merge`, { approved });

export const deleteCard = (id: string) =>
  request<{ id: string }>(`/api/pano/${encodeURIComponent(id)}`, { method: 'DELETE' });
