---
tags: [chiron, arac]
---

# Zamanlayıcı — actions/zamanlayici.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Reminders]] · [[Gelisim-Gunlugu]]

Sesle kurulan zamanlayıcı ve kısa hatırlatıcı (2026-11-04, K-014). Tek araç: `set_timer`.

- **Kur:** `action=set` + `minutes`/`seconds` ("10 dakika sonra çayı hatırlat" → minutes=10, label=çay) ya da
  `at="15:30"` (saat geçtiyse yarın o saat). En fazla 24 saat; ilerisi için [[Reminders]]/takvim.
- **Sor:** `action=list` → her zamanlayıcının adı, kalan süresi ve saati.
- **İptal:** `action=cancel, label=...` (büyük/küçük harf duyarsız, parça eşleşmesi; `hepsi` hepsini siler).
  Birden çok zamanlayıcı varken ad verilmezse hiçbirini silmez, hangisi diye sorar.
- **Haber:** main.py `_watch_timers` saniyede bir `pop_due()`'ya bakar, dolanı proaktif sistem mesajı olarak
  Chiron'a söyletir (araştırma panosu ve PC işi haberiyle aynı yol). Chiron konuşurken/duraklatılmışken dolan
  zamanlayıcı kaybolmaz, sonraki uygun anda söylenir; bir dakikadan çok gecikmişse gecikme de söylenir.
  Uzak moddaysa haber telefona yazı olarak düşer.

Desen Alexa'nın adlı zamanlayıcıları: dolunca adı söylenir, sorma/iptal ada göre.

**Sınır:** zamanlayıcılar bellekte — Chiron kapanırsa gider (bilinçli; kalıcı hatırlatma ayrı iş).
`-lık/-lik` eki ünlü uyumuyla üretiliyor; "saat" alıntı kelime olduğu için istisna (`saatlik`).

Testler: `tests/test_zamanlayici.py`.
