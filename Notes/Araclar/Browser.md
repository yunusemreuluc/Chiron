---
tags: [chiron, arac]
---

# Browser — actions/browser.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Media]]

`browser_control(action, url=None, query=None)` — `webbrowser` modülüyle çalışır, 3 eylem:
- `open_url` — verilen URL'i açar (şema yoksa `https://` ekler)
- `search` — Google arama URL'i açar
- `play_youtube` / `youtube_play` / `play_music` — `_find_first_youtube_video()` ile arama
  sonuçları HTML'inden regex (`"videoId":"([A-Za-z0-9_-]{11})"`) ile ilk video ID'sini çeker,
  `watch?v=...&autoplay=1` açar. Bulamazsa arama sonuçları sayfasına düşer.

[[Media]] modülü `play_media(provider="youtube")` çağrıldığında bu modülün `play_youtube`
eylemini kullanır. Tool: `browser_control` ([[Arac-Tanimlari]]).
