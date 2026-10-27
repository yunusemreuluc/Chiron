---
tags: [chiron, arac]
---

# Ekran Müdahale — actions/screen_control.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Screen-Vision]] · [[Izleme-ve-Brifing]]

Ekranda bir öğeyi bulup **gerçekten** tıklar / yazar. [[Screen-Vision]] yalnızca
bakıp anlatır; bu araç eyleme geçer.

Akış: ekran görüntüsü alınır → Gemini vision ile tarif edilen öge bulunur →
fare/klavye ile eylem uygulanır → eylem sonrası doğrulama (self-correction).

## İki adımlı onay — zorunlu

`confirm=false` ile çağrıldığında **hiçbir şey yapmaz**, sadece hedefi bulup
sözlü olarak açıklar. Kullanıcı onaylarsa AYNI `instruction` (ve varsa
`app_hint`) ile `confirm=true` olarak tekrar çağrılır. Onay alınmadan
`confirm=true` kullanılmaz.

Aynı iki adımlı onay deseni `control_power` ([[Bildirimler-ve-Guc]]) ve
`delete_memory` ([[Bellek-ve-Config]]) araçlarında da var; kural
`core/prompt.txt` içinde tanımlı.

## Bilinen sınır

Sekme değiştiremez, yalnızca pencere odaklayabilir (`app_hint` ile). Hedef
pencere açık ama arka planda farklı bir sekmedeyse öge bulunamayabilir.

## Durum

Gerçek ortamda test edildi (Not Defteri, Gemini sekmesi) ve kullanıcı onayıyla
2026-07-31'de `Docs/YAPILACAKLAR.md` listesinden çıkarıldı.

Tool: `intervene_screen` ([[Arac-Tanimlari]]).
