import { fetchData, post, request } from './apiClient';

// Sohbet uçları (backend/api/sohbet.py). Her mesaj aynı Claude oturumunu sürdürür;
// işi claude_jobs koşar (bekçi, kota freni, süre sınırı aynen geçerli).

export type ChatAgent = 'claude' | 'gemini';
export type MessageStatus = 'sirada' | 'calisiyor' | 'bitti' | 'onay' | 'hata' | 'durdu';

export interface ChatMessage {
  role: 'ben' | 'ajan' | 'sistem';
  text: string;
  at: number;
  job_id?: string;
  status?: MessageStatus;
  steps?: string[];
  last_step?: string;
  approval?: string;
  cost_usd?: number | null;
  bekci?: string[];
}

export interface ChatSummary {
  id: string;
  title: string;
  agent: ChatAgent;
  source: 'airon' | 'terminal';
  cwd: string | null;
  created: number;
  updated: number;
  count: number;
  busy: boolean;
  status: MessageStatus | 'onay' | '';
  last_step: string;
  approval: string;
  preview: string;
}

export interface Chat extends ChatSummary {
  messages: ChatMessage[];
}

export interface TerminalSession {
  session_id: string;
  title: string;
  last_prompt: string;
  cwd: string;
  updated: number;
  open: boolean;
  taken: boolean;
}

export const fetchChats = () => fetchData<{ chats: ChatSummary[] }>('/api/sohbet');

export const fetchChat = (id: string) => fetchData<{ chat: Chat }>(`/api/sohbet/${encodeURIComponent(id)}`);

export const createChat = (agent: ChatAgent, title = '') => post<{ chat: Chat }>('/api/sohbet', { agent, title });

export const sendMessage = (id: string, text: string) =>
  post<{ chat: Chat }>(`/api/sohbet/${encodeURIComponent(id)}/mesaj`, { text });

export const answerChat = (id: string, approved: boolean) =>
  post<{ chat: Chat }>(`/api/sohbet/${encodeURIComponent(id)}/onay`, { approved });

export const stopChat = (id: string) => post<{ chat: Chat }>(`/api/sohbet/${encodeURIComponent(id)}/durdur`);

export const deleteChat = (id: string) =>
  request<{ id: string }>(`/api/sohbet/${encodeURIComponent(id)}`, { method: 'DELETE' });

export const fetchTerminalSessions = () => fetchData<{ sessions: TerminalSession[] }>('/api/sohbet/terminal');

export const takeOver = (sessionId: string, force = false) =>
  post<{ chat: Chat }>('/api/sohbet/devral', { session_id: sessionId, force });
