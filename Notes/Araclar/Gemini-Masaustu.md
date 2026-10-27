---
tags: [chiron, arac]
---

# Gemini Masaüstü Otomasyonu — actions/gemini_automation.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Browser]] · [[Ekran-Mudahale]] · [[Bilinen-Tuzaklar]]

Masaüstündeki Chrome simgesinden başlayıp belirtilen profille açar, yeni sekmede
Google Gemini web sitesine gidip bir prompt gönderir.

Neden ayrı bir araç: [[Browser]] yalnızca URL açıyor, sayfa içi etkileşim
yapmıyor. Bu araç ise gerçek bir UI otomasyonu — profil seçimi, sekme açma,
prompt yazma ve gönderme adımlarını sırayla yürütüyor.

`repeat_count` / `repeat_text` ile aynı isteği (varsayılan `next`) tekrar
gönderebiliyor; her turda oluşan görseli indiriyor.

`confirm` parametresi var — [[Ekran-Mudahale]] ve [[Bildirimler-ve-Guc]] ile aynı
iki adımlı onay deseni.

`Docs/YAPILACAKLAR.md` listesinin dışında, kullanıcının ayrıca istediği bir
özellik.

Tool: `gemini_desktop_task` ([[Arac-Tanimlari]]).

## Neden API değil de tarayıcı

2026-08-07'de API'ye taşıma değerlendirildi ve **reddedildi**. Kullanıcının
anahtarıyla ölçüldü: görsel üretim modellerinin üçünde de ücretsiz katman
`limit: 0` döndü (`gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image`,
`gemini-3-pro-image`); `imagen-4.0-*` artık 404. Yani API'den görsel üretmek
faturalandırma açmayı gerektiriyor.

Gemini Pro aboneliği **web arayüzünü** kapsıyor, API'yi değil. Tarayıcı yolu
bu yüzden tek ücretsiz yol — bedeli, iş sürerken fare/klavyenin meşgul olması.
Bu bedel kaldırılamaz: fiziksel imleç gerektiren bir işi arka plana almak
mümkün değil (planlanan ajan sistemi de bunu çözemez).

## Güvenilirlik mekanizmaları (2026-08-07)

**Üretim bitişi — sabit bekleme yok.** Eskiden her tur sabit 18 sn bekleniyordu;
yavaş üretimde erken davranıp önceki görseli tekrar indirme, hızlı üretimde
boşuna bekleme riski vardı. Artık `_wait_until_settled()` ekranın durmasını
bekliyor: ardışık ekran görüntülerinin 64x64 gri parmak izleri karşılaştırılıyor,
tamamen yerel — **tek bir Gemini çağrısı harcamıyor**. Karar göreli veriliyor
(mutlak eşiğin neden çürüdüğü: [[Bilinen-Tuzaklar]] § "Ekran durdu mu").

**İndirme doğrulaması — yer gerçeği dosya sistemi.** `_download_latest_image`
artık başarıyı tıklamadan değil, İndirilenler klasörüne yeni ve yazılması
bitmiş bir dosya düşmesinden anlıyor (`_wait_for_new_download`). Klasörün
gerçek konumu kayıt defterinden okunuyor. Rapor edilen sayı artık gerçekten
inen dosya sayısı; hepsi inmediyse araç bunu açıkça söylüyor.

**Kota — tur başına iki vision çağrısı yerine bir.** Sohbet giriş kutusunun
koordinatı ilk prompt adımından biliniyor ve turlar arasında yer değiştirmiyor,
bu yüzden her tekrarda yeniden aranmıyor (`_type_at_verified`). Doğrulama adımı
kaldırılmadı — yalnızca arama adımı atlandı. 20 görsellik bir işte bu, onlarca
görü çağrısı demek; [[Izleme-ve-Brifing]] notundaki "kotayı yakan şey araçlar
değil" dersinin aynısı burada da geçerli.

**Canlı testle doğrulanması gerekenler:** yardımcı fonksiyonlar API'siz test
edildi (indirme bekleme, parmak izi, durma tespiti), ama uçtan uca akış gerçek
Chrome + gerçek Gemini oturumu gerektiriyor ve otomatik test edilemez.
`SETTLE_DROP_RATIO` / `GENERATION_MAX_WAIT_SECONDS` gerçek sayfada
ayarlanabilir.
