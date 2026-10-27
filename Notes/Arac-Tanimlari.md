---
tags: [chiron, araclar, prompt]
---

# Araç Tanımları — tool_defs.py + core/prompt.txt

Bağlı: [[Home]] · [[Mimari]]

## tool_defs.py
`TOOL_DECLARATIONS` listesi — Gemini Live'a fonksiyon çağırma şeması olarak verilir
(`main.py._build_config()` içinde `tools=[{"function_declarations": TOOL_DECLARATIONS}]`).
**33 araç** tanımlı (2026-07-31). Tam liste burada tekrarlanmıyor — kopyası hızla bayatlıyor;
aşağıdaki tablo araçları ilgili nota bağlıyor, kesin liste için `tool_defs.py`.

Her tanım gerçekte çalışan bir fonksiyona karşılık gelmeli. **Eşleşme artık elle yapılmıyor:**
fonksiyonlar `@register_tool("ad")` dekoratörüyle kendilerini `core/tool_registry.py`'ye
kaydediyor, `_execute_tool()` ise `dispatch_tool(name, args, instance=self, loop=loop)` çağırıyor.
Yani `main.py` içinde uzun bir `elif name == "..."` zinciri **yok** — dekoratör imzada `self`
görürse instance'ı otomatik enjekte ediyor.

> Bu not 2026-07-31'e kadar "elif zinciri" diyordu; o yapı registry'ye geçince kaldırılmış ama
> not güncellenmemişti.

Yeni araç eklerken güncellenecek yerler:
1. İlgili modülde fonksiyon + `@register_tool("ad")`
2. Buradaki `TOOL_DECLARATIONS` (Gemini'nin gördüğü şema ve açıklama)
3. `core/prompt.txt` — ne zaman kullanılacağına dair kural/örnek
4. `Notes/Araclar/` altında karşılığı — yoksa aracın ne yaptığı yalnızca kodda kalır

## core/prompt.txt
Sistem promptu — Türkçe konuşma kuralları, her aracın ne zaman çağrılacağına dair kısa açıklamalar
ve örnek konuşma → araç çağrısı eşleştirmeleri içerir. `main.py.load_system_prompt()` bunu okur;
dosya bulunamazsa kısa bir fallback prompt kullanılır (main.py:162).

Önemli davranış kuralları (prompt.txt içinde):
- WhatsApp: kullanıcı açıkça "gönder/yolla" derse `send_now=true`, sadece taslak isterse `false`
- Takvim/hatırlatıcı: göreli zaman ifadeleri gerçek ISO tarihe çevrilmeli (şu anki zaman
  `_build_config()` içinde promptun başına ekleniyor: `[ŞU ANKİ ZAMAN]`)
- Kamera: "bak/gör/göster" → `toggle_webcam(action="start")`, "kapat" → `"stop"`
- Hafıza: önemli bilgi duyulunca sessizce `save_memory` çağrılır

## Detaylar — araç → not

33 aracın tamamı bir nota bağlı. Bir araç bu tabloda yoksa notu da yok demektir.

| Araç | Not |
|---|---|
| `open_app` | [[Open-App]] |
| `sys_info` | [[Sys-Info]] |
| `get_weather` | [[Weather]] |
| `get_calendar_events`, `add_calendar_event`, `delete_calendar_event` | [[Calendar]] |
| `get_reminders`, `add_reminder` | [[Reminders]] |
| `browser_control` | [[Browser]] |
| `play_media` | [[Media]] |
| `shell_run` | [[Shell]] |
| `toggle_webcam` | [[Webcam]] |
| `analyze_screen` | [[Screen-Vision]] |
| `intervene_screen` | [[Ekran-Mudahale]] |
| `recognize_objects`, `learn_object` | [[Nesne-Tanima]] |
| `read_text` | [[OCR]] |
| `start_watch`, `stop_watch`, `start_daily_briefing`, `stop_daily_briefing`, `get_daily_activity` | [[Izleme-ve-Brifing]] |
| `search_files`, `summarize_file` | [[Dosya]] |
| `get_notifications`, `control_power` | [[Bildirimler-ve-Guc]] |
| `gemini_desktop_task` | [[Gemini-Masaustu]] |
| `get_youtube_channel_report` | [[Youtube-Stats]] |
| `send_whatsapp_message`, `save_whatsapp_contact` | [[WhatsApp]] |
| `analyze_video` | [[Video-Analizi]] |
| `save_memory`, `delete_memory` | [[Bellek-ve-Config]] |

Araçların arayüzde nasıl göründüğü (Vision paneli, zaman çizelgesi) için [[Arayuz]].

## İki adımlı onay isteyen araçlar

Yıkıcı ya da geri alınamaz eylemler önce `confirm=false` ile çağrılır (hiçbir şey yapmaz,
sadece ne yapılacağını anlatır), kullanıcı sözlü onay verirse aynı parametrelerle
`confirm=true` ile tekrarlanır. Kural `core/prompt.txt` içinde:

- `intervene_screen` — [[Ekran-Mudahale]]
- `control_power` — [[Bildirimler-ve-Guc]]
- `delete_memory` — [[Bellek-ve-Config]]
- `gemini_desktop_task` — [[Gemini-Masaustu]]
