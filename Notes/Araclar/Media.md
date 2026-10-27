---
tags: [chiron, arac]
---

# Media — actions/media.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Browser]]

`play_media(query, provider="auto", autoplay=True)`:
- `provider="spotify"` → `_play_spotify()`: `spotify:search:{query}` URI şemasını `start` ile açar
  (Spotify masaüstü kurulu olmalı)
- `provider="youtube"`/`"yt"` → [[Browser]]'daki `play_youtube` eylemini çağırır
- `"apple music"/"music"` → Windows'ta Apple Music yok, otomatik YouTube'a yönlendirilir
- `provider="auto"` (varsayılan) → önce Spotify URI dener, "açılamadı" hatası dönerse YouTube'a düşer

Pano kopyalama yardımcı fonksiyonu (`_copy_to_clipboard`) var ama `play_media` içinde
kullanılmıyor — muhtemelen ileride/eski kod kalıntısı.

Tool: `play_media` ([[Arac-Tanimlari]]).
