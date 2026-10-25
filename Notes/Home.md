---
tags: [airon, moc]
---

# Aıron — Not Haritası (MOC)

Bu klasör, Aıron Windows projesinin kod tabanını özetleyen Obsidian notlarını içerir.
Amaç: kaynak kodun tamamını her seferinde yeniden okumadan, kısa notlardan bağlam almak.
Not bir kaynağı özetliyorsa dosya:satır referansı verir — detay gerekirse oradan bakılır.

## Çekirdek
- [[Mimari]] — main.py, AironLive, WebcamStreamer, bağlantı/olay döngüsü
- [[Arac-Tanimlari]] — tool_defs.py (Gemini function declarations) ve core/prompt.txt (sistem promptu)
- [[Bellek-ve-Config]] — memory_manager.py (kalıcı hafıza), app_config.py (API anahtarları/ayarlar)
- [[Arayuz]] — 3D sahne ve paneller: Vision, Timeline, uyku modu, sol panel modülleri, telemetri
- [[Tasarim-Kurallari]] — arayüz stili, animasyon, renk, bileşen adları (kod yorumlarındaki
  `CLAUDE.md § ...` atıfları buraya bakar)
- [[Bilinen-Tuzaklar]] — zamana mal olmuş tuzaklar, arayüzde dürüstlük, nasıl doğrulanır
- [[Yerel-Model]] — Ollama denendi ve **kaldırıldı**; ölçümler duruyor (num_ctx, Türkçe, VRAM)
- `CLAUDE.md` — yalın karar kitabı: Obsidian-önce iş akışı, rol, performans hedefi
- `Docs/Son-Oturum.md` + `Docs/Acik-Konular.md` — oturumlar arası süreklilik;
  `.claude/hooks/` üçlüsü ilkini açılışta context'e enjekte eder, kasa
  güncellenmeden biten oturumu işaretler ([[Gelistirme-Ortami]] § Süreklilik)
- [[Airon-Mobil]] — telefondaki Aıron (Kotlin, `Projects/airon-mobile`): Gemini Live,
  arama/WhatsApp/cihaz araçları, PC köprüsü (`/api/remote/ask|desktop|note`)
- [[Plan-Play-Yayini]] — mobili Play Store'a çıkarma: `play` flavor'ı, kullanıcının kendi anahtarı,
  üyelik yok, kapalı test (12 kişi/14 gün)
- [[Plan-Ajan-Istasyonu]] — ofisten iş verme ve 7/24 döngü: 2D uzay istasyonu, Jarvis lider, 8 adım
- [[Ajan-Ofisi]] — Claude, alt ajanlar ve Codex/Bunny/Gemini masalarda: kim ne yapıyor, görev panosu, kota
- [[Plan-Claude-Entegrasyonu]] — telefondan sesle verilen işi PC'de Claude Code yapar;
  önce Faz 0 (performans ölçümü, test, temizlik)
- [[Uzaktan-Erisim]] — telefondan Aıron: Tailscale + PIN kapısı (`backend/core/remote_auth.py`),
  uzak mod (PC sessiz), telefon arayüzü `frontend/app/m`, kurulum adımları
- [[Kurulum-ve-Baslatma]] — kurulum ve çalıştırma: requirements.txt, AIRON.bat, make_shortcut.py,
  bellek profili; ayrıca `desktop.py` (WebView2 penceresi), `frontend/` (Next.js + Three.js) ve
  `core/web_ui.py` (ses döngüsü ↔ arayüz adaptörü)
- [[Gelistirme-Ortami]] — Aıron'un kodu değil, onu geliştirirken kullanılan araçlar:
  Claude Code alt-ajanları (agency-agents), kurulum kapsamı ve kebab-case `name` tuzağı

## Araçlar (actions/*.py — Gemini'nin çağırdığı fonksiyonlar)
- [[Open-App]] — uygulama açma
- [[Sys-Info]] — pil/CPU/RAM/disk/saat/ağ
- [[Weather]] — hava durumu (wttr.in)
- [[Calendar]] — Google Calendar (tarayıcı tabanlı)
- [[Reminders]] — Microsoft To-Do (tarayıcı tabanlı)
- [[Browser]] — URL açma, arama, YouTube ilk sonucu oynatma
- [[Media]] — Spotify/YouTube'da müzik çalma
- [[Shell]] — cmd.exe komut çalıştırma
- [[Webcam]] — canlı webcam akışı (main.py, WebcamStreamer)
- [[Screen-Vision]] — aktif pencere ekran görüntüsü + Gemini vision analizi
- [[Ekran-Mudahale]] — ekranda öge bulup tıklama/yazma (iki adımlı onay)
  (araç değil, panel — vision yerine `cv2.matchTemplate`)
- [[Nesne-Tanima]] — kameradaki nesneler, YOLO-World (yerel) + öğretme
- [[OCR]] — kameradaki yazıyı okuma, EasyOCR (yerel, Türkçe+İngilizce)
- [[Izleme-ve-Brifing]] — proaktif izlemeler, günlük brifing, aktivite günlüğü
- [[Otonom-Duzeltme]] — gördüğü hatayı kendi düzeltmesi, üç güvenlik kapısı, off/safe/all
- [[Ambient-Baglam]] — kullanıcı şu an ne yapıyor (pencere/program/boşta), kotasız
- [[Dosya]] — doğal dille dosya arama ve içerik özetleme (salt okuma)
- [[Dosya-Yonetimi]] — sıralı adlandırma, taşıma, silme (Geri Dönüşüm Kutusu'na)
- [[Bildirimler-ve-Guc]] — Windows bildirimlerini okuma, kapat/yeniden başlat
- [[Gemini-Masaustu]] — Chrome'da Gemini'ye prompt gönderme otomasyonu
- [[Youtube-Stats]] — YouTube Data API kanal raporu
- [[WhatsApp]] — mesaj gönderme, kişi kaydetme, vCard içe aktarma
- [[Video-Analizi]] — YouTube linki veya yerel video dosyasını Gemini'ye izletip rapor aldırma

## Genel akış
1. `main.py` içindeki `AironLive.run()` Gemini Live API'ye bağlanır (`LIVE_MODEL`).
2. Ses/webcam akışları `asyncio.TaskGroup` ile paralel task'lar olarak yürür.
3. Model bir `function_call` döndürdüğünde `_execute_tool()` ilgili `actions/*.py` fonksiyonunu çağırır.
4. Sonuç `FunctionResponse` olarak modele geri gönderilir; `write_log` ile arayüze (WebSocket) akar.

## Temizlik kuralı
`actions/tts.py`, `actions/webcam_vision.py`, `actions/health.py` hiçbir yerden import
edilmiyordu (macOS sürümünden kalma) — 2026-07-29'da silindiler. Aynı temizlikte
kullanılmayan frontend bileşenleri ve iskelet backend uçları da kaldırıldı.

**Kural:** bir modül `tool_defs.py`'de tanımlı değilse ve hiçbir yerden import
edilmiyorsa yaşamıyordur. "İleride lazım olur" diye tutulan kod, gerçekten lazım
olduğunda zaten yeniden yazılıyor — bkz. `Docs/AIRON_UI_ROADMAP.md`.

Aynı kural 2026-08-06'da tekrar uygulandı: iskelet backend uçları
(`GET /api/system/status`, `GET /api/settings/status` — ikisi de "hazır" yazıp
boş dönüyordu, arayüz hiçbirini çağırmıyordu), hiçbir yerden import edilmeyen
`GlassButton`, boş `.gitkeep` klasörleri (`animations/`, `assets/`, `effects/`,
`styles/`, `types/`, `utils/`, `backend/services/`) ve git'te izlenen bir hata
ayıklama artığı (`logs/airon_ses_ornegi.pcm`) silindi. Aynı turda beş servis
dosyasındaki tekrar `frontend/services/apiClient.ts` altında toplandı
([[Arayuz]] § Veri akışı).

Üçüncü tur 2026-08-21'de yapıldı — **212 + 98 = 310 satır** gitti:
`actions/weather.py`'nin yarısından fazlası (`get_weather_forecast` + WMO kod
tablosu, [[Weather]]), `actions/whatsapp.py`'deki vCard içe aktarma
([[WhatsApp]]), `main.py._interrupt_audio` (sözünü kesme yardımcısı, hiç
çağrılmadı), `ENERGY_CORE_FRAGMENT_SHADER` (`EnergyCore.tsx` yalnızca VERTEX
shader'ı alıyor), `_spotify_installed`, `VALID_ACTIONS`, `has_gemini_api_key`
([[Bellek-ve-Config]]), `measure_distinctiveness`, `registered_tool_names`,
`AUTO_SEND_DELAY_SECONDS`, `PREFERRED_BROWSERS`, üç kullanılmayan import ve
gereksiz `frontend/layouts/.gitkeep` (klasörde zaten `AppShell.tsx` var).

**Bu turun dersi — docstring bir kanıt değil.** `get_weather_forecast` "ana
UI'daki hava durumu panelinin gün-gün gezinme özelliği için kullanılıyor"
diyordu; öyle bir panel hiç olmadı. `_WMO_CODES` tablosunun yorumu ise
Tkinter'ın emoji render sorununu anlatıyordu — yani metin, silineli bir yıl
olmuş bir arayüzü tarif ediyordu. Kodun kendisi hakkında yazdığı şey değil,
**çağıranı** aranmalı.

**Ölü sanılıp bırakılanlar** (silmek ölçüsüz olurdu, ikisi de kayıt altında):
- `frontend/services/voiceApi.ts` → `setPaused` — zincirin tamamı hazır
  (`backend/api/voice.py` → `core/web_ui.py` → `main.py._paused`, beş kullanım),
  eksik olan yalnızca kullanıcının basacağı düğme. `Docs/AIRON_UI_ROADMAP.md`
  § Küçük artıklar'da açıkça bekleyen iş olarak duruyor — yani kural gereği
  "ölü" görünen bir satır, yol haritasında iş varsa **canlıdır**.
- `Fonts/` — üç Grift `.ttf`, koda bağlı değil; kullanıcı kararıyla marka fontu
  olarak bırakıldı ([[Kurulum-ve-Baslatma]] § Varlıklar).

vCard silinirken `_save_phone_book` de gitti (tek çağıranı oydu) ama
`_load_phone_book` **duruyor**: `memory/phone_book.json` elle doldurulursa
kişi araması hâlâ okuyor. Ölü kodu keserken canlı okuma yolunu kesmemek için
yazan/okuyan ayrımı tek tek kontrol edildi.

**Denetimin nasıl yapıldığı önemli:** `@register_tool` ile kaydedilen araçlar
`main.py`'de İSİMLE hiç çağrılmıyor — import'un tek amacı dekoratörü
çalıştırmak. Kör bir "kullanılmayan import" temizliği bu 20+ satırı silip
araçları sessizce yok ederdi; dosyadaki `noqa: F401` yorumları tam bu yüzden
duruyor. Ölü kod ararken registry, `TOOL_DECLARATIONS` ve `core/prompt.txt`
üçlüsü birlikte kontrol edilmeli (2026-08-06'da 36/36 örtüşüyordu; yalnızca
`read_text` prompt'ta eksikti, eklendi — [[OCR]]).

## Kaldırılan: Tkinter arayüzü (2026-07-29)
`ui.py` (3108 satır, "UI v6 Holo Prime") ve `wakeup_listener.py` kullanıcı isteğiyle
tamamen silindi. Tkinter Canvas gerçek blur/bloom/parçacık üretemediği için yaklaşık bir
karşılık çiziyordu; yerini WebGL tabanlı gerçek 3D arayüz aldı (`frontend/`, `desktop.py`).
`AironLive` bu geçişte **değişmedi** — arayüz bağımlılığı `core/web_ui.py` adaptörüyle
karşılandı. Daha öncesinde aynı orb'u PySide6 ile render etme denemesi de yapılmış ve
CPU maliyeti (~%100 tek çekirdek) yüzünden geri alınmıştı; WebGL yolunda o sorun yok
(GPU'da çalışıyor, bkz. [[Kurulum-ve-Baslatma]] bellek/performans ölçümü).
