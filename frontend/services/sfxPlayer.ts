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

// ── İnsan görünümü sesi (2026-11-01) ────────────────────────────────────────
// Dosya değil, WebAudio sentezi: yükselen süzgeçli bir "hışırtı" (parçacıklar
// toplanıyor) + derinden gelen bir uğultu + sonda tek bir kristal çınlama
// (büst tamamlandı). Kapanışta aynı şey ters yönde ve daha kısa. SFX ayarlarına
// (açık/kapalı, seviye) uyuyor.
let audioContext: AudioContext | null = null;

export function playMaterialize(opening: boolean): void {
  if (!enabled || typeof window === 'undefined') return;
  try {
    audioContext ??= new AudioContext();
    const ctx = audioContext;
    void ctx.resume();
    const now = ctx.currentTime;
    const duration = opening ? 2.6 : 1.6;
    const master = ctx.createGain();
    master.gain.value = volume * 1.6;
    master.connect(ctx.destination);

    // Hışırtı: beyaz gürültü → kayan bant geçiren süzgeç.
    const noise = ctx.createBuffer(1, Math.ceil(ctx.sampleRate * duration), ctx.sampleRate);
    const channel = noise.getChannelData(0);
    for (let i = 0; i < channel.length; i++) channel[i] = Math.random() * 2 - 1;
    const source = ctx.createBufferSource();
    source.buffer = noise;
    const band = ctx.createBiquadFilter();
    band.type = 'bandpass';
    band.Q.value = 2.2;
    band.frequency.setValueAtTime(opening ? 280 : 4200, now);
    band.frequency.exponentialRampToValueAtTime(opening ? 4200 : 220, now + duration);
    const hiss = ctx.createGain();
    hiss.gain.setValueAtTime(0.0001, now);
    hiss.gain.exponentialRampToValueAtTime(0.35, now + duration * 0.55);
    hiss.gain.exponentialRampToValueAtTime(0.0001, now + duration);
    source.connect(band).connect(hiss).connect(master);
    source.start(now);
    source.stop(now + duration);

    // Uğultu: alçak sinüs, açılırken yükselen perde.
    const hum = ctx.createOscillator();
    hum.type = 'sine';
    hum.frequency.setValueAtTime(opening ? 48 : 96, now);
    hum.frequency.exponentialRampToValueAtTime(opening ? 96 : 40, now + duration);
    const humGain = ctx.createGain();
    humGain.gain.setValueAtTime(0.0001, now);
    humGain.gain.exponentialRampToValueAtTime(0.5, now + duration * 0.4);
    humGain.gain.exponentialRampToValueAtTime(0.0001, now + duration);
    hum.connect(humGain).connect(master);
    hum.start(now);
    hum.stop(now + duration);

    if (opening) {
      // Çınlama: iki hafif akortsuz sinüs, büst tamamlanırken.
      for (const freq of [1318.5, 1324]) {
        const ping = ctx.createOscillator();
        ping.type = 'sine';
        ping.frequency.value = freq;
        const pingGain = ctx.createGain();
        const at = now + duration * 0.82;
        pingGain.gain.setValueAtTime(0.0001, at);
        pingGain.gain.exponentialRampToValueAtTime(0.12, at + 0.02);
        pingGain.gain.exponentialRampToValueAtTime(0.0001, at + 1.4);
        ping.connect(pingGain).connect(master);
        ping.start(at);
        ping.stop(at + 1.5);
      }
    }
  } catch {
    // Ses kartı yok / otomatik oynatma engelli — görsel geçiş yine çalışıyor.
  }
}
