import { fetchData, request } from './apiClient';

// Ayarlar — Tkinter penceresindeki ayar panelinin (ui.py) web karşılığı.
// Kaynak tek: config/api_keys.json (bkz. backend/api/settings.py).
export interface Settings {
  voice: string;
  voices: string[];
  hasApiKey: boolean;
  apiKeyMasked: string;
  sfxEnabled: boolean;
  sfxVolume: number;
  micDevice: string;
  speakerDevice: string;
  startupEnabled: boolean;
  shortcutExists: boolean;
}

export const fetchSettings = () => fetchData<Settings>('/api/settings');

export function saveSettings(patch: Partial<Settings> & { geminiApiKey?: string }) {
  return request('/api/settings', { method: 'POST', body: JSON.stringify(patch) });
}

export const createDesktopShortcut = () => request('/api/settings/shortcut', { method: 'POST' });

export const setStartupEnabled = (enabled: boolean) =>
  request('/api/settings/startup', { method: 'POST', body: JSON.stringify({ enabled }) });

export const minimizeToTray = () => request('/api/settings/tray', { method: 'POST' });
export const toggleFullscreen = () => request('/api/settings/fullscreen', { method: 'POST' });
