---
tags: [chiron, arac]
---

# Weather — actions/weather.py + actions/location.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Mimari]] · [[Arayuz]] · [[Bilinen-Tuzaklar]]

## Konum önceliği (2026-07-31'de gerçek tespit eklendi)

1. Çağrıda verilen `location` — kullanıcı açıkça bir şehir söylediyse
   ("Ankara'da hava nasıl") o kazanır
2. `CHIRON_WEATHER_LOCATION` env değişkeni — elle konulmuş kalıcı geçersiz kılma
3. **Gerçek konum** (`actions/location.py`)
4. `DEFAULT_LOCATION` (`"Konya"`) — yalnızca yukarıdakilerin hepsi başarısızsa

3. adımdan önce sabit bir şehre bakılıyordu. Tesadüfen doğruydu ama kullanıcı
taşınsa ya da seyahate çıksa **sessizce yanlış** cevap verirdi.

> Bu not 2026-07-31'e kadar varsayılanın "Istanbul" olduğunu söylüyordu; kodda
> "Konya" yazıyordu. Not bayatlamıştı.

## actions/location.py — iki kaynak, sırayla

**1. Windows Konum Servisi** (`winsdk`, zaten bildirimler için kurulu). WiFi/GPS
tabanlı; bu makinede ölçülen doğruluk **~111-126 m**. Kullanıcı Windows
ayarlarından konum iznini kapattıysa kullanılamaz.

WinRT asenkron, araç ise senkron — çağrı **kendi thread'inde kendi olay
döngüsüyle** çalışıyor. Doğrudan `asyncio.run()` çağrılsaydı, araç zaten bir
asyncio döngüsünün içinden çalıştırıldığında "event loop is already running"
hatası verirdi.

**2. IP tabanlı** (ip-api.com) — izin gerektirmez, şehir adını da getirir. VPN
ya da operatör yönlendirmesi yüzünden yanlış şehir verebilir.

İkisi de başarısız olursa `None` döner; modül **asla exception fırlatmaz**.

Konum 15 dakika önbellekleniyor — her hava durumu sorgusunda cihazı yeniden
yormanın anlamı yok. `detect_location(force=True)` önbelleği atlar.

## Koordinat mı, şehir adı mı

Servise **koordinat** gönderiliyor: "Konya" birden fazla yere işaret edebilir,
koordinat tektir. Ama kullanıcıya "37.88,32.49 için hava durumu" demek anlamsız
olurdu — okunur ad `wttr.in` cevabındaki `nearest_area`dan alınıyor.

**Tuzak:** `wttr.in/{lat},{lon}?format=%l` denendi ve **işe yaramıyor** —
koordinatı olduğu gibi geri yankılıyor, ad çözmüyor. Ad yalnızca `j1` cevabının
içinde geliyor.

## Tek uç

`get_weather_summary(location=None)` → `wttr.in/{konum}?format=j1`. Anlık
durum: sıcaklık, tanım, hissedilen, nem.

**Kaldırıldı (2026-08-21):** `get_weather_forecast` + WMO kod tablosu
(`_WMO_CODES`, `_wmo_lookup`, `_TR_WEEKDAYS`) — 137 satır, dosyanın yarısından
fazlası. Open-Meteo'ya çok günlük tahmin için geçilmişti ve docstring'i "ana
UI'daki hava durumu panelinin gün-gün gezinme özelliği için kullanılıyor"
diyordu; öyle bir panel **hiç olmadı**. Kod tablosunun yorumu da Tkinter'ın
emoji render sorununu anlatıyordu — yani blok, 2026-07-29'da silinen Tkinter
arayüzünden kalmaydı. Tahmin gerekirse Open-Meteo çağrısı git geçmişinde
(`git log -S get_weather_forecast`). Bu, [[Bilinen-Tuzaklar]] § arayüzde
dürüstlük kuralının kod tarafındaki karşılığı: **docstring'in "kullanılıyor"
demesi kullanıldığı anlamına gelmiyor**, çağıran aranmalı.

## Gizlilik

Konum yalnızca bellekte tutuluyor, hiçbir dosyaya yazılmıyor. Dışarı giden tek
istek hava durumu sorgusunun kendisi.

Tool: `get_weather` ([[Arac-Tanimlari]]). `main.py._focus_ui_section_for_tool`
bu araç çağrılınca arayüzde "weather" panelini odaklar — [[Arayuz]].
