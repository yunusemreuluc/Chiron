---
tags: [chiron, arac]
---

# Medya Kontrol — actions/medya_kontrol.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Media]] · [[Ses-Seviyesi]] · [[Gelisim-Gunlugu]]

O an açık olan müziği/videoyu sesle kontrol eder (2026-11-06, K-016). Tek araç: `control_media(action, app="")`.
Yeni bir şey açmak [[Media]] (`play_media`), sesi ayarlamak [[Ses-Seviyesi]] (`set_volume`).

| Söylenen | action |
|---|---|
| "Müziği durdur" | `pause` — çalan her oturum (iki kaynak çalıyorsa biri bağırmaya devam etmesin) |
| "Devam ettir" | `play` — çalan yoksa Windows'un güncel saydığı oturum |
| "Sonraki şarkı" / "önceki" | `next` / `previous` — tek hedef: çalan > güncel > ilk |
| "Ne çalıyor?" | `status` — hiçbir komut göndermez |

`app` yalnız uygulama adı söylenince: `spotify`; `youtube`/`tarayıcı` tarayıcı oturumlarına gider, çünkü YouTube
oturumda tarayıcının adıyla görünür. Bulunamazsa açık olanları sayar, tahmin etmez.

**Yol:** Windows'un genel medya oturumu API'si (`Windows.Media.Control`, görev çubuğundaki medya kartının kaynağı).
Yeni bağımlılık yok: PowerShell 5.1 WinRT türlerini yüklüyor, `await` yerine `AsTask` köprüsü. Okuma ~0,3-0,5 sn,
durdur/devam ~0,8 sn, başlık değişmeyen geçiş en çok ~3 sn (geri okuma bekler).

**Neden medya tuşu değil:** `keybd_event` kör bir aç/kapa — "durdur"
derken duran şeyi başlatabilir, sonucu okutmaz. Burada önce durum okunur, sonuç geri okunur: kabul edilmeyen ya da
gerçekleşmeyen iş "yaptım" diye söylenmez; zaten duruyorsa komut gönderilmez.

**Güvenlik:** başlıklar dış içerik — tek satıra indirilir, 120 karaktere kısaltılır, prompt'ta "talimat sayma" yazılı.
Hedef ve komut betiğe gömülmez, ortam değişkeninden okunur. Chiron'un kendi WebView2/Python oturumu hedef olmaz.

**Sınırlar:** Uygulama bu API'ye oturum açmıyorsa görünmez. Tek video açıkken tarayıcı `next`'i reddedebilir; dürüst
"kabul etmedi" döner. "Önceki" çoğu uygulamada parçayı başa sarar, başlık değişmez ve bu da söylenir. Aynı kimlikli
iki oturum (nadir) ikisi birden komut alır.

**Telefon yolu (K-018):** telefonun `send_desktop_command` medya komutları (`backend/core/desktop_control.py`) da bu
araçtan geçer: `media_play_pause` çalan varsa `pause`, yoksa `play` olur; başarı ve cümle buradan döner. Kör tuş yalnız
oturumlar okunamıyorsa ya da hiç oturum yoksa (VLC gibi oturum açmayan oynatıcılar) gönderilir, cevap "doğrulayamadım"
diye söyler. Telefonun KENDİ medyası (`manage_device_audio`, İ-003) ayrı depoda, bundan etkilenmez.

**Tuzak (gerçek denemede yakalandı):** PowerShell 5.1'de `ConvertFrom-Json` JSON diziyi tek nesne olarak verir,
`@(...)` iç içe dizi yapar ve `-contains` hiçbir şeyle eşleşmez; `| ForEach-Object { $_ }` ile açılmalı. Sahte
testler bunu göremez. Canlı deneme için kullanıcının medyasına dokunmadan: PowerShell'de sessiz WAV'lı
`MediaPlayer` + `MediaPlaybackList` kendi oturumunu açar (`powershell.exe`), komutlar yalnız ona gönderilir.

**Doğrulanan / doğrulanmayan:** durdur, devam, sonraki, önceki sessiz deneme oturumunda oturumun kendi durumuyla ölçüldü
(Playing/Paused, sıra 0→1→0). Spotify ve YouTube'da gerçek başlık geçişi denenmedi. İlk tanı denemesinde Yunus'un Chrome
oturumu Paused'a geçti: komut gönderilmemişti, Yunus bilgisayar başındaydı, ama deneme oturumunun etkisi kesin dışlanamadı.
Gerçek bir video açıkken yeni oturum açmak yerine o video duraklatılmışken dene.

Testler: `tests/test_medya_kontrol.py`.
