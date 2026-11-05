# İstek Listesi

Telefondaki Chiron'un yapamadığı ve kullanıcının "listeye ekle" dediği istekler.
Durum değerleri: `yeni` → `bakıldı` → `yapıldı` / `yapılmayacak`. Durumu elle değiştirebilirsin;
`yapıldı` olanı telefon bir sonraki konuşmada kullanıcıya haber verir.

## İstekler

### İ-001 · Ana ekrana dönme
**Durum:** yapıldı · **Sayı:** 1 · **Bildirildi:** evet
- 2026-09-17 01:24 · "Ana ekrana dön" · denenen: uygun araç yok · Xiaomi 22101316G, 0.1.0
<!-- ids: fd0421e1-3bb8-4671-8f71-c26464604a1c -->

### İ-002 · Gönderilen mesajları düzenleme
**Durum:** yapıldı · **Sayı:** 1 · **Bildirildi:** evet
- 2026-09-17 15:17 · "Mesaj gönderirken düzeltme/düzenleme yapma isteği" · denenen: send_message - mesaj düzenleme desteği yok · Xiaomi 22101316G, 0.1.0
<!-- ids: adfa8171-266a-4404-bf92-cee80af7c3d4 -->

### İ-003 · Medya oynatma/durdurma sorunu
**Durum:** bakıldı · **Sayı:** 1 · **Bildirildi:** hayır
- 2026-09-18 18:32 · "Medya oynat/durdur komutları çalışmıyor" · denenen: manage_device_audio media_play_pause — çalışmadı · Xiaomi 22101316G, 0.1.0
<!-- ids: c9645840-cbdb-4af1-b6aa-47acf0bfb6b2 -->

### İ-004 · İstek listesi görüntüleme
**Durum:** yapıldı · **Sayı:** 1 · **Bildirildi:** evet
- 2026-09-21 02:24 · "İstek listemde şu an ne var?" · denenen: uygun araç yok · Xiaomi 22101316G, 0.1.0
<!-- ids: 02f2d72e-1bf5-44e7-a529-8ca0bdf4dbc4 -->

### İ-005 · İstek listesinden silme özelliği
**Durum:** yapıldı · **Sayı:** 1 · **Bildirildi:** evet
- 2026-09-21 03:00 · "Silme özelliğini ekle" · denenen: uygun araç yok · Xiaomi 22101316G, 0.1.0
  - Ayrıntı: Kullanıcı mevcut istek listesindeki öğeleri silmek istedi ancak bunun için bir araç bulunmuyor. İdeal davranış, kullanıcının isteklerini kolayca yönetebilmesi, silme veya düzenleme yapabilmesi olmalı.
<!-- ids: c33e1d5b-6e6c-4fd8-a2c0-e210ac6e6c57 -->

### İ-006 · Güncel gündem bilgilerine erişim
**Durum:** yapıldı · **Sayı:** 1 · **Bildirildi:** evet
- 2026-10-01 14:21 · "Bugün gündem ne?" · denenen: uygun araç yok · Xiaomi 22101316G, 0.1.0
  - Ayrıntı: Kullanıcı güncel gündem bilgilerini öğrenmek istedi ancak mevcut araçlarla buna erişilemedi. İdeal davranış, kullanıcının gün içindeki önemli haberleri ve gelişmeleri sesli olarak özetleyebilmektir.
<!-- ids: f44ce607-50ab-4147-b257-cc55d7da623f -->

### İ-007 · Hata bildirimi yapma özelliği
**Durum:** yapıldı · **Sayı:** 1 · **Bildirildi:** evet
- 2026-10-02 22:25 · "Hata bildirimi yap" · denenen: uygun araç yok · Xiaomi 22101316G, 0.1.0
  - Ayrıntı: Kullanıcı, sistemde karşılaştığı hataları bildirmek için bir özellik talep ediyor. Mevcut araçlar arasında doğrudan hata bildirimi yapmaya uygun bir fonksiyon bulunmamaktadır. Kullanıcının herhangi bir durumda kolayca hata kaydı oluşturabilmesi hedeflenmektedir.
<!-- ids: 5d0ca5b6-c724-401f-994f-ca659a445774 -->

### İ-008 · Müzik çalarken ses sorununda bağlantı kesme
**Durum:** yapıldı · **Sayı:** 1 · **Bildirildi:** evet
- 2026-10-02 22:37 · "Müziği başlattığı zaman ses gelmiyor, bağlantıyı kesmek istiyorum." · denenen: manage_device_audio media_play_pause - ses gelmedi, bağlantı kesme aracı yok · Xiaomi 22101316G, 0.1.0
  - Ayrıntı: Kullanıcı müzik oynatma komutu verdi (manage_device_audio action=media_play_pause), ancak ses gelmediğini belirtti. Ses sorunu karşısında bağlantının kesilmesini istedi. Mevcut araçlarda bağlantıyı kesmeye yönelik bir fonksiyon bulunmamaktadır. İdeal durumda, ses gelmediği algılandığında veya kullanıcı talep ettiğinde bağlantının kesilebilmesi beklenir.
<!-- ids: 389a6503-7efb-4c3a-a575-d4a78c9ac3c2 -->

### İ-009 · PC durumunu görüntüleme
**Durum:** yapıldı · **Sayı:** 1 · **Bildirildi:** evet
- 2026-10-03 04:55 · "pcde şuan ne yapılıyor" · denenen: query_desktop_chiron question='PC'de şuan ne yapılıyor' - success=false · Xiaomi 22101316G, 0.1.0
  - Ayrıntı: Kullanıcı mevcut PC durumunu (açık uygulamalar, sistem durumu gibi) öğrenmek istedi ancak query_desktop_chiron aracı success=false döndü. Aracın başarılı olup kullanıcının isteğini yerine getirmesi beklenir.
<!-- ids: aa8d8c13-c58f-476c-b1ad-733e6094662c -->

### İ-010 · Terminalde yeni sekme açma ve Claude'a bağlanma
**Durum:** bakıldı · **Sayı:** 1 · **Bildirildi:** hayır
- 2026-10-20 03:48 · "terminalde yeni secme aç ve clauda bağlan" · denenen: uygun araç yok · Xiaomi 22101316G, 0.1.0
  - Ayrıntı: Kullanıcı Windows Terminal uygulamasında yeni bir sekme açmak ve bu sekme üzerinden Claude'a bağlanmak istiyor. Mevcut araç setinde Terminal içinde sekme açma veya Claude entegrasyonu sağlama işlevi bulunmamaktadır. İdeal olarak, komut doğrudan PC'de yürütülmelidir.
  - 2026-10-30 · PC'deki sesli Chiron'a `open_terminal` eklendi ([[Terminal]]). Telefondan doğrudan açmak için mobil uygulamaya ve `desktop_control` beyaz listesine eylem eklenmesi gerekiyor — o yüzden `yapıldı` değil.
<!-- ids: 6870dc01-f4eb-47da-b34c-2bf12e6cb247 -->

### İ-011 · Del uygulamasında detaylı hesap kısmı
**Durum:** yeni · **Sayı:** 1 · **Bildirildi:** hayır
- 2026-10-29 13:07 · "Del uygulamasında hesap kısmını daha detaylı yap" · denenen: delegate_to_claude — onaylanamadi · Xiaomi 22101316G, 0.1.0
  - Ayrıntı: Kullanıcı 'Del uygulamasında hesap kısmını daha detaylı yap' talebini iletti. delegate_to_claude aracıyla başlatma ve onaylama aşamaları teknik bir hata (uyumsuzluk) nedeniyle tekrar tekrar başarısız oldu. Kullanıcı bu özelliği kullanmak istediği için istek listesine eklenmesi talep edildi. İdeal durumda onay mekanizmasının sorunsuz çalışması beklenir.
<!-- ids: 0a1f6c61-38f8-4560-819b-1fa674f3c16f -->

### İ-012 · SIM kart şifresi kaldırma ayarı bulma
**Durum:** bakıldı · **Sayı:** 1 · **Bildirildi:** hayır
- 2026-11-03 17:43 · "telefonda sim kart şifresini kaldırma ayarını bulmak" · denenen: uygun araç yok · Xiaomi 22101316G, 0.1.0
  - Ayrıntı: Kullanıcı, telefon ayarlarında SIM kart şifresini kaldırmaya yönelik ayarı bulmamı istedi ancak mevcut araçlar bu işlemi doğrudan desteklemiyor. İdeal olarak, ilgili ayar menüsüne yönlendirme veya doğrudan işlemi gerçekleştirme yeteneği olmalı.
  - 2026-11-05 · chiron-mobile'a `phone_control` eklendi ([[Chiron-Mobil]] § Telefonu sesle kullanma): ayar sayfası açma (sim_lock dahil), ekran okuma, dokunma, kaydırma, yazma. Erişilebilirlik izni açılıp telefonda denenince `yapıldı`.
<!-- ids: 3e63653a-6cbf-46e1-9a31-6458df84fe13 -->

