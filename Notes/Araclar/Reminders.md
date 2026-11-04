---
tags: [chiron, arac]
---

# Reminders — actions/reminders.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Calendar]]

[[Calendar]] ile aynı desen: Apple Reminders yalnızca macOS'ta çalıştığından, Windows'ta
`get_reminders()` ve `add_reminder()` sadece `to-do.microsoft.com/tasks` tarayıcıda açar ve
kullanıcıyı bilgilendiren sabit metin döner. Gerçek okuma/ekleme otomasyonu yok.

Bugün içindeki kısa hatırlatmalar ("10 dakika sonra", "saat 15:30'da") artık [[Zamanlayici]]'da — PC'de sesle
kurulur, dolunca Chiron söyler.

Tool'lar: `get_reminders`, `add_reminder` ([[Arac-Tanimlari]]).
