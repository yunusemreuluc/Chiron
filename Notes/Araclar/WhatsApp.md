---
tags: [chiron, arac]
---

# WhatsApp — actions/whatsapp.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Bellek-ve-Config]]

## Kişi bulma
İki kaynaktan birleştirilir (`_contact_candidates`): `memory.json → whatsapp_contacts`
([[Bellek-ve-Config]], `save_whatsapp_contact` tool'uyla eklenir) ve
`memory/phone_book.json` (vCard içe aktarmayla dolar). `_find_contact()` normalize edilmiş
isim/alias üzerinde skorlu eşleşme yapar (`_match_score`: tam eşleşme 300, prefix 220,
içerir 160, çoklu kelime eşleşmesi 120).

## Mesaj gönderme — send_whatsapp_message(message, phone_number, recipient_name, send_now, app_target)
- `app_target="desktop"` (varsayılan denemede önce) → `whatsapp://send?phone=...` URI şeması,
  `send_now=true` ise `_type_and_send()` ile pencere öne getirilip pano üzerinden yapıştır+Enter
  (pyautogui gerekli)
- `app_target="web"` → `web.whatsapp.com/send?phone=...&text=...`, `send_now=true` ise bekleyip
  Enter'a basar
- Telefon numarası E.164'e normalize edilir (`_normalize_phone`: TR başında 0 varsa 90 ile
  değiştirir, 10 haneliyse başına 90 eklenir)

### Foreground/odak sorunu (2026-07-21'de düzeltildi)
Eskiden `_type_and_send` sabit `DESKTOP_LOAD_DELAY` (4.5sn) kadar uyuyup `pygetwindow`'un
`.activate()` metoduyla pencereyi öne getirmeye çalışıyordu. İki sorun vardı:
1. WhatsApp Desktop (UWP paket, `5319275A.WhatsAppDesktop`) soğuk başlangıçta gerçek
   foreground'a geçmesi ölçümde ~5sn sürüyor — 4.5sn'lik sabit bekleme çoğu zaman yetmiyor,
   Ctrl+V/Enter WhatsApp yüklenmeden önce o an odaktaki başka pencereye gidiyordu (mesaj hiç
   yazılmıyordu — kullanıcı "bağlanmıyor/mesaj göndermiyor" diye bildirdi).
2. `pygetwindow.activate()` Windows'ta bilinen bir hata yüzünden başarılı olsa bile exception
   fırlatıyor (sessizce yutuluyordu) ve arka plan sürecinden `SetForegroundWindow` zaten Windows'un
   foreground kilidi yüzünden genelde işe yaramıyor — yani "yedek" odaklama fiilen hiç çalışmıyordu.

Düzeltme: `_wait_for_whatsapp_window()` sabit sleep yerine pencere gerçekten aktif olana kadar
poll eder (max `DESKTOP_LOAD_DELAY`, artık 10sn), `_force_foreground()` ise ctypes ile
`AttachThreadInput` tekniğini kullanarak foreground kilidini güvenilir şekilde atlatır (yeni
bağımlılık yok — sadece stdlib `ctypes`). `_focus_whatsapp_window(timeout)` artık başarılı/
başarısız (bool) döner; başarısızsa `_type_and_send` panoya hiç yapıştırma yapmadan net bir
hata mesajıyla döner (yanlış pencereye sessizce yazmak yerine).

## Kayıtlı numarası olmayan kişi — uygulama içi arama (2026-07-21)
`_find_contact` eşleşme bulamazsa (whatsapp_contacts + phone_book boşsa/isim yoksa) artık
direkt hata dönmüyor: `_open_chat_via_search()` WhatsApp Desktop'ı hedefsiz açar, `Ctrl+F` ile
uygulamanın kendi sohbet arama kutusunu kullanır, ismi yazar, `Down+Enter` ile ilk sonucu açar,
sonra mesajı yazıp (send_now'a göre) gönderir. Sadece `app_target` desktop/auto iken ve
`pyautogui` kuruluyken çalışır (web hedefinde bu akış yok).

Numaralı deep-link kadar güvenilir değildir — WhatsApp'ın arama sonuçlarının ilk sırasına
güvenir, bu yüzden aynı isimden birden fazla sohbet/kişi varsa yanlışına gidebilir. Kalıcı ve
güvenilir sonuç için asıl önerilen yol hâlâ `save_whatsapp_contact` ile numarayı kaydetmek —
bu arama sadece "hiç kayıt yokken de bir şekilde çalışsın" isteği için eklenen best-effort yedek.

## save_whatsapp_contact(display_name, phone_number, aliases)
`memory.json`'a `whatsapp_contacts/<key>` olarak kaydeder.

## vCard içe aktarma — KALDIRILDI (2026-08-21)
`import_phone_book_from_vcf` + `_unfold_vcf_lines` + `_save_phone_book` (98 satır) ve
`memory/phone_book.example.json` silindi. Hiçbir yerden çağrılmıyordu: tool tanımı yoktu,
UI'ye bağlı değildi, macOS sürümünden kalmaydı.

`memory/phone_book.json` **okunmaya devam ediyor** — `_load_phone_book()` duruyor ve
`_contact_candidates()` hâlâ `whatsapp_contacts` yanında `phone_book` kaynağını da tarıyor.
Değişen tek şey: dosyayı artık kod yazmıyor. Elle `{"kisi": {"phone": "+90..."}}` biçiminde
doldurulursa aynen çalışır. Parse'ı geri isteyen olursa `git log -S import_phone_book_from_vcf`.

Tool'lar: `send_whatsapp_message`, `save_whatsapp_contact` ([[Arac-Tanimlari]]).
