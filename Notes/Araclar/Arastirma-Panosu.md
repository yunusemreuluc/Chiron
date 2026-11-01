---
tags: [chiron, arac, arayuz]
---

# Araştırma Panosu — actions/arastirma_panosu.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Arayuz]] · [[Ekran-Icerigi]] · [[PC-Isi]]

**Ne:** "Şunu araştır" → `research_board` arka planda kaynaklı araştırma yapar; ekranın üst ortasında canlı kart
("ARAŞTIRMA // AKTİF", arama/okuma sayaçları). Bitince Chiron sesle haber verir ve "göstereyim mi?" diye sorar;
"göster" → `show_research_board` tam ekran kart duvarını açar (rakam, metin, çubuk grafik, YouTube videoları,
kaynak listesi). `cancel_research` durdurur.

**Neden (2026-11-01):** Yunus huwprosser'ın "ROSE" asistanını (Instagram reel DfGOQ5pIZqy) gördü: "rose'dan bir şey
isteyince ekrana öyle veriyor, biz de yapabilir miyiz". Kare kare bakıldı: asıl iş araştırmanın düz metin değil
**blok** dönmesi, arayüz blokları çiziyor.

## Motor: Claude CLI, Gemini değil

Denendi (2026-11-01): Gemini Google arama bağlaması bu hesapta 429; bağlamayı kabul eden 2.5-flash-lite aramayı hiç
yapmadı (0 kaynak) ve kaynaksız rakam uydurdu. Claude CLI: `-p --model sonnet --tools WebSearch,WebFetch
--allowedTools WebSearch,WebFetch --setting-sources project --strict-mcp-config --output-format stream-json`.
`--tools` tek başına yetmiyor — `--allowedTools` olmadan -p modunda arama "permission denied". Kullanıcı ayarı
yüklenmiyor (global hook'lar/bellek enjeksiyonu gereksiz). Çalışma klasörü boş bir geçici klasör.

Canlı ilerleme stream-json'dan: her `tool_use` (WebSearch = arama, WebFetch = okuma) bir `research_update`. Çubuk
dolmaz, tarar — ilerleme bilinmiyor, sahte yüzde yok; yalnız "pano kuruluyor" aşamasında dolu.

Son mesaj JSON (şema PROMPT'ta): `title, summary, blocks[text|stat|chart], video_queries, sources`. `clean_board`
beyaz liste + uzunluk sınırı uygular (çıktı web içeriğinden besleniyor); 2'den az çubuklu grafik atılır.
Videolar yt-dlp `ytsearch` (extract_flat, indirme yok) — görsel kart yok, çünkü metinden gelen görsel adresi
doğrulanamıyor. Süre sınırı 420 sn, aşılırsa `taskkill /T`.

## Akış ve dosyalar

- Olaylar: `research_update` (running/done/error), `research_show` — `backend/models/events.py`, arayüzde
  `useAIStateConnection.ts`, store `stores/researchStore.ts`.
- Son pano `%LOCALAPPDATA%\Chiron\arastirma\son.json`; arayüz açılışta `/api/research/last`'tan yükler (eski pano
  için canlı kart açılmaz). Tek araştırma aynı anda.
- Sesli haber: `_announcements` listesi, main.py `_watch_research` 3 sn'de bir (yerel, ağ yok).
- "Göster" tepsideyken: `commands.dispatch("show_window")` → `desktop.py TrayController.bring_forward`.
- Arayüz: `components/research/ResearchChip.tsx` (canlı kart), `ResearchBoard.tsx` (tam ekran, z 46, Esc kapatır),
  stiller `app/research.css`.
- **Çekirdek kenara çekilir (2026-11-01, Yunus: "ortadaki animasyon küçülüp kenara geçerek ekranları önüme
  çıkarsın"):** pano yarı saydam, HUD panelleri çekilir (AppShell), çekirdek `CameraRig` içinde `zoom` 0.34 +
  `setViewOffset` ile sağ kolona kayar (merkez sağdan 170 px, yükseklik %62; 1100 px altında sağ alt köşe).
  Kamera geri çekilmiyor çünkü sis (15–44) çekirdeği soldururdu. Pano için `.rb-scroll` sağda 340 px boş kolon
  bırakır; kartlar sağdan, çekirdeğin yanından gelir. Geçişte FrameGovernor 60 FPS'e çıkar. Sahne artık pano
  açıkken durmuyor (önceki opak sürümde duruyordu). Kaynak bağlantıları tıklanmıyor: WebView2'de dış
  bağlantı Chiron penceresinin içinde açılırdı.

## Test (2026-11-01)

"VR sektörünün durumu": 37 sn, 3 arama + 2 okuma, 13 blok (5 metin, 4 rakam, 1 grafik, 3 video), 5 kaynak.
Arayüz sahte sunucuyla (statik `out/` + sahte WS) Playwright'ta 1575x945 çekildi, sayfa hatası yok. Gerçek Chiron
içinde sesli akış (başlat → haber → "göster", tepsiden öne gelme) henüz denenmedi — yeniden başlatma gerekiyor.
