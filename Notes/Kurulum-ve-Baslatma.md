---
tags: [chiron, kurulum]
---

# Kurulum ve Başlatma

Bağlı: [[Home]] · [[Mimari]] · [[Arayuz]] · [[Bilinen-Tuzaklar]]

> **2026-07-31 düzeltmesi.** Bu not altı silinmiş dosyaya atıf yapıyordu
> (`BASLAT.bat`, `ui.py`, `wakeup_listener.py`, `ses_testi.py`, `OKU_BENI.txt`,
> `setup.bat`) ve `make_shortcut.py`'nin iki kısayol ürettiğini söylüyordu.
> Depo public olduğu için yanlış kurulum talimatı gerçek bir sorundu. Aşağıdaki
> her yol ve komut diske karşı doğrulandı.

## Kurulum

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy config\api_keys.example.json config\api_keys.json
```

Gemini anahtarı `config/api_keys.json` içine yazılır — ya da uygulama açıkken
ayarlar panelinden girilir (panel dosyaya yazıyor, yeniden başlatmak gerekmez).

Arayüz ilk açılışta kendiliğinden derleniyor (`CHIRON.bat` içinde). Elle:
`cd frontend && npm install && npm run build`.

**İsteğe bağlı ağır bağımlılıklar** — kurulu değilse ilgili özellik kapalı
görünür, uygulama çökmez: `ultralytics` (nesne tanıma), `easyocr` (OCR).
easyocr'ın `opencv-python`'u ezme tuzağı için [[Bilinen-Tuzaklar]].

## Başlatıcılar

| Komut | Ne yapar |
|---|---|
| `CHIRON.bat` | Uygulama. Arayüz derlenmemişse bir kereye mahsus derler, sonra `pythonw desktop.py` |
| `WEB-BASLAT.bat` | Geliştirme: `npm run dev` + tarayıcı. 3000 portu zaten dinlemedeyse ikinci sunucu açmaz |
| `python desktop.py --sadece-arayuz` | Yalnızca 3D sahne — mikrofonu ve Gemini kotasını meşgul etmez |
| `python make_shortcut.py` | Masaüstü kısayolu |
| `python make_icon.py` | Uygulama ikonunu yeniden üretir |

`CHIRON.bat` derleme başarısız olursa duruyor ve npm çıktısına bakmayı söylüyor —
eskiden sessizce hiç açılmayan bir uygulama bırakıyordu.

## Masaüstü kısayolları — make_shortcut.py

**Tek uygulama, tek kısayol:** `Chiron.lnk` → `pythonw.exe desktop.py`.
(2026-07-29'a kadar ikinci bir kısayol daha vardı, `main.py`'yi Tkinter
penceresiyle açıyordu; o arayüz kaldırılınca kısayol da kaldırıldı.)

- `create_desktop_shortcut()` → Masaüstü
- `create_startup_shortcut()` / `remove_startup_shortcut()` → Başlangıç klasörü
- İkisini de ayarlar panelindeki düğmeler çağırıyor (`backend/api/settings.py`)
- `.lnk` PowerShell `WScript.Shell` COM nesnesiyle yazılıyor, ek bağımlılık yok

### pythonw tuzağı — ikisi de "kısayol hiç açılmıyor" olarak görünür

1. `pythonw` altında `sys.stdout` ve `sys.stderr` **None**'dır. `print()` bunu
   sessizce tolere eder ama `logging`/uvicorn etmez — `StreamHandler` None akışa
   yazmaya çalışınca patlar ve backend thread'i ilk saniyede ölür. `desktop.py`
   bu durumda akışları `logs/desktop.log`'a yönlendiriyor.
2. Konsol olmadığı için hata kullanıcıya ulaşmaz. `desktop.py` ölümcül hataları
   `_fatal()` ile Windows iletişim kutusunda gösteriyor.

## Masaüstü penceresi — desktop.py

Tek Python süreci, iki katman:

```
[WebView2 penceresi] --HTTP/WS--> [FastAPI 127.0.0.1:8000, arka plan thread]
                                     ├── /        frontend/out (statik arayüz)
                                     ├── /api/*   REST
                                     └── /ws      canlı durum akışı
```

- `frontend/next.config.ts` → `output: 'export'`: `npm run build` saf HTML/CSS/JS
  üretiyor, çalışma zamanında **Node sunucusu gerekmiyor**. Mümkün, çünkü
  uygulama tek sayfa ve tamamen istemci taraflı.
- `backend/main.py` sonundaki `StaticFiles` mount'u **EN SONDA olmalı** — "/"
  altındaki her yolu yakalar; API/WS rotaları önce kaydedildiği için gölgede
  kalmaz. Export yoksa mount edilmez, `npm run dev` akışı bozulmaz.
- 8000 portu zaten dinlemedeyse ikinci backend açılmaz.
- `gui="edgechromium"` zorunlu: belirtilmezse pywebview eski EdgeHTML'e düşebilir,
  orada WebGL2 ve `backdrop-filter` çalışmaz — arayüz siyah görünürdü.
- Pencerede doğrulandı: WebGL2 aktif, `ANGLE (AMD Radeon, Direct3D11)` — gerçek
  GPU hızlandırma.

### Sesli asistan aynı süreçte (2026-07-29)

`ChironLive`'ın **tek satırı değişmedi**. Ses döngüsü arayüzüne 15 noktadan
dokunuyordu (9 metot + 6 geri çağırma yuvası); `core/web_ui.py` tam olarak o
yüzeyi taklit ediyor ama ekrana çizmek yerine olayları WebSocket'e yayınlıyor.
Bağımlılık, ses döngüsü yeniden yazılarak değil **karşı taraf değiştirilerek**
koparıldı.

```
ChironLive --(ui.set_state/write_log/...)--> WebUI --WS--> arayüz
ChironLive <--(on_text_command/on_pause)---- WebUI <--HTTP-- arayüz
```

**Üç kural:**
- `WebUI` içindeki hiçbir çağrı ses döngüsünü bloklamamalı ve patlamamalı.
  Arayüz kapalıyken bile Chiron konuşmaya devam etmeli — olaylar sessizce düşer.
- `connected` ≠ `ready`. Ses döngüsü süreçte olabilir ama Gemini Live oturumu
  henüz kurulmamış olabilir; o aralıkta gönderilen komut **kaybolur**. Arayüz
  yazma kutusunu `ready` gelene kadar kilitliyor.
- `"Siz: ..."` satırını `ChironLive._on_text_command` zaten yazıyor; `WebUI`
  tekrar yazmamalı (ilk sürümde satır sohbette iki kez görünüyordu).

## Ses cihazları ve "Chiron konuşmuyor" teşhisi

Chiron'un sesli çalışması üç halkaya bağlı ve **herhangi biri koptuğunda belirti
aynı: sessizlik.** Bu belirsizlik gerçek bir arızada saatler kaybettirdi.

> Bir zamanlar `ses_testi.py` adında ayrı bir teşhis betiği vardı; kaldırıldı.
> Teşhis mantığı `core/audio_devices.py` içinde yaşamaya devam ediyor ve
> uygulama açılışında otomatik çalışıyor.

### İki tür mikrofon arızası — ikisi de "hata vermez"

- **`silent`** — tamponlar sıfır dolu. Uç nokta Windows'ta AKTİF ve seviyesi %97
  görünse bile olabilir (bu makinede tam olarak bu yaşandı).
- **`frozen`** — tamponlar sıfır değil ama **her tamponda birebir aynı değer**;
  sürücü ses yerine sabit çöp döndürüyor. Bu makinede DirectSound yolu böyle
  davranıyordu.

Sadece "seviye > 0" bakan bir kontrol ikincisini "çalışıyor" sanır — bu yüzden
canlılık kararı seviyeye değil **seviyenin değişimine** (standart sapma) bakıyor:
`core/audio_devices.py` → `probe_input()`.

`main.py` her açılışta (süreç başına bir kez, `_check_microphone_health`)
mikrofonu 2 sn dinliyor; ölü bulursa arayüz log'una ne yapılacağını yazan bir
`ERR:` satırı düşüyor — eskiden hiçbir belirti vermeden sessizce oturuyordu.

### Cihaz seçimi

`config/api_keys.json` içinde iki opsiyonel anahtar:
`"mic_device"` (ör. `"Microphone Array"`) ve `"speaker_device"` (ör. `"Speaker"` —
Windows varsayılanı kulaklık jakına düştüğünde).

**İsim tutuluyor, indeks değil:** PortAudio indeksleri cihaz takılınca kayar.
Eşleşme bulunamazsa uygulama sessize düşmez, varsayılana döner (log'a uyarı yazar).

**Mikrofon olmadan da Chiron konuşur:** arayüzdeki yazı kutusuna yazılan metin
`send_client_content` ile gönderiliyor ve oturum `response_modalities=["AUDIO"]`
olduğu için cevap **sesli** geliyor.

## Varlıklar

| Klasör | İçerik |
|---|---|
| `Icon/` | `chiron.ico` (10 boyutlu), `chiron.png`, `chiron-tray.png` — hepsi `make_icon.py` ile üretiliyor |
| `SFX/` | `Start` (açılış), `Done` (araç başarısı), `Error` (hata), `HUD` (uyku/uyanma, tepsi), `Think` (düşünme döngüsü) |
| `Fonts/` | Grift ailesi (.ttf) — **hiçbir yerden çağrılmıyor**, bkz. aşağısı |

**Sesleri artık tarayıcı çalıyor**, Python değil: `backend/main.py` `SFX/`
klasörünü `/sfx` altında sunuyor, `frontend/services/sfxPlayer.ts` çalıyor.
Beş dosyanın beşi de bağlı.

`Icon/` üçü de bağlı (`desktop.py`, `make_shortcut.py`, tepsi). `Fonts/` **değil**:
üç Grift `.ttf`'ine kodda tek atıf yok — silinen Tkinter arayüzünden kalma, web
arayüzü Inter kullanıyor (`next/font`). 2026-08-21 temizliğinde tespit edildi,
kullanıcı kararıyla **bilerek bırakıldı** (marka fontu olarak ileride web UI'ye
bağlanabilir). Yani bu, kasadaki "import edilmiyorsa yaşamıyordur" kuralının
bilinen tek istisnası — ölü kod ararken tekrar tespit edilirse yeniden tartışma,
karar verilmiş.

**Kritik ayrıntı:** Chromium kullanıcı sayfaya dokunmadan ses çalmayı engeller,
bu yüzden açılış sesi hiç duyulmuyordu. `desktop.py` en üstte
`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--autoplay-policy=no-user-gesture-required`
ayarlıyor — WebView2 bu değişkeni yalnızca motor başlamadan önce okuduğu için
import'lardan bile önce set ediliyor.

## Ayarlar paneli

Sol ray > dişli ikon.

| Kontrol | Nereye yazıyor |
|---|---|
| Gemini API anahtarı | `gemini_api_key` (panelde maskeli) |
| Ses (9 seçenek) | `voice` + oturumu anında yeniler |
| Ses efektleri / seviye | `sfx_enabled`, `sfx_volume` (kaydırırken değil **bırakınca** yazılır) |
| Açılışta başlat | Başlangıç klasörü kısayolu |
| Masaüstüne kısayol | `Chiron.lnk` |

"Tepsiye al" 2026-07-30'da bu panelden çıkarılıp sahnenin sağ üstüne taşındı
([[Arayuz]]).

## Pencere boyutu hafızası

Pencere en son bırakıldığı boyutta ve konumda açılıyor. Kayıt
`config/window_state.json` (kimlik bilgisi taşıyan `api_keys.json`'a
karıştırılmadı). İlk açılışta ekranın %82 × %89'u, ortalanmış.

### Neden Win32, neden pywebview değil

Bu makinede Windows ölçeklemesi **%125** ve pywebview'in birimleri tutarlı değil:
`create_window(width=...)`, `window.width`, `webview.screens[0]` ve `min_size`
hepsi **mantıksal** birim kullanıyor (1920x1080 fiziksel = 1536x864 mantıksal).

Bu yüzden boyut/konum **Win32 ile** ölçülüyor (`GetWindowRect`) ve **Win32 ile**
uygulanıyor (`SetWindowPos`) — ikisi de aynı birimi kullandığı için gidiş-dönüş
kararlı. Ekran boyutu `GetDeviceCaps(DESKTOPHORZRES/VERTRES)` ile alınıyor, bu
değer ölçeklemeden etkilenmez. `webview.screens` ile karşılaştırmak pencereyi her
açılışta ölçekleme oranı kadar küçültüyordu.

**Ölçüm tuzağı:** pencereyi DPI-farkında OLMAYAN bir süreçten ölçerseniz Windows
koordinatları sanallaştırır ve yanlış sayı görürsünüz. Ölçen süreçte
`shcore.SetProcessDpiAwareness(2)` çağrılmalı.

Ekranı kaplamış hâlde kapatılırsa yalnızca `{"maximized": true}` kaydediliyor —
kaplanmış boyutu "normal boyut" diye kaydetmek, sonraki açılışta ekran kadar
büyük ama kaplanmamış bir pencere bırakırdı.

## Bellek profili (2026-07-29 ölçümü)

31.3 GB RAM'li makinede, uygulama açıkken, süreç ağacının tamamı:

| Katman | RAM |
|---|---|
| WebView2 (6 süreç, Chromium + WebGL) | ~1.0 GB |
| Python (backend + ses döngüsü + araçlar) | ~255 MB |
| **Toplam** | **~1.25 GB** |

Karşılaştırma (aynı anda): Chrome 2.2 GB, VS Code 2.8 GB.
**Sızıntı yok** — 8 dakikalık boşta ölçümde Python 257→257 MB.

### Açılışta 340 MB → 139 MB

`main.py` araçları kaydetmek için tüm `actions/*` modüllerini import ediyor. İki
modül ağır kütüphaneleri **modül seviyesinde** import ediyordu, yani özellik hiç
kullanılmasa bile bedeli her açılışta ödeniyordu: `object_recognition.py` →
torch + ultralytics + matplotlib (**273 MB**), `video_analysis.py` → yt_dlp
(~50 MB). İkisi de gerçek kullanım anına ertelendi ([[Bilinen-Tuzaklar]]).

### İleride ne büyür

- **Nesne tanıma ilk kez çalıştığında** torch zinciri yüklenir ve süreç ömrü
  boyunca kalır (+273 MB). OCR de kendi modellerini yükler.
- **WebView2'nin ~1 GB'ı** bu mimarinin taban maliyeti; arayüze özellik eklemek
  bunu kayda değer artırmaz (3D sahne zaten GPU'da).
- Sohbet geçmişi `MAX_LINES = 200` ile sınırlı, zaman çizelgesi 120 kayıt.
- Webcam önizlemesi 8 FPS'e kısılı ve **dinleyen arayüz yoksa hiç üretilmiyor**
  (`manager.has_clients()`).
