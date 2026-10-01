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
