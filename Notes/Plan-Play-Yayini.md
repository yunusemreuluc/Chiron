---
tags: [chiron, mobil, android, plan, play-store]
---

# Plan — Chiron Mobil'i Play Store'a çıkarmak

Bağlı: [[Chiron-Mobil]] · [[Home]]

2026-10-14, kullanıcı: *"chironu mobil kısmına yayınlamak istiyorum, ona düzen lazım,
yapılacaklar lazım."* Amaç: Play Store'da yayında bir uygulama, CV'ye eklenecek.

## Kararlar (kullanıcı, 2026-10-14)

- **Gemini anahtarı kullanıcının kendisi.** Sunucu yok. İlk açılışta adım adım, hiç bilmeyen
  birine anlatır gibi yönlendiren bir kurulum ekranı ("AI Studio'ya gir → anahtar oluştur → kopyala → yapıştır").
- **Hedef Play Store**, herkese açık production.
- **Ayrı `play` flavor'ı.** Kişisel sürüm (`personal`) olduğu gibi kalıyor: WhatsApp otomasyonu,
  PC köprüsü, Claude'a iş, kendi uyandırma modeli.
- **Veritabanı ve üye girişi yok.** Anahtar ve ayarlar telefonda, Android Keystore ile şifreli.
  Sunucu olmadığı için kişisel veri toplanmıyor, gizlilik politikası ve veri güvenliği formu basit kalıyor.
  Hesap olsaydı Play hesap silme akışı da isteyecekti.
- **Hedef deneyim (kullanıcı, 2026-10-14):** *"bnm telefonda nasıl kullanılıyorsa onun gibi
  kullanmaları için."* Android'in Siri'si. Özellik kesmek değil, aynı deneyimi politikaya uygun yoldan vermek.
  - Varsayılan asistan rolü (`ROLE_ASSISTANT` / VoiceInteractionService): güç ya da ana ekran
    tuşuna basılı tutunca Chiron açılır. Play'in SMS izni istisnası da "varsayılan asistan" için var.
  - Uyandırma sözü herkes için: `chiron-wake` ile sentetik çok-sesli genel model, üstüne ilk girişte
    10 kayıtla telefonda eğitilen kişisel doğrulayıcı (openWakeWord custom verifier). Kontrol edilecek.
    Lisans CC BY-NC-SA: ücretsiz ve reklamsız kaldıkça sorun yok.
  - Uygulama açma: `QUERY_ALL_PACKAGES` yerine `<queries>` MAIN/LAUNCHER, aynı sonuç.
  - WhatsApp otomatik gönderme (erişilebilirlik): beyanla ve demo videosuyla denenir, her gönderim
    sesli onaylı. Reddedilirse Play'de "hazırla, sen bas"a düşer, tam sürüm GitHub APK olarak durur.
  - Xiaomi/Samsung pil ve otomatik başlatma izinleri: ilk girişte markaya göre adım adım rehber.

## Yapılacaklar

### 1. Kod: `play` flavor'ı
- [ ] `personal` / `play` productFlavors; play `applicationId` ayrı (iki sürüm aynı telefonda yan yana durabilsin)
- [ ] Play sürümünde gömülü anahtar yok (`DEFAULT_GEMINI_KEY` ve `DEFAULT_PC_URL` boş)
- [ ] Anahtar `EncryptedSharedPreferences` / Keystore ile saklanır
- [ ] İlk açılış sihirbazı: hoş geldin → anahtar alma rehberi (ekran görüntülü) → anahtarı test et → izinleri tek tek açıklayarak iste
- [ ] Varsayılan asistan rolü (VoiceInteractionService + ilk girişte rol isteği)
- [ ] `QUERY_ALL_PACKAGES` kaldırılır, yerine `<queries>` MAIN/LAUNCHER
- [ ] `WhatsAppSendService` kalır: erişilebilirlik açıklama ekranı, her gönderim sesli onaylı, Play beyanı + video
- [ ] `SEND_SMS` varsayılan asistan istisnasıyla kalır; rol yoksa `ACTION_SENDTO`
- [ ] Genel uyandırma modeli (sentetik çok ses) + telefonda kişisel doğrulayıcı
- [ ] Marka bazlı pil/otomatik başlatma rehberi (Xiaomi, Samsung, Oppo…)
- [ ] `WakeTestReceiver` play sürümünde yok
- [ ] Kişisel sabitler temizlenir (`ContactMatcher`, `WakeWordListener`, `AssistantService`, sistem promptu)
- [ ] PC köprüsü ve Claude'a iş play sürümünde gizli (ya da ileride "isteğe bağlı" bölümde)
- [ ] targetSdk 36'ya yükseltilir, telefonda test edilir
- [ ] Anahtar hatalı/kota dolu olduğunda anlaşılır Türkçe hata mesajı

### 2. Derleme ve imza
- [ ] Upload keystore (OneDrive dışında ve yedekli; kaybolursa güncelleme çıkarılamaz)
- [ ] `bundlePlayRelease` → AAB, Play App Signing
- [ ] versionCode/versionName düzeni

### 3. Mağaza (kod dışı)
- [ ] Play geliştirici hesabı (25 $) ve kimlik doğrulama
- [ ] Gizlilik politikası sayfası (portfolyo sitesinde): ses Google Gemini'ye gidiyor, rehber cihazda okunuyor, sunucu yok
- [ ] Veri güvenliği formu, içerik derecelendirmesi, hedef kitle
- [ ] İzin beyanları: mikrofonla çalışan ön plan servisi (video), bildirim dinleyici, `CALL_PHONE`, rehber
- [ ] Görseller: 512 px ikon, 1024×500 tanıtım görseli, en az 4 ekran görüntüsü; Türkçe açıklama
- [ ] **Kapalı test: 12 test kullanıcısı, 14 gün kesintisiz** (kişisel hesaplarda production'dan önce zorunlu; en uzun süren adım bu)
- [ ] Production başvurusu

### 4. CV
- [ ] Play linki, GitHub reposu, kısa teknik özet (Gemini Live, cihaz üstü wake word, Compose)
