---
tags: [chiron, arac]
---

# Screen-Vision — actions/screen_vision.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Webcam]]

`analyze_screen(query, target="active_window")` — sadece aktif pencereyi destekler:
1. `ctypes` ile aktif pencere başlığını okur (`GetForegroundWindow`)
2. `mss` ile birinci monitörün tam ekran görüntüsünü alır, geçici PNG'e kaydeder
3. `_image_looks_blank()` ile siyah/boş ekran kontrolü yapar
4. `VISION_MODELS` sırasıyla dener (`gemini-2.0-flash` → `2.5-flash-lite` → `2.5-flash`),
   her biri için 3 retry (geçici hatalarda: 503/429/timeout/quota vb. — `_is_transient_vision_error`)
5. Görüntü 1800px'e küçültülür, 5.5MB'ı aşarsa JPEG'e düşer

Sonuç formatı: `[Aktif pencere: <başlık>]\n<analiz>`. Geçici dosya `finally` bloğunda silinir.

Tool: `analyze_screen` ([[Arac-Tanimlari]]). [[Webcam]]'daki kullanılmayan `webcam_vision.py` ile
neredeyse aynı görüntü/retry mantığını taşıyor — ortak bir yardımcı modüle çıkarılabilir.
