---
tags: [chiron, arac]
---

# Ses Seviyesi — `set_volume`

Bağlı: [[Home]] · [[Media]] · [[Gelisim-Gunlugu]]

**Ne:** "Sesi kıs/aç", "sesi yüzde otuz yap", "sessize al", "ses kaç?" → PC'nin varsayılan çıkış aygıtının
(hoparlör/kulaklık) ana ses seviyesi. Eylemler: `get`, `set` (level 0-100), `up`/`down` (step, varsayılan 10),
`mute`, `unmute`. Kullanıcıya söylenen yüzde aygıttan GERİ OKUNAN değerdir, istenen değer değil.

**Neden (2026-11-04, K-011):** `play_media` müzik açıyordu ama PC'de sesi ayarlayan hiçbir araç yoktu; en sık
sesli komutlardan biri boşa düşüyordu.

**Nasıl:** `actions/volume.py` — Windows Core Audio, `IMMDeviceEnumerator → GetDefaultAudioEndpoint(eRender,
eConsole) → IMMDevice.Activate(IAudioEndpointVolume)`. pycaw/comtypes yok (yeni bağımlılık yasak), COM vtable'ı ham
ctypes ile çağrılıyor. Yuvalar (IUnknown'un 3'ü önce): enumerator 4, device.Activate 3, volume Set/GetScalar 7/9,
SetMute/GetMute 14/15. Her çağrıda `CoInitializeEx` (MTA); iş parçacığı zaten STA ise `RPC_E_CHANGED_MODE` kabul
edilir ve `CoUninitialize` çağrılmaz. Nesneler `with` çıkışında bırakılır.
- Sesi yükseltmek/ayarlamak sessizliği de kaldırır (sessizde yüzde değişmesi duyulmaz). Sıfıra çekmek dokunmaz.
- Medya tuşu (`VK_VOLUME_UP`, 2 puan/basış) yerine bu yol: mutlak seviye + geri okuma.

**Tuzaklar:**
- Çıkış aygıtı yoksa `0x80070490` → "hoparlör bulunamadı" cümlesi.
- Yalnız ANA seviye; uygulama başına ses (Spotify'ı kıs, YouTube kalsın) `IAudioSessionManager2` ister — yok.
- 2026-11-04 gece: gerçek aygıtta okuma (%20) ve aynı değeri yazıp geri okuma doğrulandı; sesi duyulur biçimde
  değiştirme denenmedi (Yunus'un ekranı/kulaklığı). Sesli canlı deneme birleşince.

**Kaynak:** learn.microsoft.com/windows/win32/api/endpointvolume/nn-endpointvolume-iaudioendpointvolume ·
.../nf-endpointvolume-iaudioendpointvolume-setmastervolumelevelscalar
