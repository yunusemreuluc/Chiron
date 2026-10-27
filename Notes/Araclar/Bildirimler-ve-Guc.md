---
tags: [chiron, arac]
---

# Bildirimler ve Güç Kontrolü — actions/notifications.py · actions/power_control.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Sys-Info]] · [[Ekran-Mudahale]]

## get_notifications(limit)

Windows Bildirim Merkezi'nde o an duran (okunmamış) sistem bildirimlerini okur —
hangi uygulamadan geldiğini ve içeriğini listeler.

`winsdk` üzerinden WinRT projeksiyonuyla çalışıyor (bkz. `requirements.txt`) —
yani ekran okuma değil, gerçek sistem API'si.

## control_power(action, delay_minutes, confirm)

Bilgisayarı kapatır / yeniden başlatır / uyku moduna alır / hazırda bekletir,
istenirse gecikmeli.

**ÇOK YIKICI** — kaydedilmemiş iş kaybolabilir. Bu yüzden [[Ekran-Mudahale]] ile
aynı iki adımlı onay: önce `confirm=false` (sadece ne yapılacağını açıklar,
hiçbir şey yapmaz), kullanıcı sözlü onay verirse aynı parametrelerle
`confirm=true`.

`action='cancel'` her zaman güvenli, onay gerekmez — bekleyen bir güç işlemini
iptal eder (`ChironLive._pending_power_task`).

2026-07-27'de eklendi, `Docs/YAPILACAKLAR.md` listesinin dışında ek bir özellik.

Tool: `get_notifications`, `control_power` ([[Arac-Tanimlari]]).
