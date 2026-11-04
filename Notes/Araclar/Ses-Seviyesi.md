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

**Uygulama başına ses (2026-11-04, K-012):** `app` parametresi — "Spotify'ı kıs, YouTube kalsın", "Discord'u
sessize al". `_AppSessions` aynı aygıttan `IAudioSessionManager2` (Activate) → `GetSessionEnumerator` (5) → her
oturum `IAudioSessionControl` → QI `IAudioSessionControl2.GetProcessId` (14) → psutil süreç adı (`.exe`'siz) → QI
`ISimpleAudioVolume` (Set/GetMasterVolume 3/4, SetMute/GetMute 5/6). Oturum sesi ana sesin ORANI (Ses
Karıştırıcısı kaydırıcısı), ana sese dokunmaz.
- Eşleşme `match_app`: Türkçe ek atılır ("Spotify'ı"), önce tam ad, yoksa içerme. Bulunamazsa ya da iki farklı
  uygulamaya uyarsa HİÇBİRİNE dokunmaz, ses çıkaranların listesini döndürür (model doğru adla tekrar dener).
- Aynı uygulamanın birden çok oturumu (tarayıcı) → hepsine aynı ayar; söylenen "şu anki" en yükseği.
- pid 0 (Sistem sesleri) ve adı okunamayan süreç atlanır. YouTube ayrı uygulama değil — tarayıcının adı (chrome/msedge).
- Gerçek aygıtta doğrulandı: oturum listesi (Chiron'un kendi `pythonw`'u), %99'a yazıp geri okuma, %100'e geri alma.

**Tuzaklar:**
- Çıkış aygıtı yoksa `0x80070490` → "hoparlör bulunamadı" cümlesi.
- 2026-11-04 gece: gerçek aygıtta okuma (%20) ve aynı değeri yazıp geri okuma doğrulandı; sesi duyulur biçimde
  değiştirme denenmedi (Yunus'un ekranı/kulaklığı). Sesli canlı deneme birleşince.

**Kaynak:** learn.microsoft.com/windows/win32/api/endpointvolume/nn-endpointvolume-iaudioendpointvolume ·
.../nf-endpointvolume-iaudioendpointvolume-setmastervolumelevelscalar
