# Son Oturum

Claude Code oturumları arasındaki köprü. `.claude/hooks/session_start.py` her
açılışta buradaki **en üstteki** `## Oturum:` bloğunu okuyup context'e enjekte
ediyor — biçimi bozma, parser bu iki başlığa bakıyor.

Oturum biterken: yeni bloğu en üste yaz, eskisini `## Önceki oturumlar` altına
indir. Üç madde yeter; roman değil, köprü.

## Oturum: 2026-10-02

**Ne yapıldı:** Ajan Ofisi (plan Faz A) yazıldı — `feature/ajan-ofisi` dalı. Claude Code
hook'u (`~/.claude/hooks/ofis-olay.py`, settings.json'da 11 olay, async) + Codex oturum
kayıtları → `backend/core/ofis.py` → `/api/office/*` + WS `office_update` → "Ajanlar"
modülünde tam ekran izometrik hologram ofis, ajan kartı, kanban pano, Codex kota çubuğu.
Astra 11 bulgu verdi, hepsi düzeltildi; canlı veride 3 hata daha bulundu ve düzeltildi.
pytest 80/80, tsc/eslint temiz, build geçti, headless Edge ekran görüntüleriyle doğrulandı. → [[Ajan-Ofisi]]

**Nerede kalındı:** Commit yok (kullanıcı istemedi). Gerçek Aıron penceresinde (desktop.py)
açılıp kullanıcıya gösterilmedi; kullanıcı görünce görsel geri bildirim verecek.

**Sıradaki:** Kullanıcı geri bildirimi → commit; sonra Faz 0 (performans ölçümü — ofis sahnesi de ölçülecek).

## Oturum: 2026-09-28

**Ne yapıldı:** `feature/mcp-server` dalında `mcp_server/` yazıldı — Aıron'un dört
salt-okunur aracı (ekran OCR, aktif pencere, hafıza arama, bildirimler) MCP (mcp==2.2.0)
üzerinden açık, Aıron'un kodu değişmedi. 42 pytest geçti, Inspector CLI ile listelendi ve
çağrıldı, `claude mcp add --scope user airon` ile kaydedildi ve headless Claude'dan
çağrıldı. Astra 8 bulgu verdi, 7'si düzeltildi (UNC/NTLM, telefon maskeleme, indirmesiz OCR,
piksel sınırı, yutulan ağ denemesi…), biri Aıron'un kendi kodunda. → [[MCP-Server]]

**Nerede kalındı:** Dal `origin/feature/mcp-server`'a push edildi; main'e birleştirilmedi.

**Sıradaki:** main'e birleştirme (PR); istenirse Claude Desktop kaydı; `screen_vision` geçici dosya sızıntısı.

## Oturum: 2026-09-21

**Ne yapıldı:** PC'deki Aıron açıldı, telefonda bekleyen 3 istek kasaya düştü (İ-002,
İ-003, İ-004). Dördü de yazıldı: arabada ses yolu SCO'dan A2DP'ye çevrildi (Toyota
görüşme kaynağından müziğe dönmüyordu), `go_home`, iki aşamalı mesaj gönderme,
telefondan istek listesini okuma + isteklere kapsamlı `detail`. Ayrıntı: [[Airon-Mobil]]
§ 2026-09-21. Codex Sol istek listesi lane'lerini, Claude ses yolu ve gönderim akışını
yazdı; Astra 5 bulgu verdi, hepsi doğrulanıp düzeltildi (kritik: model taslağı okumadan
gönderebiliyordu). APK kuruldu, PC yeniden başlatıldı, PC testleri 7/7.

**Nerede kalındı:** Hiçbiri gerçek kullanımda denenmedi. Araba denemesi İ-003'ün
gerçekten çözülüp çözülmediğini gösterecek — İ-003 bu yüzden `bakıldı`, diğer üçü
`yapıldı` (telefon bir sonraki konuşmada haber verecek).

**Sıradaki:** Arabada ölçüm (yankı, mikrofon menzili, kaynak dönüşü). `Notes/Istek-Listesi.md`
public depoda takip ediliyor — gizli tutulacaksa `.gitignore`'a alınmalı, kullanıcı karar verecek.

## Oturum: 2026-09-17

**Ne yapıldı:** Telefonda "Aıron" artık kullanıcının sesiyle eğitilmiş openWakeWord
modeli (Vosk kaldırıldı; eğitim `Projects/airon-wake`). Tel kafes çekirdek, ses
düzeyi/ses tonu, araba modu (Bluetooth, müzik kısma, mesaj okuma, navigasyon) ve
istek listesi eklendi — PC'ye `/api/remote/requests|requests/done|requests/ack`
ve `backend/core/feature_requests.py` → [[Istek-Listesi]]. Ayrıntı: [[Airon-Mobil]].

**Nerede kalındı:** Telefonda kurulu, gerçek arabada ve uzun kullanımda denenmedi.
PC'deki Aıron kapalıydı — yeni uçlar sonraki açılışta yüklenecek.

**Sıradaki:** Kullanıcı geri bildirimiyle uyandırma eşiği/yeniden eğitim; araba
denemesi; istek listesindeki ilk istekleri birlikte değerlendirmek.

## Oturum: 2026-09-16

**Ne yapıldı:** Aıron mobil telefona kablosuz adb (Tailscale) ile kuruldu, gerçek
cihazda denendi. Eklendi: `play_youtube`/`search_in_app`, Xiaomi arka plan açılış
izni kontrolü (MIUI op 10021 — "açıldı" diyip açmıyordu). "Hey Aıron" Vosk ile
yazıldı; servis bekleme modu ve ses devri çalışıyor ama tanıma kullanıcının
gerçek sesinde başarısız ([[Airon-Mobil]] § 2026-09-16).

**Nerede kalındı:** Kullanıcı "hey" demeden sadece "Aıron" istiyor. Karar bekliyor:
özel openWakeWord modeli eğitmek (önerilen) ya da Porcupine.

**Sıradaki:** "Başla" derse uygulamaya kayıt ekranı → ~30 "Aıron" kaydı → PC'de
eğitim → telefonda ONNX tanıyıcı, Vosk'u kaldır. Ölçüm senin sesinle yapılacak.

## Oturum: 2026-09-15

**Ne yapıldı:** Telefondan uzaktan erişim kuruldu ([[Uzaktan-Erisim]]). Tailscale
+ ayrı port (8001) + PIN'li imzalı çerez kapısı, uzak mod (telefondan yazınca PC
hoparlörü/mikrofonu susar), telefon arayüzü `frontend/app/m` (PWA, Three.js'siz).
Astra güvenlik incelemesi 4 bulgu verdi (biri eskiden beri var olan yerel WebSocket
Origin açığı), dördü doğrulanıp düzeltildi. Kapı testi 45/45, Playwright görsel testi geçti.

**Nerede kalındı:** Kod hazır ve test edildi, ama Tailscale PC'de kurulu değil —
gerçek telefonla uçtan uca hiç denenmedi.

**Sonra (aynı gün):** Kullanıcı web arayüzünü değil Siri gibi yerel uygulamayı
istedi → [[Airon-Mobil]] yazıldı (Kotlin, `Projects/airon-mobile`), PC'ye
`/api/remote/ask|desktop|note` eklendi. Tailscale kuruldu ve canlı. Astra 12 bulgu
verdi, hepsi düzeltildi; kişi eşleştirme 13 birim testi, PC köprüsü 11, kapı 45 test.
Release APK 2.3 MB, masaüstünde `Airon-mobil.apk`. Telefona henüz kurulmadı.

**Sıradaki (güncel):** PC'de Aıron'u yeniden başlat (yeni uçlar), APK'yı telefona
kur, izinleri aç, PIN'le PC'ye bağlan, gerçek cihazda "annemi ara" / WhatsApp /
"PC'de ne var" dene. Sonra Faz 2 "Hey Aıron".

**Eski sıradaki:** Kullanıcı Tailscale'i kurup `tailscale serve --bg 8001` çalıştırınca
telefondan gir; PIN, uzak mod ve ekran kilidi sonrası geçmiş tamamlamayı gerçekte
doğrula. Faz C (telefon mikrofonu) ve push bildirim bekliyor.

## Oturum: 2026-08-21

**Ne yapıldı:** Süreklilik hook'ları kuruldu (`.claude/hooks/`). Oturum başında
son oturum + açık konular otomatik yükleniyor; kasa güncellenmeden biten oturum
işaretlenip bir sonraki açılışta uyarı olarak geliyor. Kaynak fikir
[avenoxbeyin](https://github.com/avenoxai/avenoxbeyin), bash yerine Python'a ve
Windows'a uyarlandı.

**Nerede kalındı:** Hook'lar kurulu ve elle test edildi, ancak canlı bir Claude
Code oturumunda henüz doğrulanmadı.

**Sıradaki:** İlk açılışta `[Hafıza — Son Oturum]` bloğunun geldiğini teyit et.
Gelmiyorsa `claude --debug` ile hook çıktısına bak.

## Önceki oturumlar

<!-- Eski bloklar buraya. Parser bu başlıkta durur, altını okumaz. -->
