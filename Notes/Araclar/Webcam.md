---
tags: [chiron, arac]
---

# Webcam — main.py (canlı akış) + actions/webcam_vision.py (tek kare, kullanılmıyor)

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Mimari]] · [[Screen-Vision]]

## Aktif yol: canlı akış (main.py)
`toggle_webcam` tool'u (`action=start|stop`) → `main.py._execute_tool` → `WebcamStreamer`
([[Mimari]]) başlatır/durdurur. Akış aktifken `_stream_webcam_frames()` her 1.5sn'de bir en güncel
kareyi doğrudan Gemini Live session'a `send_realtime_input(media=...)` ile yollar — model kareyi
kendi multimodal bağlamında görür, ayrı bir "analyze" çağrısı gerekmez. UI önizlemesi ayrı olarak
~24 FPS güncellenir (`_update_ui_webcam_preview`).

## Kullanılmayan yol: actions/webcam_vision.py
`analyze_webcam(query)` — OpenCV ile tek kare yakalayıp Gemini vision modeline (`gemini-2.0-flash`
vb., retry'li) ayrı bir `generate_content` isteğiyle gönderir. **main.py'den hiç import edilmiyor**,
`tool_defs.py`'de karşılığı yok. [[Screen-Vision]] modülüyle neredeyse aynı görüntü işleme deseni
(`_build_image_part`, transient hata retry mantığı) tekrarlanmış durumda.

Tool: `toggle_webcam` ([[Arac-Tanimlari]]).
