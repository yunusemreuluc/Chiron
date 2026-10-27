'use client';

import { useMicStore, WAVEFORM_BARS } from '@/stores/micStore';

// Mikrofon dalga formu — kullanıcı isteğiyle (2026-07-30) sohbet dock'una
// eklendi. Chiron'un seni GERÇEKTEN duyduğunun tek görsel kanıtı: mikrofon
// simgesi açık görünürken cihaz sessizce ölmüş olabilir, çubuklar kıpırdamazsa
// bu anında belli oluyor.
//
// Veri tarayıcıdan DEĞİL backend'den geliyor. Tarayıcıda `getUserMedia` ile
// ikinci bir mikrofon akışı açmak, Python tarafının (pyaudio) kullandığı cihazla
// yarışırdı — seviye zaten ses döngüsünün okuduğu ham PCM'den hesaplanıyor
// (bkz. ChironLive._mic_level), yani gösterilen şey tam olarak Chiron'un duyduğu.

const MIN_SCALE = 0.06; // sessizken bile çubuklar görünür kalsın (ölü değil, sakin)

export function VoiceWaveform({ muted }: { muted: boolean }) {
  const levels = useMicStore((state) => state.levels);

  return (
    <span
      className="flex h-4 items-center gap-[2px]"
      aria-hidden="true"
      // Görsel bir gösterge; ekran okuyucu için anlamı yok. Mikrofonun açık/kapalı
      // olduğunu zaten yanındaki düğmenin etiketi söylüyor.
    >
      {levels.map((level, index) => (
        <span
          key={index}
          className={`w-[2px] rounded-full transition-[height] duration-100 ease-out ${
            muted ? 'bg-foreground-disabled' : 'bg-primary'
          }`}
          style={{
            height: `${Math.max(MIN_SCALE, muted ? MIN_SCALE : level) * 100}%`,
            // Kenardaki çubuklar sönük: akış ekranın dışına doğru sönümleniyor,
            // sert kesilmiyor.
            opacity: muted ? 0.35 : 0.45 + (index / WAVEFORM_BARS) * 0.55,
          }}
        />
      ))}
    </span>
  );
}
