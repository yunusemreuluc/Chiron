---
tags: [chiron, arac]
---

# İzleme, Brifing ve Aktivite — screen_watch.py · screen_monitor.py · activity_log.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Screen-Vision]] · [[Ekran-Mudahale]] · [[Arayuz]]

Chiron'un **proaktif** tarafı: kullanıcı sormadan kendiliğinden konuşan
mekanizmalar. Hepsi `main.py` içinde `asyncio.TaskGroup` ile paralel arka plan
görevi olarak dönüyor.

## Ortak ön koşul

`_proactive_checks_allowed()` — duraklatılmışken, susturulmuşken, Chiron zaten
konuşurken veya canlı oturum hazır değilken **hiçbir bekçi çalışmaz**. Bazıları
ayrıca kamera açıkken de susuyor (`block_on_webcam`).

## Kullanıcının kurduğu izlemeler (start_watch / stop_watch)

`start_watch(instruction, condition, timeout_minutes)` hemen döner; gerçek
kontrol `_watch_custom_conditions` arka plan görevinde ~20 sn'de bir yapılır.
Koşul gerçekleşince (veya süre dolunca) izleme kendiliğinden kalkar ve Chiron
sesli haber verir.

[[Ekran-Mudahale]]'nin aksine **onay gerekmez** — bu araç yalnızca izler ve
bildirir, tıklamaz/yazmaz.

Aktif izlemeler `ChironLive._active_watches` listesinde, yani **ses döngüsünün
belleğinde** yaşıyor; diskte karşılığı yok. Arayüzdeki Otomasyon paneli bu
yüzden dosyadan değil, `backend/core/commands.read_provider("automation")`
üzerinden okuyor ([[Arayuz]]).

`stop_watch(instruction)` — `instruction` boş bırakılırsa TÜM izlemeleri durdurur.

## Otomatik bekçiler (araç değil, arka plan)

- `_watch_screen_for_issues` — periyodik olarak ekranı kontrol eder
  (`actions/screen_monitor.py`), sorun görürse haber verir ve politikaya göre
  kendisi düzeltir ([[Otonom-Duzeltme]]). **Chiron'un en pahalı arka plan işi** —
  aşağıdaki kota bütçesine bak.
- `_watch_system_health` — pil/disk/CPU/RAM eşikleri
  (`actions/sys_info.check_health_thresholds`)

## Kota bütçesi (2026-08-01)

Ekran bekçisi 25 sn'de bir Gemini görü çağrısı atıyordu: **saatte 144, günde
3456**. Gemini ücretsiz katmanı **günde 1500** veriyor — yani Chiron ~10 saat
açık kalınca kota, kullanıcı hiçbir şey yapmadan biterdi
([[Bilinen-Tuzaklar]] § Kotayı yakan şey araçlar değil).

Üç katman eklendi (`main.py` → `SCREEN_WATCH_*` sabitleri):

| Katman | Ne yapar | Nerede |
|---|---|---|
| **Boşta** | Kullanıcı 120 sn'dir klavyeye dokunmadıysa hiç bakma | `main.py` |
| **Değişim** | Ekran öncekiyle aynıysa Gemini'ye sorma | `screen_monitor.screen_difference` |
| **Tavan** | Saatte en fazla 20 gerçek çağrı | `main.py` |

Aralık **25 → 90 sn**. Sıralama önemli: ucuz kontrol önce, ekran yakalama
(yerel, ~30 ms) ortada, pahalı görü çağrısı en sonda.

**Tavan neden şart:** değişim kapısının işe yarayacağı varsayılamaz. Ekranda
video oynarken ardışık farklar ölçüldü ve hepsi eşiği aşıyordu — kapı hiç
kapanmıyor. Tavan, kapı hiç çalışmasa bile kotayı garantiliyor.

**"Atlandı" sayılmaz:** `check_for_issue` Gemini'ye gitmediğinde
`skipped="unchanged"` döner ve bu çağrı tavana **işlenmez**. Aksi hâlde tavan
tasarrufun kendisini cezalandırırdı.

**Duraklatma sonrası referans unutulur** (`reset_change_tracking`): o aralıkta
ekran değişmiş olabilir ama bakılmadı, dolayısıyla elde tutulan karşılaştırma
noktası bayat.

### Ölçülen sonuç (simülasyon, gerçek sabitlerle)

| Senaryo | Eski | Yeni |
|---|---|---|
| 10 saat, ders/okuma (durgun ekran) | 1440 | **52** |
| 10 saat, sürekli video | 1440 | 200 |
| 24 saat, en kötü hâl | 3456 | **477** |

En kötü durumda bile ücretsiz kotanın **%32'si**; geriye günde 1023 istek
gerçekten kullandığın araçlara kalıyor. Tipik günde tüketim **%3**.

## Günlük brifing

`start_daily_briefing(time_str)` — her gün belirtilen saatte (`SS:DD`, 24 saat)
kendiliğinden bir "günaydın" brifingi. **Şu an sadece hava durumu** —
takvim/hatırlatıcı/haberlere gerçek erişim yok (bkz. `Docs/YAPILACAKLAR.md` #5,
Google Calendar / Microsoft Graph OAuth entegrasyonu bekliyor).

Ayar `memory.json`'daki `scheduled_briefing` altında kalıcı ([[Bellek-ve-Config]]);
`PROTECTED_CATEGORIES` içinde olduğu için hafıza sıkıştırmasında arşivlenmiyor.

## Aktivite günlüğü

`get_daily_activity(date)` — o gün nelerin konuşulduğunu ve hangi araçların
çalıştırıldığını kronolojik döner (`memory/activity_log.py`). Ham liste sesli
okunmaz, özetlenip anlatılır.

Tool: `start_watch`, `stop_watch`, `start_daily_briefing`, `stop_daily_briefing`,
`get_daily_activity` ([[Arac-Tanimlari]]).
