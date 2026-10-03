---
tags: [airon, plan, claude-code, uzaktan-erisim]
---

# Plan — Aıron'a Claude Code entegrasyonu

Bağlı: [[Home]] · [[Uzaktan-Erisim]] · [[Airon-Mobil]] · [[MCP-Server]]

2026-09-30, kullanıcı isteği: *"Ben işteyken telefonla görev verince Aıron senin
sisteminle yapabilir mi?"* — telefondan sesle verilen işi PC'de Claude Code (şu an
kullanılan sistemin aynısı: CLAUDE.md, Jarvis hafızası, skill'ler, Codex lane'leri)
analiz edip yapacak, sonucu Aıron sesli söyleyecek.

**Sıra (kullanıcı kararı):** önce Faz 0 — Aıron'un performansı ölçülür, testler
yapılır, gereksiz dosyalar silinir. Entegrasyon ondan sonra.

**2026-10-02 güncellemesi (kullanıcı):** Faz 0'dan da önce **Ajan Ofisi** (Faz A) yapılır.
Sıra: **Faz A → Faz 0 → Faz 1 → Faz 2 → Faz 3.**

---

## Faz A — Ajan Ofisi (ilk iş)

Esin: Muratify AI'ın **AgentSpace**'i (muratify.com/products/agentspace) — piksel sanat
ofiste kalıcı kimlikli ajanlar, ajana tıklayınca terminali açılıyor, kanban pano, kanıtlı
teslim, sesle iş verme, telefonda aynı ofis, token/maliyet paneli, hafıza grafiği.

Kullanıcı isteği: *"bizde çoklu ajan / alt ajan sistemi zaten var; iş verince o ofis
ortamını görelim, üstüne basınca kim ne yapıyor, ne işle meşgul, görevi, rolü… daha
fazlasını ekle."*

**Fark:** AgentSpace kendi ajanlarını çalıştırıyor. Biz yeni ajan sistemi yazmıyoruz —
var olan düzeni (Claude şef + alt ajanlar + Codex Sol/Astra + Space Bunny + Gemini +
OpenCode) **gözlemleyip** sahneye koyuyoruz. Ofis bir izleme ve yönetim katmanı.

### A.1 Kadro — kalıcı kimlikler (masalar)

| Masa | Kim | Rol (CLAUDE.md'deki iş bölümü) |
|---|---|---|
| Şef masası (ortada) | Claude (ana döngü) | Plan, karar, teşhis, güvenlik, birleştirme |
| Yürütme | Codex Sol | Mekanik/standart kod |
| Kıdemli yürütme | Codex Astra | Zor iş + çapraz inceleme (read-only) |
| Arşiv / okuma | Space Bunny | 200k+ token okuma, uzun özet |
| Araştırma | Gemini flash | ≤200k okuma, karşılaştırma |
| Ucuz kod | OpenCode (Bunny) | Hassas olmayan küçük iş |
| Geçici masalar | Claude alt ajanları | Explore, Plan, general-purpose… iş bitince masa boşalır |

Her kimliğin sabit adı, rengi, avatarı ve özgeçmişi var (kaç iş, başarı oranı, ort. süre,
toplam token). Kadro `config/ofis_kadro.json`'da tanımlı; yeni model eklenince masa eklenir.

### A.2 Veri — uydurma yok, gerçek olay akışı

Bilinen-Tuzaklar § Arayüzde dürüstlük geçerli: ofiste gösterilen her şey gerçek bir olaydan gelir.

- **Claude Code hook'ları** (`~/.claude/settings.json`, var olan dört hook'un yanına):
  `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `SubagentStop`, `Stop`,
  `SessionEnd`. Tek bir hızlı betik (`~/.claude/hooks/ofis-olay.ps1`) olayı
  `%LOCALAPPDATA%\airon\ofis\events.jsonl`'e ekler. Kural: **<30 ms, asla bloklamaz,
  hata verirse sessiz geçer** — Claude oturumunu yavaşlatamaz.
- **Kim ne yapıyor çıkarımı:** `Agent` aracı → yeni alt ajan masası (açıklama + prompt);
  `Bash` komutu `codex exec … -m gpt-5.6-sol` → Sol, `gpt-6-astra` → Astra, `bunny.py` →
  Bunny, `gemini` → Gemini, `opencode run` → OpenCode. Komutun brief'i = görev kartı.
- **Codex ilerlemesi:** `~/.codex/sessions/*.jsonl` izlenir → adım adım ne yaptığı, gerçek token.
- **Claude token/maliyet:** oturum transcript'indeki `usage` alanları.
- **Backend:** `backend/core/ofis.py` olay dosyasını izler, durumu kurar (kim, hangi iş,
  hangi aşama), WebSocket'e `office_*` olayları basar. (Tuzak: `EventType` + yayıncı +
  arayüz `switch` üçü birden — biri atlanırsa olay sessizce düşer.)
- Aıron kapalıyken de olaylar diske yazılır; açılınca geçmiş yüklenir.

### A.3 Ofis sahnesi

- **Görsel dil:** AgentSpace piksel sanat; Aıron'un tasarım kuralları (cam, derinlik,
  hacimsel ışık, "düz tasarım yok") piksel sanatla çelişir. Öneri: **izometrik, hologram
  tarzı 3D ofis** — mevcut Three.js sahnesinde, kamera çekirdekten ofise uçar.
  Kenar çubuğundaki boş `Ajanlar` modülü ofise açılır.
- **Durum dili:** çalışıyor (ekran ışıldar, yazıyor), düşünüyor, okuyor, bekliyor/onay
  bekliyor (turuncu nabız), bitti (yeşil tik), hata (kırmızı), boşta (soluk).
- **Devir animasyonu:** şef bir işi Codex'e verince masadan masaya ışık hattı uçar; sonuç
  dönünce geri uçar. İnceleme (Astra) bulguları kâğıt olarak şefin masasına iner.
- Masa üstü balon: o anki tek satır ("`pytest` koşuyor", "remote_auth.py okuyor").

### A.4 Ajana tıklayınca — kart

- Kimlik: ad, model, rol, rengi, çalışma kademesi (sandbox: read-only / workspace-write).
- **Şu anki iş:** görev başlığı, tam brief, kim verdi, ne zaman başladı, geçen süre.
- **Canlı akış:** son araç çağrıları/komutlar, okuduğu ve değiştirdiği dosyalar (terminal görünümü).
- Token ve tahmini maliyet (bu iş + bugün), kota durumu (Astra kotası uyarısı).
- Geçmiş işleri, başarı oranı; şefin bu ajanın "bitti" iddiasını doğrulayıp doğrulamadığı.
- Düğmeler: logu aç, işi durdur (süreç ağacıyla — TaskStop alt süreç bırakıyor tuzağı).

### A.5 Daha fazlası

- **Görev panosu (kanban):** Gelen → Planlandı → Yürütülüyor → İncelemede → Doğrulandı →
  Teslim. Kartlar ajan masalarına bağlı; alt görev ilerlemesi.
- **Kanıt kartı:** iş kapanınca "testler yeşil / build yeşil / değişen dosyalar / Astra kaç
  bulgu, kaçı kabul" — CLAUDE.md'deki "bitti iddiadır, kanıt değil" kuralının görseli.
- **Onay kuyruğu:** geri alınamayan adım bekleyen işler tek yerde (Faz 2 telefona taşır).
- **Kaynak paneli:** Claude/Codex/Gemini/Bunny kota ve token kullanımı, model dağılımı.
- **Zaman çizelgesi tekrar oynatma:** dünün işini hızlandırılmış izleme (olay logu üstünden).
- **Hafıza köşesi:** Jarvis/memory dosyalarına yazılanlar ofiste "arşiv dolabı"na düşer.
- **Günlük rapor:** gün sonu "bugün ofiste ne oldu" özeti, Aıron sesli okuyabilir.
- **Sesle soru:** "Aıron, ofiste kim ne yapıyor?" → yeni araç `get_office_status` (salt-okunur;
  MCP server'a da eklenebilir).
- **Telefonda ofis:** Faz 3'te Aıron Mobil'e aynı ofis + pano (salt-okunur başlar).

### A.6 Sınırlar

- Faz A **salt gözlem** — ofisten iş verme Faz 1'deki `/api/remote/claude` ile gelir
  (ofise "iş ver" kutusu o zaman bağlanır).
- Olaylarda prompt ve dosya yolları var → yalnız yerel; telefona giden uçlar PIN kapısının arkasında.
- Performans: ofis sahnesi görünür değilken render durur (Faz 0 ölçümünde ofis de ölçülür).
- Teslim öncesi: hook betiği + yeni uçlar Astra read-only incelemesinden geçer.

### A.7 Adımlar
1. Hook betiği + olay şeması + `events.jsonl` (önce sadece kayıt; bir gün gerçek veri topla).
   **✅ 2026-10-02:** `~/.claude/hooks/ofis-olay.py` (stdlib, Python311 — hermes venv'i değil),
   `settings.json`'da 11 olaya `async: true` ile bağlı (yedek: `settings.json.bak-ofis`, beyin
   hook'ları aynen duruyor). Anahtar desenleri `[gizli]` olarak maskeleniyor, 20 MB'ta dosya
   döndürülüyor, paralel yazım kilitli (40 eşzamanlı yazımda 42/42 geçerli satır). Canlı doğrulandı.
2. `backend/core/ofis.py` durum makinesi + WS olayları + testleri (örnek olay dosyasıyla).
   **✅ 2026-10-02** — ve 3–4. adımlar da: tam ekran 3D ofis (ayrı Canvas, ana sahne
   durur), ajan kartı (kimlik, iş, veren, canlı akış, dosyalar, token, kanıt), kanban
   pano, onay kuyruğu, Codex kota çubuğu. Ayrıntı ve tuzaklar: [[Ajan-Ofisi]].
   5. adımdan kalanlar: tekrar oynatma, Claude token'ı, günlük rapor. 6. adım (sesli soru) yapılmadı.
3. Ajanlar paneli: önce 2D liste + tıklayınca kart (veri doğru mu, burada görülür).
4. 3D izometrik ofis + durum animasyonları + devir ışıkları.
5. Pano, kanıt kartı, kaynak paneli, tekrar oynatma.
6. `get_office_status` aracı, sesli soru.

---

## Faz 0 — Performans, test, temizlik (ilk iş)

Amaç: Claude işleri arka planda çalışırken Aıron makineyi yormasın.

### 0.1 Ölçüm (önce taban çizgisi, sonra değişiklik)
- Boşta (dinleme açık, konuşma yok) 10 dk: CPU %, RAM, GPU/VRAM, süreç sayısı.
  `desktop.py` + WebView2 alt süreçleri + uvicorn ayrı ayrı.
- Konuşma sırasında: aynı ölçüler + ilk ses yanıt gecikmesi.
- Yerel modeller: YOLO-World ve EasyOCR ilk yükleme süresi ve bellekte kalan RAM/VRAM —
  kullanılmadığında boşaltılıyor mu?
- Arka plan döngüleri: izlemeler (`start_watch`), brifing, telemetri WS yayını,
  aktivite günlüğü — kaç sn'de bir uyanıyorlar, boşta CPU'ya katkıları.
- 3D sahne: pencere simge durumundayken/arka plandayken render duruyor mu (rAF/FPS).
- MCP server: 2026-09-30'da 4 `mcp_server/server.py` süreci vardı (venv başlatıcı +
  alt süreç, iki Claude oturumu), ~5–30 MB — kapanan oturumda süreç kalıyor mu bak.
- Sonuçlar bu nota tablo olarak yazılır (önce / sonra).

### 0.2 Testler
- Var olan: `tests/test_feature_requests.py`, `mcp_server` testleri (42/42, 2026-09-28).
  İkisi de yeniden koşulur.
- Eksik olan ve entegrasyondan önce lazım olan: `backend/core/remote_auth.py` (PIN,
  çerez, kilit sayacı, port ayrımı) ve `backend/api/remote.py` uçları için test.
  Yeni uzak uç bu kapının arkasına eklenecek; kapı testsiz kalmamalı.
- Açılış duman testi: `python desktop.py --sadece-arayuz` açılıyor, `/api/system/telemetry`
  cevap veriyor.

### 0.3 Temizlik
- Aday listesi çıkarılır, **kullanıcıya gösterilir, onaydan sonra silinir** (tek tek değil,
  liste halinde tek onay):
  `__pycache__/` klasörleri, `logs/` içindeki eski loglar, kullanılmayan ağırlıklar
  (`yolov8s-worldv2.pt` kök dizinde + `weights/` — hangisi kullanılıyor), eski makrolar,
  ölü kod/araç dosyaları (tool_defs'te tanımı olmayan `actions/*.py`).
- 2026-09-30 ilk tarama: repo `venv` hariç **1,1 GB**, 13 `__pycache__` klasörü,
  `logs/` 2 dosya (airon.log, desktop.log), `yolov8s-worldv2.pt` gitignore'da.
  Klasör bazında boyut dökümü yarına kaldı (OneDrive'da `du` çok yavaş).
- `.gitignore` kontrolü: log, ağırlık, `__pycache__`, `config/api_keys.json` repoya girmesin.
- Not: proje OneDrive içinde — büyük ağırlık/log dosyaları senkronu da yoruyor; OneDrive
  dışına taşımak ayrı bir karar olarak sorulur.
- Ayrı konu: `C:\Users\yunus\Aıron` bir **Unity projesi**, bu repo değil. Karışmasın;
  silinmesi istenirse ayrıca sorulur.

### Faz 0 sonuçları (2026-10-02)

**Ölçüm.** Yöntem: `psutil` süreç ağacı + Windows `GPU Engine(*engtype_3D)` sayacı (pid'e göre).
Sesli asistan ölçümü kullanıcının kendi açtığı tam Aıron'u (pasif, dokunmadan) okuyarak.

| Durum | CPU (makine %) | GPU 3D | RAM |
|---|---|---|---|
| Tam Aıron, **tepside**, boşta (ses döngüsü açık) | %0,5 | %0 | 1,7 GB (1,1 GB'ı WebView2 GPU süreci — gizliyken de bırakmıyor) |
| Arayüz, pencere açık, boşta — **önce** (111 FPS, 144 Hz ekran) | %5,7 | **%69,5** | — |
| Arayüz, pencere açık, boşta — **sonra** (uyarlanır FPS, ~30) | %2,7 | **%22,5** | — |

"Önce/sonra" görünür Edge'de (gerçek GPU), çalışan Aıron'un sunduğu arayüzle, 45 sn
boşta, fare hareketsiz. WebView2 aynı Chromium motoru; gerçek pencerede de doğrulanmalı
(`window.__aironGovernor()`).

- **Yapılan:** `three/FrameGovernor.tsx` — aktif/girdi 60, boşta 30, odak dışı 20, uyku 15 FPS
  (ayrıntı [[Arayuz]] § Kare hızı). Ofis açıkken ana sahne zaten duruyor ([[Ajan-Ofisi]]).
- **Yapılan:** `main.py` webcam önizleme döngüsü kamera kapalıyken saniyede 24 → 4 uyanış.
- **Temiz çıkanlar:** MCP server — kapanan oturumdan süreç kalmıyor (şu an tek çift, ~25 MB,
  sahibi canlı oturum). Arka plan bekçileri 20/45/60/90 sn aralıklı — sorun yok. Tepside
  WebView2 render'ı tamamen duruyor (GPU %0).
- **Karar bekleyen:** YOLO-World ve EasyOCR ilk kullanımda yükleniyor (açılışta bedel yok) ama
  **hiç boşaltılmıyor**. Boşta ~10 dk sonra boşaltmak belleği geri verir, bedeli sonraki ilk
  OCR/tespitte birkaç sn yükleme. Kullanıcıya soruldu.
- **Karar bekleyen (görsel):** boşta 30 FPS'te bile GPU %22,5 — kare başına maliyet yüksek.
  Sonraki kaldıraç `PostProcessing.tsx`: EffectComposer varsayılan 8× MSAA + bloom + vignette +
  noise. MSAA'yı 4'e indirmek görünümü değiştirebilir — tasarım kararı, kullanıcının gözüyle.

**Testler.** `tests/test_remote_auth.py` (Codex Sol yazdı, Claude doğruladı: config bellekte
taklit, gerçek dosyaya dokunmuyor) — 32 test. Toplam pytest **112/112** (ofis 31 +
uzak kapı 32 + istek listesi + MCP 42). Açılış duman testi yerine çalışan Aıron'a GET:
`/api/health` 1,5 ms, `/api/system/telemetry` 18 ms, `/api/office/state` 2 ms.

**Temizlik envanteri** (silinmedi — kullanıcı onayı bekliyor):

| Aday | Boyut | Durum |
|---|---|---|
| 13 × `__pycache__/` | 1,1 MB | yeniden üretilir, güvenle silinir |
| `frontend/.next/` (build önbelleği) | 17 MB | yeniden üretilir, güvenle silinir |
| `logs/airon.log`, `logs/desktop.log` | 0,8 MB | küçük; silinebilir ya da döndürülebilir |
| `weights/ViT-B-32.pt` | 338 MB | **KULLANILIYOR** (YOLO-World'ün CLIP metin kodlayıcısı) — kalır |
| `yolov8s-worldv2.pt` (kök) | 25 MB | **KULLANILIYOR** (`object_recognition.py`) — kalır |
| ölü `actions/*.py` | — | yok: 85 py dosyası tarandı, her modül bir yerden çağrılıyor |

`.gitignore` doğru: `config/api_keys.json`, `__pycache__`, `logs/*.log`, `*.pt`, `weights/`
izlenmiyor. Asıl yük silinecek dosyalar değil, **OneDrive senkronu**: `frontend/node_modules`
713 MB + `venv` OneDrive içinde. Projeyi OneDrive dışına taşımak ayrı karar (soruldu).

**Kararlar ve uygulama (2026-10-02, kullanıcı):**
- Temizlik: `__pycache__`, `frontend/.next`, `logs/*.log` silindi. Ağırlıklar kullanıldığı için kaldı.
- Makro: "kullanmıyorum, tamamen sil" — motor, API, panel, kenar çubuğu, `macros/`, not sayfası kaldırıldı.
- Görü modelleri: "basınca çalışsın, yoksa çalışmasın" → `core/vision_worker.py`: YOLO-World + EasyOCR
  ayrı alt süreçte, 2 dk boşta kapanır. Süreç içi bırakma (`core/idle_model.py`) ölçüldü ve belleği
  geri VERMEDİ (torch ayırıcısı); alt süreç ölünce 1,8–2,6 GB tamamen dönüyor. Aıron 14 MB'ta kalıyor.
  Bedel: uzun aradan sonra ilk çağrı ~6 sn (eskiden ~2,5), sıcakken 0,6 sn.
- MSAA: "yok, yapma" — dokunulmadı.
- OneDrive: taşındı → `C:\Users\yunus\Projects\Airon` (69.904 dosya, 2,5 GB, 0 hata; venv yeniden
  kurulmadan çalıştı, 121/121 test). Güncellenen: masaüstü kısayolu, Claude MCP kaydı (`claude mcp
  get airon` → Connected), Obsidian kasa kaydı (yedek `obsidian.json.bak-airon-tasima`). Eski klasör
  silindi (OneDrive çöp kutusunda 30 gün). **Yedek notu:** git'e girmeyen `config/api_keys.json` ve
  `memory/` artık OneDrive'da değil — ayrı yedek kurulmadı.

---

## Faz 1 — PC ucu: telefondan Claude'a iş

```
[Telefon · Aıron Mobil] ──Tailscale + PIN──> POST /api/remote/claude
                                              │ iş kuyruğu (job id, tek seferde 1 iş)
                                              ▼
                        claude -p "<görev>" --output-format stream-json   (cwd: C:\Users\yunus)
                                              │ hafıza, CLAUDE.md, skill'ler, Codex yüklü
                                              ▼
                        GET /api/remote/claude/{id} → durum + özet
```

- `backend/api/remote.py`'ye iki uç: `POST /remote/claude` (başlat), `GET /remote/claude/{id}`
  (durum, son adım, özet). Var olan PIN/çerez kapısının arkasında.
- **Araç kısıtı yok (kullanıcı kararı):** Claude tam yetkiyle çalışır. Tek güvence,
  normal oturumdaki davranışın aynısı: geri alınamayan adım (toplu silme, ödeme,
  başkasına mesaj/yayın, force push) öncesi bir kez sorulur — Faz 2'de soru telefona gider.
  Faz 1'de bu adımlara gelen iş durur ve "onay bekliyor" durumuna geçer.
- Her işin tam logu PC'de (`logs/claude-jobs/<id>.jsonl`), süre/tur sınırı (takılan iş
  sonsuza kadar kotayı yemesin).
- Test: PC'den curl ile iş ver → biter → özet döner; kapı olmadan 401.

### Faz 1 — yapılan (2026-10-03)

`backend/core/claude_jobs.py` + `backend/api/remote.py` sonundaki uçlar:
`POST /api/remote/claude {task, resume_of?}` · `GET /api/remote/claude` (son 10) ·
`GET /api/remote/claude/{id}` · `POST /api/remote/claude/{id}/cancel`. Kapı: `/api/remote/*` public değil.

- **Durumlar:** `queued → running → done | needs_approval | failed | timeout | cancelled`; Aıron
  kapanırken yarıda kalan iş açılışta `interrupted`. Telefona giden alanlar: `last_step` (canlı tek
  satır), `steps`, `summary` (sesli okunacak son mesaj), `approval`, `session_id`, `cost_usd`.
- **İzin modu `auto`** (araç kısıtı yok kararına en yakın güvenli hâl: bu oturumun kendisi gibi,
  tehlikeli adımı sınıflandırıcı durdurur) + `--append-system-prompt`: geri alınamayan adımda dur,
  `ONAY_GEREKLI: <ne>` yaz. Telefon cevabı `resume_of` ile aynı oturumu `--resume` eder.
- **Enjeksiyon:** `claude` npm başlatıcısı `.CMD` — argüman cmd.exe'den geçer. `claude.exe`
  doğrudan çalıştırılıyor, görev stdin'den gidiyor; exe bulunamazsa iş başlamaz.
- **Süreç ağacı = Windows Job Object** (Astra): askıda başlat → job'a ata → uyandır;
  `KILL_ON_JOB_CLOSE`. Süre sınırı (45 dk), iptal ve Aıron'un kapanması/çökmesi bütün ağacı
  öldürür — Claude'un arka planda başlattığı ve stdout'u tutan torunlar dahil (eskiden kuyruk kilitlenirdi).
- Tek iş + 3'lük kuyruk; kayıt `logs/claude-jobs/<id>.json(l)`, son 30 iş, log iş başına 20 MB.

**Doğrulama:** pytest 145/145 (iş yöneticisi 24: Sol 15 + Claude 9 Astra regresyonu). Canlı, gerçek
`claude`: sayma görevi 12 sn `done`; silme görevi `needs_approval` ("…kalıcı olarak sileceğim") →
"evet" ile `resume` → aynı oturumda silip `done`. Astra 1. tur 7 bulgu (5 yüksek), hepsi doğrulandı ve
düzeltildi; bir yarışı Sol da ayrıca yakaladı. Astra 2. tur 3 bulgu: Job Object kurulamazsa
psutil yedeği aynı kilidi geri getiriyordu (kritik) → artık iş başlatılmaz, `failed`; log kotası tek
büyük satırla aşılıyordu; budama `*.json.backup`'ı da siliyordu. Üçü düzeltildi, testli.

**Kalan:** telefondan gerçek deneme (Aıron Mobil'de araç yok → Faz 3); `/m` web arayüzüne iş kutusu yok.

## Faz 2 — Onay ve bildirim
- Claude Code `PreToolUse` hook'u geri alınamayan araç çağrısını yakalar → Aıron'a sorar →
  telefonda "Şunu yapacak, onay?" → evet/hayır işe geri döner.
- İş bitince telefona bildirim; araba modundaysa Aıron sesli okur.

## Faz 3 — Mobil araçlar ve takip
- Kotlin: `delegate_to_claude(görev)`, `claude_job_status()` araçları (Gemini Live
  tanımı: "PC'de uzun iş, kod, dosya, Etsy → buna ver"). Mekanik kısım Codex'e.
- `--resume <session>` ile takip: "bir de şunu ekle" aynı bağlamdan devam eder.

## Teslim öncesi
- Uzaktan erişim + tam yetkili ajan = güvenlik kodu → Astra read-only çapraz inceleme.
- Gerçek senaryo: telefon hücresel veriyle (Wi-Fi değil) iş verir, PC'de biter, sonuç
  telefona sesli gelir.
