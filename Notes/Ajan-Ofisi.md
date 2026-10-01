---
tags: [airon, ajan-ofisi, claude-code, codex, arayuz]
---

# Ajan Ofisi

Bağlı: [[Home]] · [[Plan-Claude-Entegrasyonu]] · [[Arayuz]] · [[MCP-Server]] · [[Bilinen-Tuzaklar]]

Kenar çubuğundaki **Ajanlar** modülü tam ekran bir hologram ofis açar: Claude
(şef), alt ajanlar, Codex Sol/Astra, Space Bunny, Gemini ve OpenCode birer
masada. Masaya tıklayınca kim olduğu, rolü, şu an hangi işte olduğu, işi kimin
verdiği, canlı akışı, dosyaları, token'ı ve kanıtı görünür. "Pano" sekmesi aynı
işleri kanban olarak gösterir. Esin: Muratify AI'ın AgentSpace'i (2026-10-02).

**Fark:** Ofis ajan ÇALIŞTIRMAZ. Var olan düzeni gözler — salt okunur (Faz A).
İş vermek Faz 1'de (`/api/remote/claude`) gelecek.

## Veri nereden geliyor

```
Claude Code ──hook (async)──> %LOCALAPPDATA%\airon\ofis\events.jsonl ─┐
Codex exec ──kendi kaydı───> ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl ─┤
                                                                       ▼
                         backend/core/ofis.py  OfficeWatcher (1 sn'de bir stat)
                                   │  OfficeState (saf durum makinesi)
                     WS office_update ─┤── GET /api/office/state | workers/{id} | desks/{id}
                                   ▼
             frontend/components/office/*  +  three/office/* (ayrı Canvas)
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
