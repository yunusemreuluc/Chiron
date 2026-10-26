---
tags: [airon, ajan-ofisi, plan, 7-24]
---

# Plan: Ajan İstasyonu (ofisten iş veren, 7/24 çalışan sisteme)

Bağlı: [[Ajan-Ofisi]] · [[Plan-Claude-Entegrasyonu]] · [[Home]]

Başlangıç 2026-10-25. Esin: Muratify AI'ın AgentSpace'i (kapalı kaynak masaüstü uygulaması)
ve ruvnet/ruflo (MIT). Ruflo **kurulmuyor**; işe yarayan fikirler Python'a uyarlanıyor,
alınan koda kaynak notu düşülüyor.

## Kararlar (Yunus)

- Ofis **2D pixel-art, uzay istasyonu teması** olacak ("bu daha iyi oldu, sonra iyileştirirsin").
  3D hologram bırakıldı; sebep kaynak: 7/24 açık duran ekran, telefonda okunurluk.
  Taslak: `Docs/onizleme/ajan-istasyonu.html` (artifact: https://claude.ai/artifact/FXrhZmuxgygam4mox13jaL).
- Karakterler: Jarvis = kaptan (Claude, lider), Terra = robot (Codex `gpt-5.6-terra`),
  Gemini = uzaylı, Alt ajan = astronot (Claude). Masa → konsol, onay panosu → onay terminali,
  kahve köşesi → dinlenme kapsülü, kota dolunca kapsülde uyur.
- **Lider ajan = Jarvis**, ayrı bir `claude -p` oturumu; sadece planlar ve kartı böler,
  kod yazmaz. Codex lider olamaz (ücretsiz plan, AGENTS.md orkestrasyonu yasaklıyor).
- Main'e otomatik birleştirme yok; son onay her zaman Yunus'ta.

## Ajanlar (2026-10-25 durumu)

| Ajan | Durum |
|---|---|
| Claude | çalışıyor |
| Codex `gpt-5.6-terra` / `luna` | ücretsiz kota 2026-10-26'da doldu, 24.11.2026 22:02'ye kadar yok; Sol/Astra yok |
| Gemini `gemini-3.8-flash` | çalışıyor |
| Ollama `qwen2.5:7b` | kurulu, denenmedi |
| OpenCode + OpenRouter ücretsiz modeller | kurulu, denenmedi |
| Space Bunny, Hermes Agent | kaldırıldı |

## Sıra

| # | Adım | Ruflo'dan | Durum |
|---|---|---|---|
| 1 | Panoya yazma: kart ekle, Başlat, durdur, sonlandır. Kart yaşam döngüsü: bekliyor → çalışıyor ↔ duraklatıldı → onay bekliyor → bitti/iptal | ruflo-workflows (aşamalar, onay kapıları) | yapıldı 2026-10-26 → [[Ajan-Ofisi]] |
| 2 | Panodan iş başlatma (`claude_jobs.py`'ye bağla) | — | yapıldı 2026-10-26 (1 ile birlikte) |
| 3 | Her iş ayrı worktree + test; birleştirme Yunus onayıyla | — | yapıldı 2026-10-26 → [[Ajan-Ofisi]] § Proje kartı |
| 4 | Lider ajan Jarvis: kartı böler, kime gideceğini yazar | — | yapıldı 2026-10-26 → [[Ajan-Ofisi]] § Lider ajan |
| 5 | 2D uzay istasyonu ofisi (mevcut `three/office` yerine) | ruflo-console "Oda" (incele/kes/sonlandır) | yapıldı 2026-10-26 → [[Ajan-Ofisi]] § Uzay istasyonu |
| 6 | Kota takibi: %50/75/90 uyarı, %100 dur | ruflo-cost-tracker | sırada (Terra kotası adım 4'te kısmen) |
| 7 | Bekçi: 13 kural, önce öğren → uyar; engelleme modunu Yunus açar | ruflo-protector | |
| 8 | 7/24 döngü: kotada dur, sıfırlanınca devam, sabah rapor | — | 6 ve 7 bitmeden açılmaz |

Var olan temel: `backend/core/ofis.py` (izleyici), `claude_jobs.py` (telefondan iş, kuyruk,
onay, süre sınırı), `feature_requests.py` (istek listesi), `components/office/TaskBoard.tsx`
(salt okunur pano).
