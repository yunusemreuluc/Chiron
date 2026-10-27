---
tags: [chiron, arac]
---

# Youtube-Stats — actions/youtube_stats.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Bellek-ve-Config]]

`get_youtube_channel_report(query, handle="", video_limit=6)` — YouTube Data API v3 (public,
Studio değil) ile kanal raporu üretir. `youtube_api_key` gerekli ([[Bellek-ve-Config]] →
`config/api_keys.json`); handle verilmezse `youtube_channel_handle` ayarı kullanılır.

Akış: `_fetch_channel_payload` (kanal istatistikleri) → `_fetch_recent_videos` (uploads playlist'ten
son videolar + istatistikleri) → ortalama izlenme/beğeni/yorum, en güçlü video, yayın temposu
(ortalama gün aralığı), trend cümlesi (`_trend_sentence` — son yarı vs önceki yarı izlenme oranı).
`query` içinde "detay/analiz/rapor" geçerse son 3 videonun satır satır dökümü eklenir.

API hataları (`_api_get`) kullanıcı dostu Türkçe mesaja çevrilir: `keyInvalid`, `quotaExceeded`,
`accessNotConfigured/forbidden`.

Tool: `get_youtube_channel_report` ([[Arac-Tanimlari]]).
