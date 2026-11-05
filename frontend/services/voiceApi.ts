// Sesli asistana (backend/api/voice.py) giden komutlar.
// Taban adres, zarf tipi ve hata yutma: services/apiClient.ts.
import { fetchData, post } from './apiClient';

/** `images`: data URL'ler; Gemini Live'a aynı turda gider (backend/api/voice.py). */
export const sendTextCommand = (text: string, images: string[] = []) => post('/api/voice/text', { text, images });
export const setMuted = (value: boolean) => post('/api/voice/mute', { value });
export const setPaused = (value: boolean) => post('/api/voice/pause', { value });
export const resetSession = () => post('/api/voice/reset');

export interface VoiceStatus {
  connected: boolean;
  ready: boolean;
}

export async function fetchVoiceStatus(): Promise<VoiceStatus> {
  const data = await fetchData<Partial<VoiceStatus>>('/api/voice/status');
  return { connected: Boolean(data?.connected), ready: Boolean(data?.ready) };
}
