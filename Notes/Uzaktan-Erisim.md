---
tags: [chiron, uzaktan-erisim, guvenlik]
---

# Uzaktan Erişim — telefondan Chiron

Bağlı: [[Home]] · [[Mimari]] · [[Arayuz]] · [[Bilinen-Tuzaklar]]

2026-09-15, kullanıcı isteği: *"PC açık, dışarı çıktım, telefondan Chiron'a
diyeceğim ki PC'deki şu uygulama bitti mi, o da PC'me bakıp cevap verecek."*

Beyin zaten hazırdı (metin komutu, ekran/sistem araçları, cevabın WebSocket'e
yazı olarak düşmesi). Eksik olan taşıma, kapı ve kabuktu.

## Mimari

```
[Telefon · Chiron PWA] ──HTTPS (tailnet)──> tailscale serve ──> 127.0.0.1:8001 ┐
[WebView2 penceresi]  ──HTTP────────────────────────────────> 127.0.0.1:8000 ┴─ AYNI uvicorn sunucusu
```

- **Port yönlendirme YOK, LAN'a açılma YOK.** Backend hâlâ yalnızca
  `127.0.0.1`'i dinliyor. Dışarıya tek kapı Tailscale: yalnızca kullanıcının
  kendi hesabındaki cihazlar görebiliyor, sertifika Tailscale'den.
- **Tek sunucu, iki soket** (`desktop.py` `_start_backend`). İki ayrı uvicorn
  sunucusu iki asyncio döngüsü demek; WebSocket yayını (`manager.bind_loop`)
  tek döngüye bağlı olduğu için ikinci döngüdeki bağlantılara yayın
  yapılamazdı.
- 8001 açılamazsa uygulama yine açılıyor, yalnızca telefon erişimi kapalı kalıyor.

## Kapı — `backend/core/remote_auth.py`

**Uzak mı yerel mi, başlığa değil PORTA bakılarak karar veriliyor.** `tailscale
serve`'ün hangi `X-Forwarded-*` başlıklarını eklediğine, Host'u yeniden yazıp
yazmadığına güvenmek, bir Tailscale sürümünün davranışına güvenlik emanet etmek
olurdu. Yerel sayılmak için HEPSİ doğru olmalı:

1. 8000'e gelmiş
2. istemci loopback
3. hiçbir proxy başlığı yok (`x-forwarded-*`, `forwarded`, `tailscale-user-*`)
4. Host `localhost` / `127.0.0.1` / `[::1]`

3 ve 4 yedek kilit: `tailscale serve` yanlışlıkla 8000'e yönlendirilirse kapı
sessizce açılmasın. Bunlar ayrıca DNS rebinding'e karşı yerel portu da koruyor.

**PIN → oturum çerezi.**
- PIN 6–12 hane, yalnızca rakam (telefonda sayısal klavye açılıyor; harfli PIN
  dışarıda girilemezdi). `config/api_keys.json`'da **düz değil**, pbkdf2 özeti
  (`remote_pin_hash`).
- Başarılı girişte `v1.<bitiş>.<HMAC>` çerezi: HttpOnly, Secure,
  SameSite=Strict, 30 gün. İmza anahtarı `remote_session_secret` (ilk girişte
  üretilir), mesaja PIN özeti de giriyor → **PIN değişince tüm telefon
  oturumları düşer.** Kaybolan telefonun erişimini kesmenin yolu bu.
- PIN yalnızca PC'den değiştirilebilir (Ayarlar → Uzaktan erişim). Çalınan bir
  oturum PIN'i değiştirip sahibini kilitleyemesin.
- 5 hatalı deneme → 60 sn kilit, sonra her denemede ikiye katlanır (tavan 1 saat).
  Sayaç süreç genelinde tek: bütün uzak istekler aynı proxy'den geliyor, IP ayırt
  edici değil.
- PIN hiç ayarlanmadıysa uzak giriş tamamen kapalı (belirsizlikte kapalı).

**Kimlik doğrulamasız erişilebilen yollar** yalnızca giriş ekranını çizmeye
yetenler: `/m/`, `/m/manifest.webmanifest`, `/m/icons/*`, `/_next/static/*`,
`/api/remote/login`, `/api/remote/session`. Uzak `/` → `/m/`'e yönleniyor
(1366px hedefli 3D sahne telefonda anlamsız).

**Origin kapısı — yerel DAHİL** (Astra incelemesiyle eklendi). WebSocket el
sıkışması ve durum değiştiren HTTP isteği Origin taşıyorsa o Origin bizim olmalı:
yerelde `http://127.0.0.1:8000` / `localhost:8000` / `:3000`, uzakta sayfanın
kendi adresi (Host **ya da** X-Forwarded-Host — proxy Host'u hedefe yeniden
yazabilir). Origin'siz istek geçiyor: tarayıcı bu iki durumda hep gönderiyor.

- **Yerel açık, bu işten ÖNCE de vardı:** tarayıcılar WebSocket'e aynı kaynak
  politikası uygulamıyor. PC'de açılan herhangi bir site `ws://127.0.0.1:8000/ws`'e
  bağlanıp sohbeti ve webcam karelerini okuyabiliyordu.
- **Uzakta SameSite=Strict yetmiyor:** `ts.net` public suffix; aynı tailnet'teki
  `baska.tailXXXX.ts.net` ile PC'nin adresi aynı "site", çerez gidiyor.

**WebSocket:** ara katman saf ASGI (`BaseHTTPMiddleware` WebSocket'i görmüyor).
Uzak el sıkışmada çerez şartı; PIN değişince açık uzak soketler de kapatılıyor
(`manager.close_remote`) — el sıkışmadan sonra çereze bir daha bakılmıyordu. Uzak bağlantıya yalnızca
`log`, `assistant_status`, `energy_state`, `task_started`, `task_finished`
gidiyor — webcam karesi (saniyede 8 × ~130 KB) mobil veride gönderilmiyor.

## Uzak mod — `core/web_ui.py`

Telefondan metin gelince (`backend/api/voice.py` isteğin uzak olduğunu
`request.state.remote`'tan okuyor) komuttan ÖNCE uzak mod açılıyor:

- **PC hoparlörü susuyor** — `main.py _play_audio` ses parçasını çalmadan
  düşürüyor. Cevap metni etkilenmiyor: `output_transcription` modelin
  çıktısından geliyor, hoparlörden değil.
- **Mikrofon kapanıyor** — boş evde TV sesi komut sanılmasın. `WebUI.muted` bir
  özellik: `kullanıcı tercihi VEYA uzak mod`. Tercih ayrı saklanıyor; önceki
  sürüm girişte `muted`'ı ezip çıkışta eski değeri geri yazıyordu ve uzak
  moddayken verilen susturma kararı kayboluyordu (Astra). PC'den mikrofonu
  "aç"mak uzak moddan çıkarıyor — o kişi masada.
- **Proaktif bekçiler çalışmaya devam ediyor** (`_proactive_checks_allowed`):
  normalde susturulmuşken çalışmıyorlar, ama uzak modda kullanıcı tam tersine
  "bitince haber ver" diyebilmeli.
- Masaüstü arayüzü ses efekti ve düşünme döngüsü çalmıyor.

Çıkış: PC'deki dock'ta telefon ikonu (tek dokunuş), PC penceresinden yazmak
(kullanıcı masada demektir) ya da telefondaki "PC sessiz / PC sesli" düğmesi.

## Telefon arayüzü — `frontend/app/m`

Statik export'un ikinci sayfası; bu yüzden `next.config.ts`'e
`trailingSlash: true` eklendi (onsuz `out/m.html` çıkıyor, StaticFiles `/m/`'i
bulamıyordu). Ana ekrana eklenince tarayıcı çerçevesiz açılıyor (manifest +
`appleWebApp`). İkonlar `make_icon.py` → `_build_remote_icons`, zemine basılı.

- **Three.js yok.** Çekirdek saf CSS hologram (`components/remote/RemoteCore.tsx`),
  renkleri `three/coreColors.ts`'ten — palet `palette.ts`'ten bu yüzden ayrıldı:
  orada kalsaydı telefona ~400 KB Three.js inerdi (ölçüm: 1168 → 797 KB).
- **Mobil yaşam döngüsü:** ekran kilitlenince tarayıcı soketi öldürüyor.
  `useRemoteConnection` görünürlük geri gelince beklemeden bağlanıyor ve kaçan
  satırları `/api/remote/history`'den tamamlıyor (WebUI son 80 satırı tutuyor).
  Tekilleştirme `at` + ham metin ile — aynı satır iki yoldan gelirse bir kez.
- **Demo döngüsü yok.** Masaüstü backend yokken sahte durumlar oynatıyor; telefonda
  bu yalan olurdu, "PC'ye ulaşılamıyor" dürüstçe yazıyor.
- Duraklatılmış Chiron metni sessizce yutuyor (`_on_text_command`) — telefonda yazı
  kutusu yerine "Chiron'u devam ettir" düğmesi çıkıyor.

## Kurulum (bir kerelik)

1. **PC:** Chiron'da Ayarlar → Uzaktan erişim → PIN belirle.
2. **PC:** Tailscale'i kur ve giriş yap (`winget install Tailscale.Tailscale`).
3. **Telefon:** Tailscale uygulamasını kur, AYNI hesapla giriş yap.
4. **Tailscale yönetim paneli** (login.tailscale.com → DNS): MagicDNS ve
   **HTTPS Certificates** açık olmalı.
5. **PC (yönetici olmayan terminal):** `tailscale serve --bg 8001`
   → çıktıdaki `https://<pc-adı>.<tailnet>.ts.net` adresi telefonun adresi.
   `--bg` kalıcı: PC yeniden başlasa da serve yapılandırması duruyor.
6. **Telefon:** adresi aç → PIN → paylaş menüsünden "Ana ekrana ekle".

**Dışarıdayken çalışması için:** PC uyku moduna girmemeli (Güç ayarları →
Uyku: Hiçbir zaman, fişe takılıyken) ve Chiron açık olmalı (Ayarlar → Açılışta
başlat).

## Doğrulama (2026-09-15)

- **Astra (gpt-6-astra, read-only) çapraz incelemesi:** 4 bulgu, dördü de kodla
  doğrulanıp düzeltildi — yerel WebSocket Origin açığı (kritik), PIN değişince
  açık soketin kapanmaması, uzakta CSRF, susturma tercihinin ezilmesi.
- Uçtan uca kapı testi, gerçek uvicorn + iki soket, 45/45 (düzeltmelerin
  testleri dahil): yerel/uzak ayrımı,
  proxy başlıklı ve yabancı Host'lu yerel istek, oturumsuz 401, kilit, sahte
  imza, PIN değişince oturum düşmesi, telefonun PIN değiştirememesi, WebSocket
  çerez/Origin reddi, uzak istemcinin webcam karesi almaması.
- Görsel test (Playwright, 390 ve 360 px): kapı, hatalı PIN, karşılama, araç
  göstergesi, cevap, ekran kilidi benzetimi → kaçan satır geçmişten tek kez
  geldi, yatay taşma yok. Masaüstü dock'ta uzak mod düğmesi göründü, tıklayınca
  mod kapandı ve mikrofon eski hâline döndü.
- **Gerçek `tailscale serve` altında ölçüldü (Tailscale 1.102.4, 2026-09-15):**
  `https://<pc-adi>.<tailnet>.ts.net` → `/` 307 `/m/`, oturumsuz `/api/health`
  401, `/api/remote/session` `remote: true`, `/m/` 200; kendi Origin'le POST
  kapıdan geçiyor (401 = oturum yok), `evil.<tailnet>.ts.net` Origin'i 403. Aynı
  anda yerel 8000 `remote: false`. Yani port sınıflandırması ve Origin kapısı
  gerçek proxy arkasında tasarlandığı gibi çalışıyor. Telefonla PIN girişi
  kullanıcı tarafından denenecek.

## Bilinçli olarak yapılmayanlar

- **Telefon mikrofonu (Faz C):** `getUserMedia` HTTPS istiyor (artık var) ama
  `/ws` istemci mesajını işlemiyor; ses akışı ayrı iş.
- **Anlık bildirim (push):** "bitince haber ver" cevabı telefon uygulaması
  açıkken canlı, kapalıyken açınca geçmişten geliyor. Kilit ekranına bildirim
  için Web Push + service worker gerekiyor.
