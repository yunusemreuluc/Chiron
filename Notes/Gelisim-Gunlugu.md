---
tags: [chiron, gelisim]
---

# Gelişim Günlüğü

Chiron'un kendini geliştirme döngüsünün (backend/core/dongu.py § Kendini geliştirme) kaydı. Her geliştirme
kartı en üste bir kayıt ekler: ne yaptı, neden daha iyi, ne öğrendi, kaynak. Sonraki kartlar bunu okuyup
tekrar etmez. Bağlı: [[Ajan-Ofisi]] · [[Istek-Listesi]]

## 2026-11-04 — "Chrome'a geç", "bunu sola yasla"
- **Ne yaptım:** PC'deki sesli Chiron'a `manage_window` aracı ([[Pencereler]], `actions/windows.py`): açık
  pencereleri listeler, öne getirir, küçültür, tam ekran yapar, eski boyutuna alır, kapatır, ekranın sol/sağ yarısına
  yaslar, masaüstünü gösterir. Ad verilmezse öndeki pencere; Chiron'un kendi penceresi hiç hedef olmaz.
- **Neden daha iyi:** Uygulama açabiliyordum ama açık pencereye dokunamıyordum; sesle çalışırken Yunus'un en sık
  fareye döndüğü an pencere değiştirmek ve yan yana dizmekti. Artık tek cümle, ve "yaptım" demem pencerenin durumunu
  geri okuduktan sonra — kapanmayan (kaydetmeyi soran) pencereye "kapattım" demiyorum.
- **Ne öğrendim:** Alt+Tab listesi resmi bir API değil; görünür + sahipsiz + tool window değil + DWM "cloaked" değil
  filtresiyle yaklaşılıyor, yoksa askıdaki mağaza uygulamaları ve kabuk pencereleri listeye düşüyor. Ad eşleşmesinde
  süreç adı başlıktan önce gelmeli ("chrome-notes.md - VS Code" Chrome isteğini çalmasın). 64 bit'te ctypes
  imzaları verilmezse pencere tanıtıcıları int'e kırpılır. Yarım ekran için `rcWork` kullanılmalı (görev çubuğu
  hariç, ikinci monitörde 0,0'dan başlamaz). Arka plan sürecinden öne getirme Windows kilidine takılabiliyor.
- **Kaynak:** https://devblogs.microsoft.com/oldnewthing/20071008-00/?p=24863 ·
  https://learn.microsoft.com/en-us/windows/win32/gdi/positioning-objects-on-a-multiple-display-setup

## 2026-11-04 — "10 dakika sonra çayı hatırlat"
- **Ne yaptım:** `set_timer` aracı ([[Zamanlayici]], `actions/zamanlayici.py`): sesle zamanlayıcı/kısa hatırlatıcı
  kurar (dakika/saniye ya da "saat 15:30"), kalan süreyi söyler, ada göre iptal eder; dolunca main.py
  `_watch_timers` Chiron'a sesle söyletir ("çay zamanı").
- **Neden daha iyi:** "Hatırlat" deyince `add_reminder` yalnız tarayıcıda To-Do açıyordu — zamanı gelince kimse
  haber vermiyordu. Şimdi çay, ocak, pomodoro, "toplantıya 10 dakika" tek cümle; Chiron konuşurken dolsa bile
  kaybolmaz, sırası gelince söylenir.
- **Ne öğrendim:** İyi sesli zamanlayıcının özü ad: dolunca adı söylemek, sorma/iptali ada göre yapmak (Alexa'nın
  adlı zamanlayıcıları). Birden çok zamanlayıcı varken ad verilmeden iptal istenirse tahmin etmek yerine sormak
  daha dürüst. Kodda: araştırma panosunun "liste + bekçi" haber yolu yeni proaktif özellikler için hazır kalıp;
  bekçi `_proactive_checks_allowed` kapalıyken listeden almadığı için haber kaybolmuyor. Türkçe `-lık/-lik` ekinde
  "saat" istisna. Zamanlayıcılar bellekte — kalıcı hatırlatma ve telefondan kurma sıradaki adaylar.
  `test_onay::test_hook_outputs...` hâlâ önceden kırık, dokunmadım.
- **Kaynak:** https://developer.amazon.com/docs/alexa-voice-service/enable-named-timers-and-reminders.html ·
  https://www.techhive.com/article/578364/how-to-make-the-most-of-your-alexa-timers.html

## 2026-11-04 — "Parlaklığı kıs", "ekranı yüzde kırk yap"
- **Ne yaptım:** PC'deki sesli Chiron'a `set_brightness` aracı ([[Parlaklik]], `actions/brightness.py`): dizüstü
  ekranının parlaklığını okur, yüzdeye ayarlar, 10'ar puan (ya da söylenen kadar) kısar/açar. Söylenen yüzde
  panelden geri okunan değer.
- **Neden daha iyi:** Sesi sesle ayarlayabiliyordum ama ekranı değil; gece ya da sunumda Yunus klavyeye uzanıyordu.
  Artık "parlaklığı kıs" tek cümle. Ekran tamamen kararmasın diye yüzde 5'in altına inmiyor ve bunu söylüyor.
- **Ne öğrendim:** Parlaklık için COM vtable'a gerek yok: WMI `WmiMonitorBrightnessMethods.WmiSetBrightness`
  yönetici izni istemeden çalışıyor (bu dizüstünde denendi). Panel değeri gecikmeli bildirebiliyor ve her yüzdeyi
  desteklemeyebiliyor — yazıp birkaç kez geri okumak gerek. Harici monitörde bu sınıf yok, DDC/CI (dxva2) gerekir.
  Önceki kaydın "telefondan PC'de Spotify'ı kıs" adayı mobil uygulamadaki eylem listesini (enum) değiştirmeyi
  istiyor — bu depodan yapılamıyor, chiron-mobile işi. `test_onay` hook testi hâlâ kırık (onay/bekçi alanı, dokunmadım).
- **Kaynak:** https://learn.microsoft.com/en-us/windows/win32/wmicoreprov/wmisetbrightness-method-in-class-wmimonitorbrightnessmethods ·
  https://devblogs.microsoft.com/scripting/use-powershell-to-report-and-set-monitor-brightness/

## 2026-11-04 — "Spotify'ı kıs, YouTube kalsın"
- **Ne yaptım:** `set_volume`'a `app` parametresi ([[Ses-Seviyesi]]): tek bir uygulamanın sesini okur, yüzdeye
  ayarlar, kısar/açar, sessize alır — Windows'un Ses Karıştırıcısı'ndaki uygulama kaydırıcısı. Önceki kaydın
  "sıradaki aday" dediği iş.
- **Neden daha iyi:** Müzik çalarken toplantıya ya da videoya geçince bütün PC'yi kısmak gerekiyordu. Artık
  "Spotify'ı kıs", "Discord'u sessize al" tek cümle; diğer sesler olduğu gibi kalıyor. Uygulama bulunamazsa
  tahmin edip yanlış şeyi kısmıyor, o an ses çıkaran uygulamaları sayıyor.
- **Ne öğrendim:** Uygulama sesleri aygıtın `IAudioSessionManager2` oturum listesinden geliyor; adı oturumda değil,
  `IAudioSessionControl2.GetProcessId` + süreç adından çıkıyor (görünen ad çoğu uygulamada boş). Tarayıcı birden
  çok oturum açar — hepsine aynı ayarı vermek gerek, yoksa "kıstım" denir ama bir sekme bağırır. Belgeler yöntemleri
  ALFABETİK listeliyor; vtable yuvası başlıktaki bildirim sırası — gerçek aygıtta geri okuyarak doğruladım.
  `test_onay::test_hook_outputs...` hâlâ kırık (önceden de), dokunmadım. Sıradaki aday: aynı aracı telefondan
  ("PC'de Spotify'ı kıs") `desktop_control` üzerinden açmak.
- **Kaynak:** https://learn.microsoft.com/en-us/windows/win32/api/audiopolicy/nn-audiopolicy-iaudiosessioncontrol2 ·
  https://learn.microsoft.com/en-us/windows/win32/api/audiopolicy/nn-audiopolicy-iaudiosessionmanager2

## 2026-11-04 — "Sesi kıs", "sesi yüzde otuz yap"
- **Ne yaptım:** PC'deki sesli Chiron'a `set_volume` aracı ([[Ses-Seviyesi]], `actions/volume.py`): varsayılan
  hoparlörün sesini okur, yüzdeye ayarlar, 10'ar puan (ya da söylenen kadar) kısar/açar, sessize alır/geri açar.
- **Neden daha iyi:** Müzik açabiliyordum ama sesini ayarlayamıyordum; "sesi kıs" boşa düşüyordu. Artık tek cümle,
  ve söylediğim yüzde aygıttan geri okunan gerçek değer — tahmin değil.
- **Ne öğrendim:** Yeni bağımlılık olmadan Windows ses API'si ham ctypes vtable çağrısıyla kullanılabiliyor
  (pycaw/comtypes gerekmez); yuva numaraları başlık dosyasındaki bildirim sırası. Medya ses tuşu yalnız 2 puanlık
  göreli adım veriyor ve sonucu okutmuyor. Sesi açarken sessizliği de kaldırmak gerek, yoksa yüzde değişir ama
  duyulmaz. Uygulama başına ses (yalnız Spotify'ı kıs) ayrı arayüz ister — sıradaki aday.
  Taban testte `test_onay::test_hook_outputs...` worktree'de zaten kırıktı (hook çıktısı boş JSON), dokunmadım.
- **Kaynak:** https://learn.microsoft.com/en-us/windows/win32/api/endpointvolume/nf-endpointvolume-iaudioendpointvolume-setmastervolumelevelscalar

## 2026-10-30 — "Terminalde yeni sekme aç ve Claude'a bağlan"
- **Ne yaptım:** PC'deki sesli Chiron'a `open_terminal` aracı (`actions/terminal.py`, [[Terminal]]): Windows
  Terminal'in son penceresinde, söylenen projenin klasöründe (`~/Projects` altı, ad/önek eşleşmesi) yeni sekme açar,
  içinde `claude` ya da "kaldığı yerden" denince `claude --continue` başlatır. İstek listesindeki İ-010.
- **Neden daha iyi:** Eskiden "terminal aç" eski `cmd` penceresini açıyordu, klasöre gitmek ve Claude'u başlatmak elle
  yapılıyordu. Şimdi "Dilcep'te Claude aç" tek cümle; yeni pencere değil, açık terminale sekme olarak eklenir.
- **Ne öğrendim:** `wt -w 0 new-tab -d <klasör>` son pencereye sekme ekler, pencere yoksa yenisini kurar; `;` wt'nin
  komut ayırıcısı, yolda geçerse komutu böler. npm'in `claude`'u `.cmd` kabuğu, wt onu doğrudan başlatamaz —
  `cmd /k claude` gerekiyor (`/k` Claude kapanınca sekmeyi açık tutar). Belirsiz proje adında (iki eşleşme) tahmin
  etmek yerine reddedip proje listesini döndürmek daha dürüst. Telefondan açmak mobil uygulamada iş istiyor (sırada).
- **Kaynak:** https://learn.microsoft.com/en-us/windows/terminal/command-line-arguments

## 2026-10-30 — "İş ne durumda?" sorusuna canlı cevap
- **Ne yaptım:** Sesle sorulabilen `check_pc_job` aracını ekledim. Komuta'daki son işin canlı durumunu
  söylüyor: sırada mı, kaç dakikadır çalışıyor, şu an hangi adımda; bittiyse ne zaman bitti ve sonucu ne;
  onay bekliyorsa neyi beklediği. Arka uçta `GET /api/remote/komuta/durum` ve `sohbet.job_status()`.
- **Neden daha iyi:** Yunus sesle iş verip başka işe geçiyor. "Dilcep işi ne alemde?" diye sorduğunda
  Chiron'un elinde yalnız oturum açılışındaki eski bilgi vardı; ya bayat cevap veriyor ya uyduruyordu.
  Artık Komuta ekranına bakmadan, gerçek iş kaydından gelen bir cümle duyuyor.
- **Ne öğrendim:** Ses arayüzünde ilerleme bildirirken yalnız arka ucun doğruladığı birkaç durum
  (sırada/çalışıyor/bitti) söylenmeli. "Ne zamandan beri" ve "şu anki adım" bilgisi, belirsiz bir
  "çalışıyor" sözünden çok daha fazla güven veriyor. Kodda: canlı mesajın `at` alanı işin verildiği an,
  iş bitince `_sync` onu bitiş anıyla değiştiriyor. Dock'taki Duraklat düğmesini Yunus 2026-07-30'da
  bilerek "Sohbeti sil" ile değiştirmiş. Yol haritasındaki "Duraklat düğmesi yok" maddesi bu yüzden
  geri eklenecek bir şey değil, yanıltıcı (AssistantDock.tsx'teki yoruma bak).
- **Kaynak:** digitalapplied.com/blog/voice-agent-background-tool-work-guide (doğrulanmış, az sayıda
  iş durumu); blog.logrocket.com/ux-design/ui-patterns-for-async-workflows-background-jobs-and-data-pipelines
  (şu anki adım, son güncelleme zamanı); appmaster.io/blog/background-tasks-progress-ui.

