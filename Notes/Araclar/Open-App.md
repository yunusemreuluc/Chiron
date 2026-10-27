---
tags: [chiron, arac]
---

# Open-App — actions/open_app.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Mimari]]

`open_app(app_name)` — Windows'ta uygulama açar. Sırasıyla dener:
1. `APP_ALIASES` sözlüğünde Türkçe/İngilizce takma ad eşleşmesi (örn. "dosya gezgini" → "explorer")
2. `URI_SCHEMES` içindeyse (`ms-settings:`, `outlookcal:` vb.) `os.startfile`
3. `shutil.which()` ile PATH'te bulunan exe → `subprocess.Popen`
4. `start "" "..."` shell komutu
5. Son çare `os.startfile`

Tool: `open_app` ([[Arac-Tanimlari]]). Çağıran: `main.py._execute_tool` → `run_in_executor`
(bloklamasın diye thread pool'da çalışır).

## UWP/Store uygulamaları — normal .exe akışı işe yaramaz
Microsoft Store (UWP paket) olarak kurulu uygulamalar (`WhatsApp` gibi) PATH'te yer almaz ve
`start "" "AdSoyad"` shell komutuyla bulunamaz — bulunamayınca `start` ~10sn boyunca donup
zaman aşımına uğrar, sonra `os.startfile(ad)` da `FileNotFoundError` verir (2026-07-21'de
WhatsApp özelinde bu şekilde tespit edildi: kullanıcı "WhatsApp'ı aç" dedğinde 10sn donma +
"bulunamadı" hatası). Çözüm: UWP uygulamalar için 2 numaralı adımdaki `URI_SCHEMES` yoluna
(`os.startfile` doğrudan) yönlendirmek — `APP_ALIASES["whatsapp"] = "whatsapp://"` ve
`URI_SCHEMES` içine `"whatsapp://"` eklendi, böylece `shutil.which`/`start` denemesine hiç
girmeden protokol şemasıyla anında açılıyor ([[WhatsApp]]'ın mesaj gönderme akışında da aynı
`whatsapp://` şeması kullanılıyor). Başka bir Store uygulaması eklenirken aynı belirti
görülürse aynı çözüm uygulanmalı (uygulamanın kendi URI şeması varsa `URI_SCHEMES`'e eklenir).
