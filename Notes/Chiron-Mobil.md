---
tags: [chiron, mobil, android]
---

# Chiron Mobil — telefondaki Chiron (Android)

Bağlı: [[Home]] · [[Uzaktan-Erisim]] · [[Mimari]]

2026-09-15, kullanıcı isteği: *"Siri gibi konuşabilecektim; annemi ara deyince
arayacaktı, şuraya WhatsApp'tan mesaj at, PC'de şu an durumum ne."*

Web arayüzü ([[Uzaktan-Erisim]] § Telefon arayüzü) bunu karşılamıyordu: arama,
rehber, SMS ve WhatsApp'a dokunmak yalnızca yerel uygulamaya açık. Bu yüzden ayrı
bir Kotlin uygulaması.

**Kod:** `C:\Users\yunus\Projects\chiron-mobile` — bilerek OneDrive DIŞINDA (Gradle
derleme klasörleri senkronla çakışır). Kendi git deposu.

## Mimari

```
Telefon (Chiron APK)
 ├─ Gemini Live — ham WebSocket, PC'dekiyle AYNI model ve ses (Charon)
 ├─ Telefon araçları — arama, WhatsApp/SMS, uygulama/alarm/fener, ses/medya/DND,
 │                      bildirimler, pil/bağlantı
 └─ Masaüstü köprüsü — Tailscale → tailscale serve → PC /api/remote/{ask,desktop,note}
```

**İki beyin, tek kişilik.** Kullanıcı kararı: "telefon ayrı o ayrı olsun ama bir
olsun." Telefon Gemini'ye kendi bağlanıyor — PC kapalıyken bile arama ve mesaj
çalışıyor. PC'ye yalnızca PC soruları gidiyor. Sistem promptunun ilk bölümü
kullanıcının kendi yazdığı metin, değiştirilmeden (`live/SystemPrompt.kt`).

## Araçlar (kullanıcının verdiği adlarla)

| Araç | Uygulama | Not |
|---|---|---|
| `call_contact` | `ContactTools` → `ACTION_CALL` | Türkçe ek soyma (aşağıda) |
| `send_message` | WhatsApp intent + `WhatsAppSendService` / `SmsManager` | Varsayılan WhatsApp, otomatik gönderim |
| `control_device` | uygulama aç, `AlarmClock`, `CameraManager.setTorchMode` | |
| `manage_device_audio` | `AudioManager`, medya tuşları, DND | DND ayrı özel izin |
| `get_recent_notifications` | `ChironNotificationListener` | Bellekte, diske yazılmıyor |
| `get_device_health` | `BatteryManager`, `ConnectivityManager` | Boşalma süresi tahmini uydurulmuyor |
| `query_desktop_chiron` | PC `/api/remote/ask` | PC cevabı bekleyip metin döner (≤90 sn) |
| `send_desktop_command` | PC `/api/remote/desktop` | Beyaz liste: lock, sleep, medya, pano. Kapatma YOK |
| `save_quick_note` | telefon `notes.json` + PC `/api/remote/note` | Önce telefona yazılıyor |

## Doğrulananlar ve tuzaklar

- **Live protokolü PC'den gerçek anahtarla ölçüldü** (sonra Kotlin'e yazıldı):
  sunucu çerçeveleri BINARY (içi JSON), ilk mesaj `setupComplete`, ses
  `inlineData` audio/pcm;rate=24000, mikrofon `realtimeInput.audio` kabul.
- **Astra çapraz incelemesi (12 bulgu, hepsi doğrulanıp düzeltildi).** En ağırları
  yanlış kişiye işlem: kısmi eşleşmeyle "Annemi" → "Annemin Doktoru", "Ali" →
  "Halil"; aynı adlı iki numaranın teke indirilmesi; WhatsApp göndericinin alıcıyı
  doğrulamaması ve metin kutusu okunamayınca kontrolü atlaması. Diğerleri: kapanmış
  oturumun geç geri çağrıları, çoklu araçta boşta zamanlayıcısı, yankı kapısında
  `write()` blokajı, söz kesilince eski parçanın tekrar çalması, arka planda
  sessizce engellenen ekran açılışının "aranıyor" diye raporlanması, geçersiz PC
  adresinde çökme, PC `/ask`'te geç cevabın yanlış soruya gitmesi, aynı saniyedeki
  iki notun ezilmesi.
- **Eşleştirme kuralı (`ContactMatcher`, 13 JVM birim testi):** doğrudan işlem
  yalnızca TAM ad ya da TAM kelime eşleşmesinde ve tek adayda. Kısmi eşleşme tek
  aday olsa bile `Weak` → model sorar, onaylanınca `contact_id` ile tekrar çağırır.
  Aynı ad + farklı numara ayrı aday. İyelikten türeyen hâl ("annem" → "anne")
  yalnız tam ad eşleşmesinde kullanılıyor — kelime eşleşmesinde "Ayşe Anne"ye çıkıyordu.
- **WhatsApp otomatik gönderim üç şartlı:** silahlı (12 sn, tek kullanım), sohbet
  başlığı hazırlanan kişinin adı/numarası, mesaj kutusu okunabilir ve metin aynı.
  Biri tutmazsa gönderilmiyor ve araç bunu "gönderilmedi" diye dönüyor — "gönderildi"
  yalnızca servis gerçekten tıkladıysa.
- **PC `/ask` sıralaması:** bekleyen, kendi "Siz: <soru>" satırı görülene kadar
  silahsız; ancak ondan sonraki ilk "Chiron:" satırı cevap sayılıyor.
- **Model kişi adını EKİYLE gönderiyor:** "Annemi ara" → `name="Annemi"`. Araç
  açıklaması yalın hâli istese de güvenilmiyor; `ContactMatcher.queryVariants`
  hâl eklerini ve iyeliği soyarak deniyor ("annemi" → "annem" → "anne").
- **Yankı:** telefonda hoparlör mikrofona çok yakın. PC'deki kararın aynısı —
  Chiron konuşurken, `write()` sürerken ve 500 ms kuyrukta mikrofon karesi gönderilmiyor.
- **Sürüm seçimi:** 2026-09'da güncel olanlar AGP 9.4 / Gradle 9.7 / Kotlin 2.4 /
  SDK 37 ama AGP 9 yapı değişiklikleri getirdi; bilinen uyumlu set seçildi:
  AGP 8.7.3, Gradle 8.11.1, Kotlin 2.1.0, compileSdk/targetSdk 35, minSdk 29.
- **Yeni cmdline-tools (23.0) paket yolunda `;` değil `/` istiyor:**
  `sdkmanager "platforms/android-35"`. `;` ile "Package not found" diyor.
- Release APK R8 ile 2.3 MB (debug 55 MB — `material-icons-extended`).

## Derleme ve kurulum

```bash
export JAVA_HOME="/c/Program Files/Microsoft/jdk-21.0.12.101-hotspot"
cd /c/Users/yunus/Projects/chiron-mobile && ./gradlew assembleRelease
/c/Users/yunus/Android/Sdk/platform-tools/adb.exe install -r app/build/outputs/apk/release/app-release.apk
```

`secrets.properties` (git dışı) Gemini anahtarını ve PC adresini ilk açılış
varsayılanı olarak derlemeye koyuyor; uygulama Ayarlar'ından değişir.

## 2026-09-16 — gerçek cihaz (Redmi Note 12 Pro, Android 12)

- **Kurulum kablosuz adb ile Tailscale IP'si üzerinden** (`adb pair <telefonun-tailscale-ip>:<port>`).
  Xiaomi `pm grant`'e izin vermiyor (USB hata ayıklama güvenlik ayarı yok);
  bildirim/DND/overlay adb ile verildi, çalışma zamanı izinleri kullanıcı verdi.
- **YouTube:** `MEDIA_PLAY_FROM_SEARCH` filtresi ilan ediliyor ama sorguyu yok sayıyor.
  Çalışan: `youtube.com/results?search_query=` ve `watch?v=`. `play_youtube` ilk
  videoyu arama HTML'indeki ilk `videoRenderer`'dan buluyor (`AppSearch.kt`);
  `search_in_app` YouTube/Music/Spotify/Chrome/Google/Play/Haritalar.
- **Xiaomi arka plan açılış kapısı:** Android "SYSTEM_ALERT_WINDOW ile izinli"
  dese de MIUI `Permission Denied Activity` ile iptal ediyordu, araç "açıldı"
  diyordu. MIUI app-op 10021 — adb: `appops set com.chiron.mobile 10021 allow`.
  `MiuiBackgroundStart` artık okuyor, kurulum kartında satır var.
- **"Hey Chiron" (Vosk) BAŞARISIZ.** Küçük Türkçe modelin sözlüğünde "Chiron" yok.
  TTS ile 12/16 tuttu ama kullanıcının gerçek sesi: "hayır unut", "hayır oyu",
  "kayra", "yeridir", "hey aydı" — sabit kalıp yok. Grammar modu da kötü
  ("her yer kar" → "hey iron"). `VOICE_RECOGNITION` kaynağı bu cihazda SIFIR
  örnek veriyor, `VOICE_COMMUNICATION` çalışıyor.
- **Ham openWakeWord gömme + DTW şablonu da ayırmıyor:** "Aaron", "ayran" Chiron'la
  aynı skor. Kod şu an Vosk'lu hâlde telefonda (servis bekleme modu, ses devri,
  1,5 sn ön kayıt çalışıyor — sadece tanıyıcı değişecek).

## 2026-09-16/17 — kendi sesiyle uyandırma, araba modu, istek listesi

- **"Chiron" artık openWakeWord.** Vosk kaldırıldı (APK 50 → 23 MB). Eğitim ayrı projede:
  `C:\Users\yunus\Projects\chiron-wake` (kendi `.venv`'i — PATH'teki `python` hermes-agent
  ortamı, oraya paket kurma). Veri: uygulamadaki kayıt ekranı (Ayarlar → Uyandırma sözü
  kaydı; 41 "Chiron", 41 benzer kelime, 6 konuşma, 2 ortam) + edge-tts/piper 4580 klip
  (`synth.py`), `filter_tts.py` TTS pozitiflerini kullanıcının sesine benzerliğe göre süzüyor.
  Model `chiron_r3`: eşik 0,5 + 2 ardışık parça → İngilizce 10,7 sa akışta ~1,9 yanlış/sa,
  eğitime girmeyen kayıtlarda tanıma %63–75, benzer kelime %0.
- **Telefon/Python eşdeğerliği birebir** (82 dosya, fark 0,0000): `WakeTestReceiver`
  (yalnız adb, DUMP izni) + `chiron-wake/device_parity.py`. Mel çıktısı çalışma anında
  `(1, 1, t, 32)` — zaman ekseni üçüncü boyut (Astra yakaladı, ilk sürüm hiç çalışmazdı).
- **Arayüz:** PC'deki tel kafes çekirdeğin Canvas karşılığı (`Orb.kt`, üç ikosfer,
  kapalıyken de buz mavisi); ses düzeyi kaydırıcısı + 9 Gemini sesi (açılır liste);
  geri tuşu ana ekrana döner; anahtar/PC adresi panelden çıkarken kaydedilir, adres
  değişince PC oturumu silinir.
- **Yazıya dökme "Iron Man" yazıyordu:** `inputAudioTranscription.languageHints=tr-TR`
  + `adaptationPhrases` (Gemini API destekliyor, canlı `setupComplete` ile doğrulandı).
- **Araba modu:** oturumda Bluetooth eller serbest (`setCommunicationDevice`, yalnız
  Android 12+; bekleme dinlemesi telefon mikrofonunda kalır — SCO açık kalırsa araba
  radyoyu keser), müzik kısma (geçici odak), gelen WhatsApp/SMS'i okuyup cevap sorma
  (`MessagingStyle` ile yön/tekrar ayrımı, kullanıcı sustuktan 1,5 sn sonra),
  `start_navigation` (ev/iş adresi Ayarlar'da), pil muafiyeti adb ile verildi.
  Gerçek arabada henüz denenmedi.
- **İstek listesi:** Chiron yapamadığı işte "İstek listene ekleyeyim mi?" diye soruyor →
  `add_feature_request` → telefonda `requests_pending.json` → `/api/remote/requests` →
  [[Istek-Listesi]] (`backend/core/feature_requests.py`). Durumu elle `yapıldı` yapınca
  telefon bir sonraki konuşmada, kullanıcının ilk işi bittikten sonra haber veriyor
  (`/requests/done` + `/requests/ack`). Canlı Gemini denemesinde akış doğru çalıştı.
  PC'deki Chiron yeniden başlayınca uçlar devreye giriyor.
- Gemini'ye metin turu (`clientContent`) ses modelinde çalışıyor — mesaj okuma ve
  "yapıldı" haberi bu yoldan.

## 2026-09-21 — araba ses yolu ve istek listesinden gelen işler

- **Arabada SCO kaldırıldı (varsayılan).** Toyota C-HR, eller serbest (SCO) hattını
  telefon görüşmesi sayıp kaynağı "Bluetooth telefon"a çeviriyor ve hat kapanınca
  müziğe DÖNMÜYOR; gerçek aramada dönmesinin sebebi telefon yığınının gönderdiği HFP
  `+CIEV: call,0` göstergesi — uygulamalar bunu gönderemez, yani hattı "kapattık"
  diyemiyoruz. Artık `CarAudio.Route`: PHONE / BT_MEDIA (varsayılan; ses A2DP medya
  akışından, mikrofon telefonun kendisi — araba görüşme durumuna hiç girmiyor) /
  HANDS_FREE (Ayarlar → Araba → "Telefon hattı kullan", eski yol). Bedeli: telefon
  mikrofonu ve araba hoparlöründen dönen yankı — A2DP gecikmesi için yankı kuyruğu
  900 ms. Gerçek arabada denenmedi.
- **Kapanış sırası düzeltildi (İ-003).** `AudioIO.stop()` önce hattı bırakıyordu ama
  mikrofon/hoparlör iş parçacıkları hâlâ açıktı; açık bir görüşme kaydı dururken SCO
  temizlenince Android hattı ayakta tutuyor. Şimdi: `AudioRecord.stop()` +
  `AudioTrack.pause()` → iş parçacıklarını bekle → hat → 600 ms → odak → müzik
  çalıyorduysa `KEYCODE_MEDIA_PLAY`. `CarAudio` tekil, `acquire`/`release` nesil
  belirteciyle korunuyor (eski oturumun geç release'i yeni oturumun odağını bırakmasın).
- **Bluetooth'ta boşta kapanma 45 → 15 sn**, ama Chiron konuşuyorsa süre yenileniyor.
- **`go_home` (İ-001).** Erişilebilirlik servisi bağlıysa `performGlobalAction(HOME)` —
  arka plan açılış kısıtına ve MIUI 10021 kapısına takılmıyor; değilse ana ekran niyeti.
- **Mesaj gönderme iki aşamalı (İ-002).** `send_message` `draft_id` olmadan GÖNDERMİYOR,
  taslak dönüyor; Chiron okuyup onay istiyor, "şunu değiştir" denince yeni taslak. Gönderim
  için üç şart: son taslağın kimliği + numara/kanal/metin birebir aynı + **taslak
  okunduktan sonra kullanıcının sesinin duyulmuş olması** (`AudioIO.lastUserVoiceAt`;
  Astra bu üçüncüsü olmadan modelin okumadan gönderebileceğini gösterdi). Taslak tek
  kullanımlık, 3 dk, oturum kapanınca düşüyor.
- **İstek listesi telefondan okunuyor (İ-004):** `list_feature_requests` →
  `GET /api/remote/requests/list`; PC'ye ulaşılamazsa telefonda bekleyenler dönüyor.
  `add_feature_request` artık `detail` alanı yazıyor (geliştirici için 2-5 cümle;
  kişi adı/mesaj metni/numara YASAK — [[Istek-Listesi]] public depoda takip ediliyor).
- Astra incelemesi: 5 bulgu, hepsi doğrulandı ve düzeltildi (biri kritik: onaysız gönderim).

## 2026-10-03 — PC'deki Claude Code'a iş (Plan Faz 2 + 3)

Bağlı: [[Plan-Claude-Entegrasyonu]] § Faz 1 — yapılan. Araçlar: `delegate_to_claude`,
`claude_job_status`, `cancel_claude_job` (`tools/ClaudeJobs.kt`).

- **Akış:** "Claude'a şunu yaptır" → taslak okunur, "vereyim mi?" → evet → PC kuyruğa alır.
  `ClaudeWatchWorker` (WorkManager, dakikada bir, en fazla 6 sa, PC'nin `active` sayısına göre)
  bitince / onay gerekince bildirim gösterir. Bildirime dokununca konuşma açılır, sonuç
  `[CLAUDE İŞİ]` olarak sesli okunur. Onay sorusunda "evet/hayır" → aynı oturum `--resume`.
- **Güvenlik kapısı** (Astra iki tur, kritik 3): PC'deki Claude tam yetkili, model ise gelen
  WhatsApp mesajını / Claude özetini okuyor. Bu yüzden:
  - Yeni iş iki aşamalı (`draft_id` + taslaktan sonra kullanıcı sesi), `send_message` deseni.
  - Onay cevabı serbest metin değil `decision=approve|reject`; PC'ye giden metni uygulama yazar.
  - Aynı anda tek onay sorusu; kapı soru sesli olarak SONUNA KADAR okununca açılır, kesilirse açılmaz.
- **Ack:** ses çalımı bitince; 50'lik partiler; atomik dosya; söylenen işin bildirimi kaldırılır,
  `claude_told.json` ile geri gelmez.
- Codex Sol ilk sürümü yazdı; güvenlik kapısı ve inceleme düzeltmeleri Claude. Derleme + birim
  test geçti, 2026-10-03 04:28'de telefona kuruldu. **Gerçek cihazda denenmedi.**

## 2026-10-03 (2) — yazılı sohbet ve istek kaldırma

Kullanıcı isteği: "msjlaşma şeyi mobile gelsin, Claude ile yazışma gibi olsun".
- **Yazışma modu:** alt çubukta yazı kutusu (`Composer`). Yazılan mesaj Live oturumuna
  `sendText` ile gider; oturum yoksa açılır, hazır olunca bekleyenler gönderilir. Yazışma
  modunda cevap sesi çalınmaz (`AudioIO.playbackMuted`), mikrofon duraklar (`micPaused`) —
  toplantıda/sessizde kullanılır; cevap ekranda transcript olarak okunur. Mikrofona dokunmak
  sesli moda döndürür. Boşta kapanma 5 dk (sesli 45 sn).
- **Güvenlik:** yazılan mesaj kullanıcı girdisi → `lastUserVoiceAt` ilerler (mesaj taslağı ve
  Claude onay kapıları bunu görür). Mikrofon "duraklı mı" kontrolü ile damga güncellemesi aynı
  kilitte (Astra kritik: eski kare kapıyı açabiliyordu). Servis `exported=false`.
- **Claude balonları:** sonuç / onay sorusu sohbette turuncu "Claude · bitti / onay bekliyor"
  balonu; ekran açıkken süren iş için canlı şerit ("Claude · pytest koşuyor · 2 dk", 5 sn yoklama).
- **İ-005:** `remove_feature_request` → PC `POST /api/remote/requests/remove`, istek
  `yapılmayacak` olur ve listeden düşer, geçmiş kalır (Codex Sol, iki taraf).
- Derlendi, kuruldu (2026-10-03 04:51). Gerçek cihazda denenmedi.

## 2026-10-03 (3) — istekler İ-006..009

- **İ-006 gündem:** Live oturumuna `googleSearch` aracı; aynı native-audio modelle fonksiyon
  araçlarıyla birlikte PC'den canlı doğrulandı (gerçek haber döndü).
- **İ-007 hata bildirimi:** `report_bug` → istek listesine "Hata: …", son 6 araç çağrısının
  kişisel içeriksiz özeti (`RecentCalls`: araç, action, başarı, mesaj başı) eklenir.
- **İ-008 müzik sesi yok:** kök neden oturum boyunca tutulan ses odağı (`CarAudio`,
  `GAIN_TRANSIENT_MAY_DUCK`) — kullanıcının tarifi: "ana ekran ses tuşu açık kalıyor". Başarılı müzik
  komutundan (media_*, unmute, play_youtube) sonra Chiron cevabını bitirince oturum kapanır.
  İ-003 (medya komutu çalışmıyor) büyük ihtimalle aynı kök; arabada doğrulanacak.
- **İ-009 PC raporu:** `get_pc_status` → PC `GET /api/remote/status` (Sol): sesli Chiron'a sormadan
  uptime, CPU/RAM, boşta süre, kilit, ön pencere, Claude işleri, ofis, `voice_ready`. 04:55'teki
  `query_desktop_chiron` hatasının kök nedeni kanıtlanmadı (log yok); olası: PC sesli oturumu duraklı.

## 2026-10-29 — Komuta telefonda, sesli işte onay sorusu yok

Kullanıcı: "Claude'a iş verdim şeklinde olmasın, hemen hallediyorum deyip arka planda yapsın; arada biri var gibi
oluyor" + Komuta'dan kopukluk + ne yaptığını görememe + fazla onay.
- **Sesli iş Komuta'ya:** `delegate_to_claude` → PC `POST /api/remote/komuta {text, new_topic}`. PC son Claude
  sohbetine yazar (aynı `--resume` oturumu); `new_topic` ya da hiç sohbet yoksa yeni sohbet. Son sohbet meşgulse 409
  "önceki iş sürüyor". Onay cevabı `POST /api/remote/komuta/onay {job_id, approved}`; sohbete ait olmayan eski işte
  eski `/api/remote/claude` resume yolu.
- **origin `sohbet_tel`** (backend/core/claude_jobs.py): telefondan gelen sohbet mesajı — sonucu telefona bildirilir
  (`PHONE_ORIGINS`), not "son mesajın sesli okunabilir" der. Telefondaki Komuta ekranından yazılan mesaj da
  böyle: `/api/sohbet/{id}/mesaj` uzak istekte `via=telefon` (`request.state.remote`).
- **Kişilik:** prompt Chiron'a işi kendisi yapıyormuş gibi konuşturur ("Hemen hallediyorum", sonuçta "Hallettim");
  balonlar "PC'de · bitti", şerit "Chiron · <adım>".
- **Hızlı yol kapısı `UntrustedInput`** (tools/ClaudeJobs.kt): taslaksız gönderim yalnız kullanıcının son sözü
  2 dk içindeyse VE son 3 dk modele dışarıdan metin girmediyse. İşaretleyenler: `[YENİ MESAJ]`/`[CLAUDE İŞİ]`
  enjeksiyonu, bildirim/PC cevabı/PC durumu/iş durumu/istek listesi araç sonuçları, Live `groundingMetadata`
  (Google Arama). Kapı kapalıysa eski iki aşamalı akış ("Başlayayım mı?"). JVM testi `UntrustedInputTest`.
- **Komuta ekranı** (`ui/KomutaScreen.kt`): üst çubuktaki sohbet ikonu ya da turuncu şerit açar. Liste → sohbet;
  canlı adımlar (son 6), Onayla/Reddet, Durdur, yazma kutusu; yoklama meşgulken 2 sn, değilken 8 sn.
- Gerçek cihazda Yunus'la denenmedi (Xiaomi `input tap` yetkisi yok).

## 2026-10-29 (2) — APK teslimi: adb'siz kurulum

Soru: "işteyken Chiron Dilcep'i yapar ama kuramaz, sunucu alsam çözülür mü?" — Hayır: kablosuz hata ayıklama
yalnız Wi-Fi'da açık (Xiaomi her Wi-Fi değişiminde kapatıp yeni port veriyor); sunucu da aynı engele takılır.
- **PC:** `backend/core/apk_teslim.py` — kutu `%LOCALAPPDATA%\chironpk` (son 5, zip+manifest kontrolü, sha256).
  Claude işi `venv\Scripts\python.exe backend\corepk_teslim.py <apk> --ad X --not "..."` ile yayınlar
  (`APK_NOTE`: önce `adb devices`, bağlıysa adb). Uçlar `GET /api/remote/apk`, `GET /api/remote/apk/{id}/indir`.
- **Telefon:** `tools/ApkInbox.kt` — `ClaudeWatchWorker` her turda yeni APK'ya bakar, indirir, sha256 doğrular,
  "<ad> hazır · Yükle" bildirimi; dokununca `MainActivity` → izin yoksa "bilinmeyen uygulamalar" ayarı, varsa
  FileProvider (`${applicationId}.apk`, yalnız `cache/apk/`) + `ACTION_VIEW`. Komuta listesinin başında son
  3 günün APK kartı. Komuta'dan gönderilen mesaj da worker'ı kurar. İzin listesinde "Uygulama yükleme".
- Bilinen sınır: worker yalnız iş sürerken yoklar (APK işten gelir); iş yokken elle yayınlanan APK Komuta'da görünür.
- PC tarafı uçtan uca denendi (CLI → liste → 23 MB indirme). Telefonda yükleme Yunus'la denenmedi.

## Sıradaki

- Gerçek kullanımda uyandırma geri bildirimi; arabada 2 ortam kaydı → yeniden eğitim;
  gerekirse Ayarlar'a eşik kaydırıcısı. Pil tüketimi ölçümü.
- **Arabada ölç:** araba telefon kaynağına geçiyor mu, müzik konuşma sonrası geri
  geliyor mu, Chiron kendi sesini duyup sözünü kesiyor mu, seyir hâlinde telefon
  mikrofonu seni duyuyor mu. Kötüyse Ayarlar'dan "Telefon hattı kullan" ile eski yol.
- Arabada mesaj okuma ve kilitli ekranda navigasyonu doğrula.
- WhatsApp otomatik gönderme erişilebilirlik servisi güncellemede kapanmış — kullanıcı açacak.
- **Faz 3 — ortak hafıza:** telefon ve PC aynı `memory.json`'u görsün.
