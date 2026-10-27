---
tags: [chiron, arac]
---

# Calendar — actions/calendar.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Mimari]]

macOS sürümünde Apple Calendar/EventKit kullanılıyordu; Windows'ta gerçek bir takvim entegrasyonu
**yok** — üç fonksiyon da tarayıcıda Google Calendar açar ve kullanıcıyı bilgilendiren sabit bir
metin döner:
- `get_calendar_events(query, limit)` — sadece `calendar.google.com` açar, gerçek etkinlik okumaz
- `add_calendar_event(...)` — Google Calendar "quick add" URL'i (`render?action=TEMPLATE&...`)
  oluşturup tarayıcıda açar; kullanıcı formu kendisi tamamlar
- `delete_calendar_event(...)` — yine sadece takvimi açar, silme işlemini otomatikleştirmez

Tool'lar: `get_calendar_events`, `add_calendar_event`, `delete_calendar_event`
([[Arac-Tanimlari]]). Model, tarih ifadelerini gerçek ISO tarihe çevirmekle sorumlu
(`core/prompt.txt` kuralı) — bu modül tarih parse etmez.
