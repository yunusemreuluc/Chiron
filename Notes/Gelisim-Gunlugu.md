---
tags: [chiron, gelisim]
---

# Gelişim Günlüğü

Chiron'un kendini geliştirme döngüsünün (backend/core/dongu.py § Kendini geliştirme) kaydı. Her geliştirme
kartı en üste bir kayıt ekler: ne yaptı, neden daha iyi, ne öğrendi, kaynak. Sonraki kartlar bunu okuyup
tekrar etmez. Bağlı: [[Ajan-Ofisi]] · [[Istek-Listesi]]

## 2026-11-06 — Saatlik kopmada konuşma unutulmasın
- **Ne yaptım:** Oturum artık sunucunun verdiği devam anahtarını istiyor ve saklıyor (`SessionResume`, `core/live_oturum.py`).
  Kopunca yeni bağlantı aynı anahtarla açılıyor. SIFIRLA, ses seçimi ve ses değişimi yeni oturum istiyor; iki saattir anahtar
  tazelenmediyse de eski konuşma geri gelmiyor. Değişiklik bağlantı başına çağrılan metotlarda, canlı yama ulaşıyor.
- **Neden daha iyi:** Eskiden her kopmada modelin belleği sıfırlanıyor, yalnız diskteki kısa not taşınıyordu. Artık model
  konuşmanın kendisini hatırlamalı. Anahtar reddedilirse üç hızlı başarısızlıktan sonra (mevcut yeniden denemelerle
  ~6 sn, hesap) yeni oturum açılıyor, hata ekranına varmıyor. Bedel: bu birkaç saniye ve üç hata kaydı, bir kez.
- **Ne öğrendim:** K-020'nin açık bıraktığı soruda güçlü kanıt var: sessizlik işe yarıyor gibi. Satır 08:12:32'de düştü, ondan
  sonra 10:06'ya kadar hiç hareketsizlik kopması yok (öncesinde iki dakikada bir). Kesin değil, çünkü mikrofon durumu günlükte
  yazmıyor; açıldıysa oturumu gerçek ses de tutmuş olabilir. 08:12:12'de açılan oturum 09:12:12'de,
  tam 60 dakikada "1011 service unavailable" ile kapandı. Tek örnek; süre sınırı olduğu çıkarım, bu yüzden 1011'i "olağan"
  saymadım, hata olarak yazılmaya devam ediyor. **Gerçek oturumla denemedim:** sunucunun değişen sistem komutuyla devamı kabul
  edip etmediğini belge de söylemiyor (son konuşma notu ve saat her bağlantıda değişiyor). Doğrulama: "Konuşma kaldığı
  yerden sürdürülüyor" satırı `✅ Bağlandı` ile sürüyor mu, "Devam anahtarı çalışmadı" satırı çıkıyor mu? Altı saniyeyi
  aşan ağ kesintisi anahtarı bırakır, o durumda davranış eskisi gibi. Anahtarın geçerlilik süresini arama doğrulamadı
  (Vertex belgesi 24 saat diyor, Gemini API için bulamadım); iki saat benim muhafazakâr seçimim.
- **Kaynak:** `logs/chiron.log` · SDK `_live_converters.py`, `LiveServerSessionResumptionUpdate` ·
  https://docs.cloud.google.com/vertex-ai/generative-ai/docs/live-api/start-manage-session

## 2026-11-06 — İki dakikada bir kopma düzeltmesi yeniden başlatma beklemesin
- **Ne yaptım:** Sessizlik görevini `run()`dan `_send_realtime()`e taşıdım (`main.py`). `run()` süreç boyunca bitmiyor, canlı
  yama çalışan döngüsüne ulaşamıyor; `_send_realtime()` ise her bağlantıda yeniden çağrılıyor. İki alanı da aynı yerde
  kuruyorum, çünkü yamadan önce doğmuş nesnede `__init__` onları kurmamıştı; yoksa görev ilk kontrolde ölürdü. İlk
  başarılı gönderim bağlantı başına bir kez günlüğe yazılıyor ("oturum sessizlikle ayakta tutuluyor").
- **Neden daha iyi:** 02:09'daki düzeltme çalışan süreçte hiç devreye girmedi; hatanın izi 08:03'te hâlâ eski `run()`dan
  geçiyor ve "olağan sebeple" satırı günlükte hiç yok. Son 300 hata kaydının 235'i bu kopma. Artık birleşmeden sonraki ilk yeni
  bağlantıda (kopma sürüyorsa en geç iki dakika içinde), yeniden başlatmadan sessizlik başlar. Ayrıca sessizliğin işe yarayıp yaramadığı ilk kez günlükten okunabilir.
- **Ne öğrendim:** Sessizliğin sunucu sayacını sıfırladığı **hâlâ doğrulanmadı**; arama da belge çıkarmadı, gerçek oturumla
  denemedim. Yeni satırdan sonra kopma sürüyorsa sessizlik işe yaramıyor demektir. O durumda çalışan süreçte hata kaydı da
  durmaz, çünkü sessiz yeniden bağlanma `run()`da ve yeniden başlatma ister. Canlı yamada yeni bir içe aktarma adı
  eklemedim: iki dosya birlikte değişince sıra `main.py` önce gelirse ad bulunamayabilir (kodu okuyarak çıkarım, denemedim).
  K-019 dalı birleşmemiş; muhtemel sebep birleşme kapısının yasakladığı `canli_yukleme.py`ye dokunması (günlükte kayıt yok,
  çıkarım). İ-003, İ-010, İ-011 ve İ-012'ye bu kartta dokunmadım, K-019'a göre ilk üçünün kalanı telefon deposunda.
- **Kaynak:** `logs/chiron.log` · K-019 dalındaki kayıt ·
  https://discuss.ai.google.dev/t/gemini-3-8-live-1011-1008-session-drops-runaway-audio-and-output-transcription-with-unspoken-text/190881
## 2026-11-06 — Canlı yama "uygulandı" deyip eski döngüyü çalıştırmasın
- **Ne yaptım:** Canlı yama (`backend/core/canli_yukleme.py`) `while`/`async for` içeren bir fonksiyonu yamalarken o an
  çalışan bir çerçevesi var mı diye bakıyor (thread yığınları + askıdaki coroutine'ler). Varsa kod yine yamalanıyor ama
  "yeniden başlatma" listesine "şu an çalışıyor, süren çağrı eski kodla devam eder" düşüyor. Canlı nesnesi olan sınıfın
  `__init__`'i değişince de aynısı: "var olan nesneler eski kurulumla duruyor". Mevcut kehribar bildirim yolu kullanılıyor.
- **Neden daha iyi:** Sessizlik düzeltmesi 02:09'da `ChironLive.run()` dahil "uygulandı" (INFO) yazdı, oysa
  çalışan `run()` hiç bitmediği için yeni görev başlamadı: 1008 kopması iki dakikada bir 06:02'ye kadar sürdü, "olağan
  sebeple" satırı bir kez bile çıkmadı. Dört saat kimse bunun beklediğini bilmedi. Artık böyle bir yama uyarıyla bitiyor.
  Bedel: döngülü tanım değişince dosya başına bir tüm-nesne taraması; 2 milyon nesnede 141 ms ölçtüm (yapay süreç,
  Chiron'un gerçek nesne sayısını ölçmedim).
- **Ne öğrendim:** Kopma düzeltmesi **hâlâ denenmedi**, Chiron yeniden başlayınca ilk kez çalışacak; "sessizlik
  sayacı sıfırlıyor mu" sorusu açık. Kanıt günlükte: izde `run` satır 1880 (dosyada artık orası bir yorum, yani bellekteki
  kod eski) ama `_receive_audio` satır 1712'ye kaymış (yeni kod); "Alım hatası" 02:11'de bitti çünkü o metot her bağlantıda yeniden çağrılıyor.
  Yani `_watch_*` ve `_receive_audio` gibi bağlantı başına çağrılanlar da uyarı alır, sonraki bağlantıda kendiliğinden
  düzelir; bildirimin "Yeniden başlatma ister" başlığı onlar için fazla sert, ayrıntı metni "süren çağrı eski kodla" diyor. Sınır: uyarı bir kez çıkar, aynı
  fonksiyonun ikinci yamasında eski çerçeve yakalanmaz. Döngüsüz ama uzun süren çağrı da uyarılmaz. Yalnız birim testle
  denedim, çalışan Chiron'da görmedim. İ-010, İ-011 ve İ-003'ün kalan kısmı telefon deposunda, bu karttan çözülemedi.
- **Kaynak:** `logs/chiron.log` (02:09:21 yaması, 06:02 izi) · [[Canli-Yukleme]]

## 2026-11-06 — Telefondan "PC'de müziği durdur" artık gerçeği söylüyor
- **Ne yaptım:** Telefonun PC medya komutları (`backend/core/desktop_control.py`) kör tuş yerine [[Medya-Kontrol]] yolundan
  geçiyor: oynat/duraklat çalan varsa durdurur, yoksa devam ettirir; sonraki/önceki parça başlık değişimiyle doğrulanır.
  Kör tuş yalnız medya oturumu okunamayınca ya da hiç görünmeyince kalıyor, cevap da "doğrulayamadım" diyor.
- **Neden daha iyi:** Eskiden telefon her seferinde "sonraki parçaya geçildi" diyordu; hiçbir şey çalmasa bile. Artık
  "Şimdi: «parça», sanatçı" ya da "hâlâ çalıyor görünüyor" diyor. İki kaynak çalıyorsa aç/kapa ikisini de durduruyor;
  kör tuşun hangisine gideceği belli değildi. Bedel: medya komutu anlık değil, tahminen ~1,5 sn (ölçmedim; PowerShell
  çağrısı başına ~0,5 sn'den, K-016 ölçümü).
- **Ne öğrendim:** VLC gibi oynatıcılar Windows medya oturumu açmayıp tuşu yine de dinleyebiliyor, o yüzden "oturum yok"
  durumunda tuşu kaldırmak gerileme olurdu. Bu kart İ-003'ü **kapatmıyor**: o kayıt telefonun kendi medyası
  (`manage_device_audio`) içindi ve kodu ayrı depoda; arabadaki deneme hâlâ bekliyor. Gerçek oynatıcı ve telefonla
  denemedim, yalnız sahte oturumlu testler koştu.
- **Kaynak:** [[Medya-Kontrol]] · `Notes/Istek-Listesi.md` İ-003 · K-016 kaydındaki "sıradaki aday" notu

## 2026-11-06 — Mikrofon sustuyken oturum iki dakikada bir düşmesin
- **Ne yaptım:** Hiç ses gitmeyen 20 saniyenin ardından canlı oturuma 40 ms sıfır ses gönderiliyor (`core/live_oturum.py`,
  mikrofondan okumuyor). Yine de hareketsizlik ya da süre sınırıyla kapanırsa ERROR yazmıyorum, deneme sayacına ve
  "Chiron hazır" satırına dokunmadan sessizce yeniden bağlanıyorum. Kota, hizmet kesintisi gibi gerçek arızalar eskisi gibi.
- **Neden daha iyi:** 2026-11-06'nın ilk iki saatinde 118 hata kaydı vardı (iki dakikada bir çift); her döngü ~60 satır
  iz, mikrofonu yeniden açma ve **canlı oturumun belleğinin sıfırlanması** demekti, yeni oturuma yalnız diskteki son
  konuşma notu geçiyor. Sessizlik tutarsa mikrofonu birkaç dakika kapatınca oturum aynı kalır. Süre sınırı kapanışı da
  artık hata gibi görünmüyor.
- **Ne öğrendim:** Sessizliğin sunucunun sayacını sıfırladığı **doğrulanmadı**: belge de, gerçek oturum denemesi de yok
  (kartta anahtar kullanmadım). Doğrulama: mikrofon kapalıyken günlükte "olağan sebeple kapattı" satırı iki dakikada bir
  sürüyorsa sessizlik işe yaramıyor, ama o durumda da gürültü kesilmiş olur. Araç çağrısı sürerken giriş göndermek bazı
  modellerde 1008 ürettiği bildirildiği için o sırada sessizlik de göndermiyorum. Sebep olarak "mikrofon kapalı" da
  çıkarım: 120 sn'lik tam aralıktan ve tek gönderim kapısından; günlükte mikrofon durumu yazmıyor.
- **Kaynak:** `logs/chiron.log` · https://discuss.ai.google.dev/t/gemini-3-8-live-1011-1008-session-drops-runaway-audio-and-output-transcription-with-unspoken-text/190881 ·
  https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/troubleshooting?hl=it

## 2026-11-06 — "Müziği durdur", "sonraki şarkı", "ne çalıyor?"
- **Ne yaptım:** PC'deki sesli Chiron'a `control_media` aracı ([[Medya-Kontrol]], `actions/medya_kontrol.py`): açık
  medyayı durdurur, devam ettirir, sonraki/önceki parçaya geçer, ne çaldığını söyler; istenirse tek uygulamaya
  ("Spotify'ı durdur").
- **Neden daha iyi:** Müzik açabiliyor, sesini ayarlayabiliyordum ama çalanı durduramıyordum; "müziği durdur" boşa
  düşüyordu. Artık tek cümle, ve "durdurdum" demem oturumun durumunu geri okuduktan sonra. Zaten duruyorsa komut
  göndermiyorum, yani kör tuş gibi duran şeyi yanlışlıkla başlatmıyorum.
- **Ne öğrendim:** `Windows.Media.Control` PowerShell 5.1'den bağımlılıksız kullanılabiliyor (`AsTask` köprüsü,
  ~0,5 sn). PS 5.1'de `ConvertFrom-Json` diziyi tek nesne verir: `@()` iç içe dizi yapıp `-contains`'i sessizce
  bozdu, üstelik `catch{}` da hatayı saklayabilirdi — sahte testler geçti, ancak gerçek deneme yakaladı. Kullanıcının
  medyasına dokunmadan canlı deneme mümkün: sessiz WAV'lı kendi `MediaPlayer` oturumu (kalıp [[Medya-Kontrol]]'de).
  Telefon yolu hâlâ kör medya tuşunda — sıradaki aday bu aracı oraya da bağlamak.
- **Kaynak:** https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssession ·
  https://devblogs.microsoft.com/oldnewthing/20231108-00/?p=108980

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

