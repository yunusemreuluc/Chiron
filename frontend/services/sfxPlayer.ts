import { apiBase } from './apiClient';

// Ses efektleri. Tkinter sürümünde Python çalıyordu (ui.py SoundManager);
// 3D arayüzde tarayıcı çalıyor — dosyalar backend'den sunuluyor (/sfx).
// Ayarlar panelindeki "SFX ON" ve "FX LEVEL" doğrudan buradaki iki değişkeni
// besliyor (bkz. components/SettingsPanelContent.tsx).
const FILES = {
  startup: 'Start.mp3',
  success: 'Done.mp3',
  error: 'Error.mp3',
  // Arayüz eylemleri (uyku/uyanma) — dosya projede duruyordu ama hiçbir yerden
  // çalınmıyordu. Bir DURUM sesi değil, kullanıcının kendi eyleminin
  // onaylanması: bu yüzden başarı/hata seslerinden ayrı tutuluyor.
  hud: 'HUD.mp3',
  // Düşünme döngüsü — tek atış değil, DÖNGÜ (bkz. setThinkingLoop). Chiron
  // düşündüğü sürece çalıyor, durum değişince susuyor.
  think: 'Think.mp3',
} as const;

export type SfxName = keyof typeof FILES;

let enabled = true;
let volume = 0.2;

// Her efekt için tek bir Audio nesnesi: her çalışta yeni Audio yaratmak
// (özellikle hata sesi arka arkaya gelirse) belleği boşuna şişirir.
const cache = new Map<SfxName, HTMLAudioElement>();

function element(name: SfxName): HTMLAudioElement | null {
  if (typeof window === 'undefined') return null;
  let audio = cache.get(name);
  if (!audio) {
    audio = new Audio(`${apiBase()}/sfx/${FILES[name]}`);
    audio.preload = 'auto';
    cache.set(name, audio);
  }
  return audio;
}

export function configureSfx(config: { enabled?: boolean; volume?: number }): void {
  if (config.enabled !== undefined) enabled = config.enabled;
  if (config.volume !== undefined) volume = Math.max(0, Math.min(1, config.volume));
  for (const audio of cache.values()) audio.volume = volume;
}

export function playSfx(name: SfxName): void {
  if (!enabled) return;
  const audio = element(name);
  if (!audio) return;
  audio.volume = volume;
  audio.currentTime = 0;
  // Otomatik oynatma engellenirse (bkz. desktop.py'deki autoplay-policy ayarı)
  // sessizce geç — bir ses efekti yüzünden konsola hata basmanın anlamı yok.
  void audio.play().catch(() => {});
}

// Düşünme sesi diğerlerinden BELİRGİN ŞEKİLDE KISIK: bir olayı bildiren tek
// atışlık efektlerin aksine bu, saniyelerce süren bir arka plan dokusu. Aynı
// seviyede çalsaydı Chiron'un her düşünme anı rahatsız edici olurdu.
const THINKING_VOLUME_SCALE = 0.35;

/**
 * Düşünme döngüsünü açar/kapatır. Chiron "thinking" durumuna girdiğinde
 * başlıyor, çıktığında susuyor (bkz. hooks/useThinkingSound.ts).
 */
export function setThinkingLoop(active: boolean): void {
  const audio = element('think');
  if (!audio) return;

  if (!active || !enabled) {
    audio.pause();
    audio.currentTime = 0;
    return;
  }

  audio.loop = true;
  audio.volume = volume * THINKING_VOLUME_SCALE;
  void audio.play().catch(() => {});
}
