---
tags: [chiron, ajan-ofisi, claude-code, codex, arayuz]
---

# Ajan Ofisi

Bağlı: [[Home]] · [[Plan-Claude-Entegrasyonu]] · [[Arayuz]] · [[MCP-Server]] · [[Bilinen-Tuzaklar]]

> **2026-10-26:** 3D hologram sahne kaldırıldı; yerine 2D pixel-art **uzay istasyonu** (§ Uzay istasyonu,
> en altta). Aşağıdaki 3D sahne / EffectComposer notları tarihçe olarak duruyor.

Kenar çubuğundaki **Ajanlar** modülü tam ekran bir hologram ofis açar: Claude
(şef), alt ajanlar, Codex Sol/Astra, Space Bunny, Gemini ve OpenCode birer
masada. Masaya tıklayınca kim olduğu, rolü, şu an hangi işte olduğu, işi kimin
verdiği, canlı akışı, dosyaları, token'ı ve kanıtı görünür. "Pano" sekmesi aynı
işleri kanban olarak gösterir. Esin: Muratify AI'ın AgentSpace'i (2026-10-02).

**Fark:** Ofis ajan ÇALIŞTIRMAZ. Var olan düzeni gözler — salt okunur (Faz A).
İş vermek Faz 1'de (`/api/remote/claude`) gelecek.

## Veri nereden geliyor

```
Claude Code ──hook (async)──> %LOCALAPPDATA%\chiron\ofis\events.jsonl ─┐
Codex exec ──kendi kaydı───> ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl ─┤
                                                                       ▼
                         backend/core/ofis.py  OfficeWatcher (1 sn'de bir stat)
                                   │  OfficeState (saf durum makinesi)
                     WS office_update ─┤── GET /api/office/state | workers/{id} | desks/{id}
                                   ▼
             frontend/components/office/*  +  office/station/* (2D tuval; eskiden three/office)
```

- **Hook:** `~/.claude/hooks/ofis-olay.py` — repo DIŞINDA, `~/.claude/settings.json`'da
  11 olaya `async: true` ile bağlı (yedek `settings.json.bak-ofis`). Claude'u asla
  bekletmez; hata olursa sessiz çıkar. Sadece stdlib, Python311 (hermes venv'i değil).
- **Codex kaydı:** model, sandbox, adım adım komut, gerçek token ve **kota yüzdesi**
  (`rate_limits.primary/secondary.used_percent`) buradan. Yalnız `originator=codex_exec`
  oturumları lane sayılır.

## Kim ne yapıyor — çıkarım kuralları

| Olay | Sonuç |
|---|---|
| `UserPromptSubmit` | Şefe yeni kök görev (G-0001…) |
| `UserPromptSubmit` `<task-notification>` ile başlıyorsa | Yeni görev DEĞİL — içindeki `tool-use-id` ile arka plan lane'ini/alt ajanı kapatır (exit code ≠ 0 → hata) |
| `PreToolUse` `Agent` | Alt ajan masasına işçi; `SubagentStart` ona bağlanır (FIFO, tür eşleşmeli) |
| `PreToolUse` Bash/PowerShell `codex exec` / `bunny.py` / `opencode run` / `gemini -p` | İlgili masaya lane |
| Codex `turn_context` | Lane'e bağlanır: açık `-m` uymalı, `-C`/`cd` dizini uymalı; birden çok aday → en eski, "tahmini" diye yazılır |
| `PermissionRequest` | Onay kuyruğu + kehribar durum |
| `Stop` / `SessionEnd` | Tur biter / oturum kapanır, açık işler "durdu" |

Test kanıtı: Bash komutu `pytest`, `npm run build`, `tsc`… içeriyorsa çıktının
sonundan yeşil/kırmızı/bilinmiyor çıkarılır ve kök görevin kanıt kartına yazılır.

## Tuzaklar (yaşandı)

- **Async hook'lar sırasız yazabilir.** `SubagentStart`, `PreToolUse(Agent)`'tan önce
  gelebilir → yetim işçi açılır, sonra sahiplenilir (çift sayım yok). İzleyici her
  turdaki partiyi `ts`'ye göre sıralar.
- **Git Bash yolu** (`/c/Users/...`) ile Codex'in `C:\Users\...` yolu aynı dizin —
  `_same_dir` çeviriyor. Yoksa Codex lane'i hiç bağlanmıyordu (canlı veride bulundu).
- **Bash yanıtı bir sözlük** (`stdout`, `stderr`, `isImage`…). Sonucun "kuyruğu"
  JSON'un sonundan alınırsa `77 passed` satırı kesilir — hook `stdout`'u alır.
- **EffectComposer'ı yeniden render etme.** Çocukları her ebeveyn render'ında yeni
  kimlikle gelince geçişler sökülüp kuruluyor ve ofis sahnesi siyaha düşüyordu.
  Işık/zemin/bloom `StaticStage` (memo, prop yok) içinde; değişen kısım `LiveOffice`.
- **drei `<Html>` etiketleri** sahnenin istifleme bağlamında kalmalı
  (`.office-view__stage { isolation: isolate }`) — yoksa panonun üstüne çıkıyorlar.
- Gizli değer maskeleme **iki yerde**: hook ve `ofis.py` (Codex yolu). Biri değişirse ikisi.

## Performans

- Ofis açıkken ana çekirdek sahnesi `frameloop="never"` — GPU iki sahne çizmiyor.
- Pano sekmesinde ofis Canvas'ı da durur.
- İzleyici turu ~15 ms (gerçek veriyle), anlık görüntü ~4 KB; arayüz açık değilse
  (`manager.has_clients()`) yayın yapılmaz.

## Testler

`tests/test_ofis.py` — durum makinesinin her yolu, izleyici (yarım satır, döndürme,
aynı boyda yeni dosya, Codex kaydının lane'den önce okunması), API, Astra
incelemesinin 11 bulgusu ve canlı veride bulunan 3 hata için regresyon.

## Sınırlar

- Claude'un kendi token'ı henüz yok (transcript `usage` alanları — Faz A.5).
- Ofisten iş verme / durdurma yok (Faz 1). Onay Claude Code penceresinde verilir.
- Arka plana atılan bir lane'in bitişi, Claude o bildirimi işlemezse (oturum
  kapandıysa) bilinmez — "durdu, bitişi izlenemedi" yazar, tahmin etmez.

## Yazılabilir pano (2026-10-26, Ajan İstasyonu adım 1+2)

Plan: [[Plan-Ajan-Istasyonu]]. Sekmeler artık **Ofis · Pano · Etkinlik**. "Etkinlik" eski gözlem
panosu (`TaskBoard.tsx`, salt okunur). "Pano" yazılabilir: `components/office/CardBoard.tsx`.

```
CardBoard ──2 sn yoklama──> GET /api/pano ──> backend/core/pano.py (Pano)
   düğmeler ──POST /api/pano/{id}/start|pause|stop|answer──┘      │ kart durumu iş kuyruğundan türetilir
                                                                  ▼
                                   backend/core/claude_jobs.py  submit(origin="pano")  → claude -p
```

- **Kart durumları:** bekliyor → calisiyor ↔ duraklatildi / onay / hata → bitti / iptal.
  Kart kendi durumunu uydurmaz: `_reconcile` her okumada işin gerçek durumuna bakar.
  Durdur/Sonlandır işi iptal eder; iptalden sonra kartın nereye düşeceğini `intent` söyler.
- **Devam:** aynı Claude oturumu `--resume` ile (`session_job`). İş `KEEP_JOBS` geçmişinden
  düşmüşse görev baştan verilir. Kuyruk doluysa kart değişmez, hata söylenir.
- **`origin="pano"`:** sistem notu `PANO_NOTE` (özet sesli okunmuyor, kartta), iş `notified=True`
  doğar → telefona haber verilmez. Telefondan gelen işler eskisi gibi.
- **Kayıt:** `config/pano.json` (git dışı). Okunamayan dosya silinmez, `pano.bozuk-<ts>.json`
  olarak kenara alınır. Kullanıcı eyleminde diske yazılamazsa hata döner (`_commit`); kart açma
  geri alınır.
- **Ölçüm (gerçek iş):** önemsiz bir kart bile ~0,39 $ — her `claude -p` oturumu hafıza köprüsü ve
  hook'larla açılıyor. 7/24 döngüde kart başına maliyet buna göre düşünülmeli.

Testler: `tests/test_pano.py` (19; sahte kuyrukla durum makinesi + gerçek `ClaudeJobs` + API).
Çapraz inceleme: Astra yok (ücretsiz plan) → Terra read-only; 3 kalıcılık bulgusu, üçü düzeltildi.

## Proje kartı — ayrı kopya, test, onaylı birleştirme (2026-10-26, adım 3)

Kart açarken **Proje** seçilirse (`GET /api/pano/repos` → `~/Projects` altındaki git depoları) iş
o deponun ayrı bir worktree'sinde yapılır. Kod: `backend/core/pano_git.py` (git/test) + `pano.py` (durum).

```
Başlat ──> worktree ~/Projects/.pano-worktrees/<repo>-K-001, dal pano/K-001 (ana dalın ucundan)
Claude worktree'de çalışır (cwd = worktree; commit/push/merge YAPMA notu görevde)
bitti ──> dogrulaniyor: Chiron commit_all → test komutunu KENDİSİ koşar → reset_after_test
          ├─ değişiklik yok → bitti, kopya + dal silinir
          ├─ test kaldı → hata (çıktının kuyruğu kartta; Yeniden dene aynı oturumu sürdürür)
          └─ test geçti / test yok → birlestir ──Birleştir──> ana klasörde merge --no-ff → bitti
                                               └─Reddet──> iptal, kopya silinir, DAL KALIR
```

- **Birleştirme kuralları:** ana klasör kartın açıldığı dalda olmalı; izlenen dosyalarda commit'lenmemiş
  değişiklik varsa birleştirme REDDEDİLİR (Yunus'un yarım işi korunur). Çakışmada `merge --abort`,
  kart `hata`ya düşer ve hata metni Claude'a "worktree'de `git merge <ana dal>` yap" der.
  ⚠ Chiron'un kendi deposu şu an commit'siz değişiklik taşıdığı için Chiron kartları birleşemez —
  önce commit.
- **Test komutu:** kabukta, Claude'un izin denetimi OLMADAN koşar. Bu yüzden uzaktan (telefon)
  yalnızca `suggest_test` önerisi ya da boş kabul edilir (403); özel komut yalnız PC'den.
  Süreç ağacı Job Object'te (zaman aşımı 15 dk, Chiron kapanınca test de ölür).
- **Test artıkları:** test `commit_all`'dan SONRA koştuğu için HEAD'den farklı her şey testin ürünü;
  `reset --hard` + `clean -fd` ile atılır. Önceden (canlı deneme) `__pycache__` yüzünden
  `worktree remove` reddediyor, dal silinemiyordu.
- **Hiçbir iş kaybolmaz:** kopya zorla silinmeden önce kalan iş dala commit'lenir ("kopya silinirken
  kalan iş"). Test sürerken kart sonlandırılamaz/silinemez.
- **Bilinen sınır:** birleştirme ve kopya silme pano kilidi altında (birkaç sn); yavaş diskte pano
  o sürede donar (Terra, düşük önem — bilinçli bırakıldı).

Canlı deneme: geçici depoda hatalı `carp` fonksiyonu → Claude düzeltti, Chiron test koştu (1 passed),
birleştirme commit'i oluştu, dal ve kopya temizlendi. Testler: `tests/test_pano_worktree.py` (21;
Codex Terra 16 + Claude 5 gerileme). Terra read-only: 6 bulgu, 5'i düzeltildi, 1'i (kilit) bırakıldı.

## Lider ajan Jarvis ve ekip (2026-10-26, adım 4)

> **2026-10-29:** Lider ajanın görünen adı **Chiron** ("ekipte Jarvis yazıyor, Chiron koy"): arayüz, planlama promptu,
> kart hatası. İç kimlik `jarvis` (istasyon koltuğu, Komuta kişisi) değişmedi.
>
> **Alt ajanlar:** iş kayıtları tarandı — Komuta/telefon işlerinde Agent aracı HİÇ çağrılmamıştı. `TEAM_NOTE`
> (backend/core/claude_jobs.py) telefon, sohbet ve sohbet_tel notlarına eklendi: büyük ve bölünebilir işte
> Explore / general-purpose alt ajanlara paralel dağıt, birleştir, kendin doğrula; küçük işte açma.
> Pano lider akışı (plan modu) ayrı, ona eklenmedi. Gerçek bir işte henüz gözlenmedi.

**Motorlar:** `claude_jobs` artık üç motoru aynı kuyrukta, aynı Job Object ve süre sınırıyla koşar
(`Job.engine`): `claude` (stream-json), `codex` (`node codex.js exec --json -m gpt-5.6-terra --sandbox
workspace-write -C <worktree> -`), `gemini` (`node gemini.js --approval-mode plan -o text`, salt okunur).
Codex/Gemini `.cmd` başlatıcıyla DEĞİL `node <betik>` ile, görev stdin'den (BatBadBut). Codex olayları
(`thread.started`, `item.completed`, `turn.completed|failed`) `_codex_event` ile Claude biçimine çevrilir.
Gemini'nin stderr'i stdout'a katılı; "True color / Ripgrep" uyarıları `_GEMINI_NOISE` ile ayıklanır.
Codex/Gemini oturum sürdürmez: "Yeniden dene" görevi baştan, notla verir. Gemini kartı kopya açmaz.

**Jarvis:** "Jarvis'e böldür" → `claude -p --permission-mode plan` (salt okunur), görev `LEADER_NOTE`:
ekip tanımı + kurallar + JSON şablonu. `parse_plan` son ```json bloğunu okur, doğrular (en çok 8 görev,
"sonra" yalnız öncekileri gösterir, bilinmeyen ajan → claude). Alt kartlar: `parent`, `after` (bağımlılık;
bitmeden Başlat kapalı), repo ve test komutu üstten miras. Üst kart `bolundu`; alt kartların hepsi kapanınca
`bitti` (hepsi iptalse `iptal`). Bölünmüş kart sonlandırılmaz; açık alt kartı varken silinmez.
Plan okunamazsa üst kart `hata`, "Yeniden dene" yeniden planlatır.

**Terra'nın kotası:** ChatGPT free planında Codex kotası 2026-10-26'da doldu ("usage limit ... try again at
Nov 24th, 2026 10:02 PM"). Codex kartı bu hatayla düşünce pano tarihi okur (`codex_retry_at`),
`config/pano.json`'da `codex_blocked_until` olarak saklar: Jarvis'e "codex kullanılamaz" denir, yine verirse
o görev Claude'a çevrilir, codex kartı başlamaz. Kartın ajanı bekliyor/durdu/hata durumunda değiştirilebilir
(PATCH `agent`; Claude oturumu başka ajana geçmez, görev baştan). Pano 2026-10-26'da bu bilgiyle başlatıldı.

**Codex `-C` yan etkisi:** Codex her `-C` klasörünü `~/.codex/config.toml`'a `trust_level = "trusted"` diye
yazıyor; worktree'ler için satır birikir (zararsız, ara sıra temizlenebilir).

Canlı deneme: Jarvis küçük bir kartı iki Terra görevine böldü (README ikincisinin "sonra"sında); Terra ilkini
yaptı, kendi sandbox'ında testi koşamadı (venv) ama Chiron koştu → geçti → birleşti. Testler:
`tests/test_pano_leader.py` (Terra 19, kotası dolarken yazdı + Claude 5 kota testi); paket 174/174.
Çapraz inceleme YAPILAMADI: Terra kotası dolu, Astra yok, özel kod Gemini'ye gitmez — Claude kendi inceledi.

## Uzay istasyonu (2026-10-26, adım 5)

Kullanıcı kararı: ofis 3D hologram yerine **2D pixel-art uzay istasyonu** (sebep GPU/CPU: 7/24 açık ekran,
telefonda okunurluk). Taslak `Docs/onizleme/ajan-istasyonu.html` → `components/office/station/`:
`stationArt.ts` (piksel çizimler, 224×160 tuval, 1 birim = 16 px) + `StationScene.tsx` (canlı veri → hareket).
`three/office/*` silindi (git geçmişinde).

| Karakter | Masa (ofis.py) | Görünüm |
|---|---|---|
| Jarvis | `claude` | kaptan (mavi üniforma, pelerin), kaptan koltuğu |
| Terra | `sol` / `astra` | robot; Codex kotası doluyken (pano `agents.codex`) kapsülde uyur "zzz" |
| Gemini | `gemini` | uzaylı |
| Alt ajan | `subagents` | astronot |

- **Davranış** (`goalOf`): masada `onay_bekliyor` işçi → onay terminaline yürür, "?" (öncelikli);
  `calisiyor` → konsoluna yürür, yazar, balonda işçinin `current`'ı; son 3 dk içinde `hata` → konsol kırmızı;
  son 1 dk içinde `bitti` → konsol yeşil; yoksa dinlenme köşesindeki ev konumu. Yürüme koridordan (z=0,7).
- **Tıklama:** karaktere ya da konsoluna tıkla → `selectDesk` → var olan `AgentCard` (canlı akış).
- **Performans:** 15 fps, `document.hidden`'da ve Pano/Etkinlik sekmesinde hiç çizilmez; tuval tam sayı
  katla büyür (keskin piksel). Etiketler React'e değil doğrudan DOM'a (`transform`) yazılır.
- **Tuzak (yaşandı):** ev konumları dikeyde 1,5 birimden yakınsa isim etiketleri üst üste biniyordu.
- Bilinçli eksik: Bunny/OpenCode masaları sahnede yok (araçlar kaldırıldı); "Jarvis kart dağıtıyor"
  animasyonu, kart sayısına göre yoğunluk ve gece modu sonraya.

## Claude kotası — fren (2026-10-26, adım 6)

Fikir: ruvnet/ruflo `ruflo-cost-tracker` (basamaklı uyarı; kod alınmadı). Ama sayı tahmin değil: Claude Code
stream-json her işte `rate_limit_event` gönderiyor → `rate_limit_info.unifiedWindows.{five_hour,seven_day}
.utilization` (0..1) + `resetsAt`. `claude_jobs._note_limits` son değeri `logs/claude-jobs/limits.json`'a yazar
(iş kaydı sanılmaz, budanmaz); `jobs.limits()`.

- **Basamaklar** (`pano._claude_quota`, en dolu pencereye göre): %50 bilgi · %75 uyarı (kehribar) ·
  **%90 dur** (mercan). Dur %100 değil %90: Yunus'un terminaldeki kendi işine pay kalsın.
  `status: rejected` gelirse `resetsAt`'e kadar dur. Sıfırlanmış pencerenin eski doluluğu 0 sayılır.
- **Dur ne yapar:** yeni Claude işi (Başlat, Jarvis'e böldür, Onayla) PanoError ile reddedilir, mesajda yüzde,
  pencere ve sıfırlanma saati. Çalışan iş KESİLMEZ. Gemini/Codex kartları Claude kotasından etkilenmez.
- **Görünüm:** Pano'nun üstünde kota şeridi (+ Terra uyuyor notu); ofis üst şeridinde "Claude kota" çubukları
  (`OfficeView`, 30 sn'de bir `/api/pano`).
- **Sınır:** sayı yalnız Chiron'un başlattığı Claude işlerinden geliyor; terminal oturumları bildirmez. Chiron
  uzun süre iş başlatmazsa gösterilen değer bayatlar (`seen` zamanı tutuluyor). İlk değer 2026-10-26'da
  bugünkü iş kayıtlarından yazıldı.

Testler: `tests/test_pano_quota.py` (11; Claude yazdı — Codex kotası dolu). Paket 185/185.

## Bekçi — ajanın tehlikeli adımı (2026-10-26, adım 7)

Fikir: ruvnet/ruflo `ruflo-protector` (kod alınmadı). Kod: `backend/core/bekci.py` (yalnız stdlib).
Kullanıcı kararı: global `~/.claude/settings.json`'a DOKUNULMAZ (ilk deneme güvenlik denetiminde durmuştu).

- **Katman 1, araç öncesi (yalnız Claude):** `claude_jobs` her `claude -p`'ye `--settings logs/bekci/settings.json`
  ekler; içinde PreToolUse hook'u → `python backend/core/bekci.py`. Ayar yalnız o oturuma, worktree'de değil
  (ajan kendi bekçisini kapatamasın). 2026-10-26 gerçek işle denendi: hook `-p`'de tetikleniyor,
  `CHIRON_CLAUDE_JOB` geliyor, `deny` adımı durduruyor.
- **Katman 2, birleştirme öncesi (her motor):** `_verify` worktree diff'ini `scan_diff` ile tarar — eklenen
  anahtar/parola, `.env`/anahtar dosyası, `.claude`/`.git/hooks`, CI dosyası. Codex/Gemini'yi bu katman görür.
- **13 kural:** toplu-silme, git-push, git-yikici, dis-gonderim (curl POST, rclone, gh pr…), indir-calistir,
  yayinlama, sistem-ayari, surec-oldurme (orta), izin-atlatma, gizli-ortam (orta), kok-disi-yazma (worktree
  dışına Write/Edit; `~/.claude/projects` ve `Temp/claude` serbest), gizli-dosya, kafes (ajanın kendi
  ayarı/hook'u/bekçi). Diff katmanında ayrıca gizli-deger, ci-degisikligi.
- **Mod** (`logs/bekci/mod.json`): `uyar` varsayılan — her araç çağrısı `logs/bekci/<iş>.jsonl`'e yazılır
  (öğrenme verisi), takılan kural kartta "Bekçi" kutusunda. `engelle` — yalnız `yuksek` kural reddedilir,
  Claude gerekçeyi görür ve `ONAY_GEREKLI:` ile durur (gerçek işte denendi, kart "onay"a düştü).
  Mod Pano'daki Bekçi şeridinden değişir; engellemeyi kapatmak onaylı; **telefondan değişmez** (403).
- **Hata davranışı:** bekçinin kendi hatası işi durdurmaz (çıkış 0, `logs/bekci/hata.log`). Hook 10 sn'de
  cevap vermezse Claude Code adımı geçirir — yani engelleme "fail-open".
- **Sınırlar:** kurallar desen eşleşmesi; kabukta dolaylı yazma (`> dosya`, python -c) kök kuralına takılmaz.
  Telefon işlerinde de hook çalışır ama uyarı yalnız `Job.bekci`'de, telefon arayüzü göstermiyor.
  Kart Chiron'un kendi bekçisini düzenlemek isterse `kafes`'e takılır (bilerek).

Testler: `tests/test_bekci.py` (41). Paket 226/226. Çapraz inceleme yapılamadı (Codex kotası yok); Claude kendi inceledi.

## 7/24 döngü (2026-10-26, adım 8)

Kod: `backend/core/dongu.py`; durum `config/dongu.json`, raporlar `logs/dongu/rapor-YYYY-MM-DD.md` (ikisi de gitignore).
Thread Chiron'la açılır (`main.py` lifespan), **döngü varsayılan kapalı**; Pano'daki "7/24" şeridinden açılır.
Telefondan da açılıp kapanır (açmak korumayı gevşetmez; bekçi ve kota freni aynen geçerli).

- **Ne yapar:** açıkken "Bekliyor" sütunu kuyruktur — hiçbir kart çalışmıyorsa en eski hazır kartı (bağımlılıkları
  `bitti`) başlatır, tek seferde tek iş. Jarvis'in alt kartları sırayla kendiliğinden yürür. Her tikte
  `pano.snapshot()` → proje kartının doğrulaması (commit + test) arayüz kapalıyken de koşar (önceden yalnız
  arayüz yoklayınca koşuyordu).
- **Tik:** boşta 60 sn, kart çalışırken 10 sn; yeni kart açılınca (`POST /api/pano`) hemen uyanır. Tik yerel,
  API çağrısı yok. Ölçüldü: biten karttan sonrakine ~7 sn, yeni karta ~2 sn.
- **Kota:** Claude `stop` basamağında Claude kartları atlanır, durum `uyuyor` + sıfırlanma saati; pencere geçince
  kendiliğinden devam. Codex kotası doluysa Codex kartı atlanır, Gemini yürür.
- **Fren:** günde en fazla `DAILY_LIMIT` (20) kart. Başlatılamayan kart (PanoError ya da başka hata, ör. deposu
  silinmiş → NotADirectoryError) 30 dk atlanır, döngü sıradakine geçer — testte yakalandı, önceden aynı kartta
  kilitlenirdi.
- **Yapmaz:** kart bölmez, hata vereni yeniden denemez, onay/birleştirme vermez — o kartlar Yunus'u bekler.
- **Sabah raporu:** her gün 08:00 (yerel), son rapordan beri: bitenler, Yunus'u bekleyenler, hatalar, bekçi
  uyarıları, yaklaşık harcama, kota. Chiron 08:00'de kapalıysa ilk açılışta yazılır (denendi). Pano'da 18 saat
  görünür, "Tamam" ile kapanır.
- **Uyarı:** döngü açık ve bekçi `uyar` modundaysa şerit "Gözetimsiz çalışıyor ama bekçi yalnız uyarıyor" der.
- **Sınır:** PC uyursa döngü de uyur (Windows uyku ayarına dokunulmadı). Rapor maliyeti kartın toplam
  maliyetinden; rapor aralığından önceki harcamayı da içerebilir (~ işareti bu yüzden).

Testler: `tests/test_dongu.py` (9). Paket 235/235. Canlı: 2 Claude + 4 Gemini kartı döngüyle sırayla yürüdü.

## Komuta ekranı ve sohbet (2026-10-27)

Yunus: "sana terminalde nasıl iş veriyorsam Chiron'da da öyle olsun" + mevcut ofis/pano "kullanışsız" (boş
sütunlar, üç şerit, iş üç sekmeye dağılmış). Taslak: https://claude.ai/artifact/9gfiWpCSyYSWTGuTxU1SYU.

- **Sekmeler:** Komuta · İşler (eski Pano, `CardBoard`) · Geçmiş (eski Etkinlik, `TaskBoard`). Tam ekran
  istasyon sahnesi kalktı; istasyon Komuta'nın sağ üstünde küçük pencere (`StationScene mini onPick`) —
  karaktere tıklamak o ajanın sohbetini açar.
- **Komuta** (`components/office/Komuta.tsx`): solda ekip (durum ofis masalarından + sohbetten, Terra kota
  uykusu panodan) ve sohbet listesi + "PC'deki oturumlar"; ortada sohbet (araç adımları, canlı satır, onay
  kutusu, hafif Markdown); sağda mini istasyon, senden bekleyenler (sohbet onayları, kart onay/birleştirme,
  PC'deki Claude Code izinleri), sıra, bekçi ve 7/24 anahtarı.
- **Sohbet** (`backend/core/sohbet.py`, `/api/sohbet`): her mesaj `claude_jobs`'a `origin="sohbet"` iş; ilk
  mesaj oturum açar, sonrakiler `submit(session_id=...)` ile `--resume`. Kimlik her iş bitince işten alınır
  (`-p --resume` yeni kimlik dönerse izlenir; canlıda aynı kaldı). Gemini oturum sürdürmez: son 8 mesaj bağlam
  olarak görevin başına. Onay: `ONAY_GEREKLI` → mesaj "onay", Onayla/Reddet aynı oturuma yazar. Kayıt
  `config/sohbet.json` (gitignore). İşte `trail` alanı: araç adımları sırayla (en fazla 30).
- **Terminali devral:** `~/.claude/projects/*/<id>.jsonl` içinden son 14 günün etkileşimli (`entrypoint: cli`)
  oturumları; başlık `ai-title`, son mesaj `last-prompt` (dosyanın yalnız başı + son 256 KB okunur). Açık sayılır:
  kayıt son 2 dk'da değişti ya da ofis SessionEnd görmedi (`office.session_active`, 6 sa ufuk). Açıksa "Yine de
  devral" onayı istenir. Devralınan sohbet oturumun kendi klasöründe sürer.
- Canlı: iki mesajlı sohbette ikinci mesaj ilkini hatırladı (KARPUZ / `pwd`), arayüzden uçtan uca denendi.
  Gerçek bir terminal oturumu devralınarak denenmedi (Yunus'un kayıtlarına yazardı) — birim testte.

Testler: `tests/test_sohbet.py` (11). Paket 246/246.
