---
tags: [airon, tuzak]
---

# Bilinen Tuzaklar

Bağlı: [[Home]] · [[Arayuz]] · [[Mimari]] · [[Tasarim-Kurallari]]

Her biri gerçek zamana mal oldu. İlgili alana dokunmadan önce oku.

## Bir WebSocket olayı ÜÇ yer ister

1. `backend/models/events.py` → `EventType` listesi
2. Yayınlayan taraf (`core/web_ui.py`)
3. Tüketen taraf (`frontend/hooks/useAIStateConnection.ts`)

Biri atlanırsa olay **sessizce ölür** — `WebUI._emit` Pydantic doğrulama
hatasını debug seviyesinde yutuyor, hiçbir yerde görünmüyor.

`vision_detections` 2026-07-30'da tam olarak böyle kayboldu.

**Testte dikkat:** olayı doğrudan arayüze enjekte etmek bunu YAKALAMAZ, o yol
backend doğrulamasını atlar. Yakalamanın yolu `WSEvent(event="ad", data={})`
kurmayı denemek.

**`energy_state` için DÖRDÜNCÜ yer var:** `useAIStateConnection.ts` içindeki
`VALID_STATES` kümesi. Olay tipi geçerli olsa bile burada listelenmeyen bir
durum değeri sessizce yutulur ve sahne eski hâlinde donar — hata yok, log yok,
sadece "hiçbir şey olmuyor". Yeni durum eklerken `core/web_ui.py` `STATE_MAP`
ile bu kümenin **aynı** kalması şart (2026-07-31, beş tepki çalışması).

## Kalıcı durum bayrağı sonradan bağlanana GİTMEZ

`assistant_status` (muted/paused/remote) yalnızca DEĞİŞTİĞİ an yayınlanıyordu.
Telefondan uzak mod açıldıktan sonra açılan PC penceresi bayrağı hiç öğrenmedi,
dock "uzak mod" göstermedi ve Aıron sebepsiz susmuş gibi göründü (2026-09-15,
görsel testte yakalandı). Artık `backend/websocket/router.py` her yeni bağlantıya
o anki durumu ilk mesaj olarak yolluyor.

**Kural:** olay olarak yayınlanan her KALICI durum (anlık olay değil), yeni
bağlanan istemciye bir anlık görüntü olarak da verilmeli.

## Katmansız CSS sınıfı Tailwind yardımcısını ezer

`.glass-panel`, `.surface-card`, `.label-micro` `globals.css`'te hiçbir
`@layer` içinde değil; Tailwind v4 yardımcıları ise `@layer utilities` içinde.
Katmansız kural HER ZAMAN kazanıyor: `surface-card rounded-[20px]` 18px kalıyor,
`label-micro text-primary` gri kalıyor. Hata yok, sadece etkisiz sınıf.
Telefon arayüzünde bu yüzden köşe yarıçapı ve etiket rengi satır içi `style`
(2026-09-15).

## framer-motion opacity'yi satır içi yazar

`opacity-0` Tailwind sınıfı onu **ezemez** — satır içi stil her zaman kazanır.

Açılış animasyonunu dıştaki `motion.div`'e, diğer opacity kontrolünü İÇTEKİ düz
bir div'e koy. İki kütüphane aynı özellik için yarışmamalı.

Uyku modundaki HUD sönmesi bu yüzden hiç çalışmadı; perde onu karartıyordu ve
çalışıyor sanılıyordu.

## Ağır Python import'ları tembel olmalı

`ultralytics` modül seviyesinde torch + matplotlib zincirini çekiyordu:
açılışta **273 MB**, kullanıcı nesne tanımayı hiç çalıştırmasa bile.

Kurulu olup olmadığını `importlib.util.find_spec` ile test et — dosya
sisteminde arar, modülü çalıştırmaz (mikrosaniyeler). Gerçek import ilk
çağrının içinde.

Aynı desen `easyocr` için de geçerli ([[OCR]]).

## Gemini yerine yerel modeli tercih et

Ücretsiz katmanın günlük kotası gerçek bir kısıt — vision-ağır özellikler aynı
gün art arda test edilince 429'a takılıyor.

YOLO-World ([[Nesne-Tanima]]) ve EasyOCR ([[OCR]]) ikisi de yerel çalışıyor ve
kotaya hiç dokunmuyor. Gemini'ye ancak yerel yapamıyorsa uzan.

## useFrame içinde asla bellek ayırma

`THREE.Vector3` / `THREE.Color` nesnelerini ref üzerinden yeniden kullan.
Kare başına bir `new`, bileşen başına saniyede 60 ayırma demek.

Hex dizeleri de her karede `THREE.Color`'a çevrilmemeli — `three/palette.ts`
bunun için önbellek tutuyor.

## Sönümle, asla sıçratma

3D için `THREE.MathUtils.damp`, renkler için üstel lerp. Sıçrayan bir değer
durum değişikliği gibi değil, **hata** gibi okunur.

## Live oturum yapılandırmasına yeni alan eklemek riskli

`LiveConnectConfig`'e model desteklemediği bir alan koyarsan oturum **hiç
kurulamaz** — ve bağlantı döngüsü sonsuza kadar aynı sebeple yeniden dener,
yani Aıron tamamen susar. Sessiz bir kayıp değil, tam bir arıza.

`thinking_config` (muhakeme akışı, 2026-07-31) bu yüzden güvenlik valfiyle
eklendi: `_is_thinking_rejection` hatayı inceleyip yapılandırma reddi mi ağ
sorunu mu ayırıyor, reddiyse `_thinking_supported = False` yapıp hemen yeniden
bağlanıyor.

**Kural:** oturum yapılandırmasına eklenen her yeni alan, reddedilme
ihtimaline karşı kapatılabilir olmalı. Bir arayüz özelliği, sesli asistanın
çalışmasından önce gelmez.

## easyocr kurulumu cv2'yi ezmeye çalışır

`pip install easyocr` bağımlılık olarak `opencv-python-headless` çekiyor ve
mevcut `opencv-python`'un `cv2`'sini üzerine yazmaya çalışıyor. Aıron açıkken
dosya kilitli olduğu için kurulum `WinError 5` ile patlıyor.

Projenin kullandığı cv2 API'leri (`VideoCapture`, `resize`, `flip`, `imencode`,
`IMWRITE_JPEG_QUALITY`) zaten `opencv-python`'da var, headless'a gerek yok:

```
pip install ninja lazy-loader imageio scikit-image
pip install easyocr --no-deps
```

## prettier taze bir klonda hemen patlıyor

`git config core.autocrlf` = **true**, yani git depoda LF saklıyor ama çalışma
kopyasına **CRLF** yazıyor. `frontend/.prettierrc.json`'da `endOfLine`
ayarlanmamış, prettier varsayılanı ise `"lf"`. Sonuç: klonlar klonlamaz
`npm run format:check` yüzlerce dosyada başarısız.

Ölçüm (2026-07-31): HEAD'de bir worktree kurulduğunda prettier **58 dosyaya**
kızıyordu — o worktree taze bir checkout'tan başka bir şey değildi.

**Buradan çıkan asıl ders:** "prettier N dosyaya kızıyor" tek başına *hiçbir
şey* anlatmıyor, çünkü N'in büyük kısmı satır sonu. `git diff` bunu göstermez
(autocrlf normalize eder). Gerçek biçim borcunu görmek için `prettier --write`
çalıştırıp **git diff'e** bak: bu depoda 23 "hatalı" dosyanın gerçek karşılığı
**5 dosya, 13 satır**dı, hepsi satır sarma.

Kalıcı çözümü henüz seçilmedi. İki seçenek: `.prettierrc.json`'a
`"endOfLine": "auto"` (prettier dosyanın mevcut hâlini kabul eder) ya da bir
`.gitattributes` + `* text=auto eol=lf` (çalışma kopyası da LF olur). İlki
daha az müdahaleci, ikincisi satır sonlarını gerçekten tekilleştirir.

---

# Arayüzde dürüstlük

Bir paneli bitmiş göstermek için **asla veri uydurma**.

Arkasında backend olmayan panel, nedenini söyleyen dürüst bir boş durum
gösterir. Ajanlar ve Tarayıcı panelleri tam olarak bunu yapıyor ([[Arayuz]]).

Bir yetenek yoksa **hiç görünmez** — soluk bir satır yok, "N/A" yok, yer tutucu
yok. Telemetri kartında GPU ve sıcaklık bu yüzden hiç yer almıyor.

**Alınmamış bir ölçümü asla iddia etme.**

Bayatlamış bir sonuç bayat görünmeli — Vision paneli tespit çerçevelerini 6
saniye sonra soldurur, çünkü kare altlarında akmaya devam eder.

---

# Bakarak doğrula

Tip kontrolü ve derleme, görüntünün doğruluğu hakkında **hiçbir şey
kanıtlamaz**. Bitti demeden önce gerçeğinin ekran görüntüsünü al.

Bunlar SADECE bakarak yakalandı:

- konuşma yeşili premium değil asitti
- uyuyan çekirdek dinlenen bir cisim değil, siyah bir delikti
- HUD hiç sönmüyordu
- bir tespit etiketi kareden taşıyordu

Ölçülebilen şeyi ölç — kutu koordinatları, kaydırma konumu, eleman geometrisi.
**"Doğru görünüyor", bir sayıdan daha zayıftır.**

## Arayüzü nasıl test ediyoruz

**Tercih edilen yol (2026-07-31): sahte backend, sahte soket değil.** Statik
export'u FastAPI ile **8000 portundan** sun (WS adresi 2026-09-15'ten beri sayfanın
kendi kaynağından türetiliyor, ama `/api/*` ile aynı kaynakta olmalı), gerçek bir `@app.websocket("/ws")` aç ve olayları
oradan yayınla. Sayfa gerçek soketle konuştuğu için `VALID_STATES` gibi
arayüz tarafı filtreler de test edilmiş oluyor.

Eski yol — WebSocket'i sahte bir sınıfla değiştirip `window.__emit` ile
enjekte etmek — hâlâ çalışıyor ama **backend tarafını atlıyor**. Pydantic
zarfını, `EventType` listesini ve arayüzün ayrıştırıcısını es geçiyor;
`vision_detections` hatası tam olarak bu yüzden testten kaçmıştı
(bkz. [[Bilinen-Tuzaklar]] § Bir WebSocket olayı ÜÇ yer ister).

**Sayfayı olay tetiklemek için BAŞKA BİR URL'ye götürme.** `page.goto("/emit?…")`
+ `go_back()` WebSocket'i yıkıyor ve uygulama sıfırdan başlıyor: durum `idle`'a
dönüyor, açılış animasyonu baştan oynuyor. Bu fark edilmezse tüm ölçümler
**birbirinin aynı** çıkar ve bu "hiçbir şey değişmiyor" gibi okunur. Tetiği
sayfadan değil, test sürecinden (`urllib`/`requests`) çağır.

Durum değişimi ölçerken `REACT_DAMPING` oturması için ~2 sn bekle; sönümleme
kasıtlı olarak yavaş (bkz. § Sönümle, asla sıçratma).

Yörünge düğümlerine tıklarken `click(force=True)` gerekiyor: düğümler sürekli
döndüğü için Playwright'ın "element sabit olsun" beklentisi hiç karşılanmıyor.

## Rengi ölçerken arka planı dışarıda bırak

Ekran görüntüsünün tamamının ortalamasını almak yanıltıyor: sahne çoğunlukla
siyah, bu yüzden ortalama arka plana kilitleniyor ve gerçek renk farkını
gizliyor.

Beş tepki çalışmasında `memory` ile `thinking` arasındaki Manhattan farkı **13**
ölçüldü — "çok yakın, ayrım yok" demekti. Ekran görüntüsüne bakınca biri
**mor**, diğeri **mavi-gri**, gözle apaçık farklıydılar.

Doğrusu: kırpılan bölgenin **en parlak %15'ini** al (kürenin kendi gövdesi) ve
RGB yerine **ton (hue)** karşılaştır. Aynı ölçüm bu yöntemle 38 derecelik net
bir ayrım verdi. Ayrıca doygunluğa da bak — bir durum diğerlerinden belirgin
soluk kalıyorsa renk bilgi taşımayı bırakır.

Kısacası: sayı gözü doğrulamak için, gözün yerine geçmek için değil.

## Playwright `bounding_box()` CSS `scale`'i görmüyor

Tailwind v4 `hover:scale-*`'ı `transform: scale()` ile DEĞİL, bağımsız `scale`
CSS özelliğiyle uyguluyor. Playwright'ın `locator.bounding_box()`'ı CDP'nin
layout kutusunu döndürüyor ve o kutu bu özelliği içermiyor.

Sonuç: hover büyümesi ekranda çalışırken ölçüm **"1.000, büyümüyor"** dedi
(2026-07-31). Çalışan bir özelliği bozuk sanıp düzeltmeye girişmek üzereydim.

Doğrusu `page.evaluate` içinde **`getBoundingClientRect()`** — o transform'u da
`scale`'i de içeriyor. Teyit için `getComputedStyle(el).scale` de okunabilir;
`transform` bakmak yanıltır, orada `none` yazıyor.

## Kotayı yakan şey araçlar değil, ekran bekçisiydi

Gemini **ücretsiz katmanı günde 1500 istek** veriyor (Flash).
`_watch_screen_for_issues` **25 saniyede bir** görü çağrısı atıyordu:

```
3600 / 25 = saatte 144 çağrı   →   1500 / 144 = 10.4 saat
```

Yani Aıron ~10 saat açık kalınca günlük kota, **kullanıcı tek kelime etmeden**
biterdi. `gemini_desktop_task`, `search_files` ve `activity_log` maddelerinin
üçünde de "test ederken kota dolmuştu" notu var — suçlu test edilen araç değil,
arka planda sessizce dönen bekçiydi.

**Ders:** proaktif bir bekçi eklerken "saatte kaç API çağrısı eder" hesabını
kotayla birlikte yap. 25 saniye makul görünüyor ama günde 3456 çağrı demek.

Çözüm ve ölçülen sonuçlar: [[Izleme-ve-Brifing]] § Kota bütçesi.

## "Ekran sabitken fark küçüktür" — YANLIŞ

Ekran bekçisinin çözümü olarak "görüntü değişmediyse Gemini'ye sorma" kapısı
tasarlandı. Eşiği seçmeden önce ölçüldü ve varsayım çöktü.

Gerçek masaüstünde **ardışık** ekran görüntüleri arasındaki ortalama fark
(0-255 ölçeği, 96×96 gri tonlama): **4.5 / 5.5 / 16.7 / 17.4 / 22.1 / 54.8 /
71.7**. Karşılaştırma için, ekranın ortasında **%30 genişliğinde bir hata
diyaloğu açılması yalnızca 13.6** fark üretiyor.

Yani "sabit" sanılan ekran, açılan bir diyalogdan daha çok değişiyor. Sebebi:
ekranda video/animasyon olabiliyor ve yakalama (adına rağmen) tüm monitörü
alıyor.

**Sonuç: değişim kapısı tek başına yeterli değil.** Video oynarken hiç
kapanmaz. Ölçülen diyalog farkları (%12 → 1.38, %20 → 5.0) eşiğin düşük
seçilmesini gerektiriyor, bu da kapıyı daha da geçirgen yapıyor.

Bu yüzden mimari üç katmanlı oldu ve **garantiyi veren katman tavan**:

1. **Boşta** — kullanıcı masada değilse ekran yakalamaya bile gerek yok
2. **Değişim** — ekran durgunsa sorma (okuma/yazma sırasında çok etkili)
3. **Saatlik tavan** — 1 ve 2 hiç çalışmasa bile kotayı garantiler

**Genel ders:** bir tasarruf mekanizmasının işe yarayacağını varsayma, en kötü
durumda da tutan bir tavanla destekle. Kapı ortalama durumu iyileştirir, tavan
felaketi engeller.

## Türkçe güvenlik listesi diakritiksiz yazımı KAÇIRIR

`auto_fix.DESTRUCTIVE_PATTERNS` yıkıcı eylemleri engelliyor: `satın al`,
`gönder`, `devre dışı`, `kaldır`... Ama model hedefi **diakritiksiz** yazınca
(`Satin Al`, `Gonder`, `devre disi`) alt dize eşleşmesi tutmuyordu ve kapı
**sessizce açılıyordu** — bir güvenlik kapısının en kötü hâli.

LLM'ler Türkçe karakterleri sık atlıyor; bazı arayüzler zaten ASCII yazıyor.
2026-08-01'de testte yakalandı, üç kalıp birden etkileniyordu.

**Kural:** Türkçe metinle çalışan her güvenlik/eşleşme karşılaştırması, iki
tarafı da aynı biçime indirgemeli:

```python
_TR_ASCII = str.maketrans("ıİşŞğĞüÜöÖçÇâÂîÎûÛ", "iissgguuooccaaiiuu")
def _normalize(t): return (t or "").translate(_TR_ASCII).casefold()
```

Liste de normalize edilmiş hâlde tutulmalı — karşılaştırma simetrik olmalı.

Aynı hata eşanlam sözlüklerinde de vardı: `set_auto_fix("guvenli")`
reddediliyordu çünkü anahtar `"güvenli"` yazılmıştı.

## Bir güvenlik kapısı, denetlediği şeye güvenemez

Otonom düzeltmede model her adıma kendi risk puanını veriyor (`low`/`medium`/
`high`). Bu puana **tek başına** güvenmek, kilidin anahtarını hırsıza vermek
olurdu — modelin yanlış tahmini tam da korunmak istediğimiz şey.

Bu yüzden yerel yasak listesi Python'da ve modelden bağımsız duruyor; `all`
modunda bile gevşemiyor.

Bir kademe daha var: yasak listesi yalnızca **tarifi** görüyor, model "Sil"
düğmesine *"kırmızı buton"* derse kaçırırdı. Çözüm iki fazlı uygulama —
`intervene_screen(confirm=False)` önce hedefi BULUR ve bulduğunu geri verir,
denetim **bulunan şeyin** tarifi üzerinde yapılır, ancak temizse tıklanır.
Ayrıntı: [[Otonom-Duzeltme]].

## Mikrofon: host API'yi de ölç, yalnızca cihazı değil

2026-08-06'da Aıron kullanıcıyı duymuyordu (`karar=silent medyan=0.5`). Bu
makinedeki HER giriş cihazı, HER host API üzerinden ayrı ayrı ölçüldü
(`probe_input` ile — uygulamanın kendi ölçüsü, ayrı bir ölçüt uydurulmadı):

| Host API | Cihaz | 16 kHz | Native (48 kHz) |
|---|---|---|---|
| MME | Headset Microphone (varsayılan) | medyan 0.49, tepe 0.53 | tepe 0.50 |
| MME | Microphone Array (AMD) | medyan 0.49, tepe 0.92 | — |
| DirectSound | hepsi | medyan **12612**, tepe 23417 | medyan 1371 |
| WASAPI | Headset Microphone | **açılamıyor** (Invalid sample rate) | medyan 0.00, tepe 5.6 |
| WASAPI | Microphone Array (AMD) | **açılamıyor** | medyan 0.94, **tepe 361**, yayılım 71 |

Kullanıcı konuşurken ölçüldüğünde iki WASAPI cihazı da **çalıştı** (kulaklık
tepe 19771, dizi 3911). Yani donanım sağlam, sorun tamamen yoldaydı. Üç ders:

**1. PortAudio varsayılanı MME ve bu makinede MME ölü.** `mic_device` boşken
PortAudio varsayılanı seçiyordu, o da MME Headset.

**2. `resolve_device_index` host API'ye bakmıyor.** İsim ipucuna göre indeks
sırasıyla ilk eşleşmeyi alıyor; `"Microphone Array"` yazmak MME'deki (ölü)
kopyayı seçiyordu. Yani config'i doğru yazmak bile sorunu çözmüyordu.

**3. WASAPI 16 kHz'i reddediyor** (`Invalid sample rate`) — paylaşımlı modda
cihazın kendi hızını istiyor. `SEND_SAMPLE_RATE = 16000` sabit olduğu için
çalışan tek yol hiç denenmiyordu.

Çözüm (2026-08-06): `resolve_input_device` WASAPI'yi tercih ediyor ve sistemin
varsayılan cihazının ADINI o API altında arıyor (kullanıcının Windows'ta yaptığı
seçime saygı, yalnızca yol değişiyor); `open_input_stream` hızı uzlaşıyor ve
`downsample_int16` 48 kHz'i 16 kHz'e indiriyor.

**DirectSound'a güvenme ama eşiğe de güvenme.** DirectSound bu makinede çöp
üretiyor; ardışık iki ölçümde medyan **12612** ve **838** (ikincisinde tepe
27070) verdi. Yani "makul olmayan seviye" kapısı bazen yakalıyor bazen
kaçırıyor — asıl koruma cihaz seçiminin WASAPI'yi tercih etmesi, eşik yalnızca
ikinci savunma hattı.

## Sessiz mikrofonla ölü mikrofon AYIRT EDİLEMEZ

`core/audio_devices.py`'nin kurucu varsayımı şuydu: "çalışan bir mikrofon sessiz
odada bile gürültü tabanı üretir; ölü akış tam sıfır döndürür." Medyan 3.0'ın
altındaysa kullanıcıya **"mikrofonun BOZUK"** deniyordu.

2026-08-06'da çürüdü. Aynı Realtek kulaklık, WASAPI, aynı gün:

| Ne zaman | medyan | tepe | yayılım |
|---|---|---|---|
| sessizken (1. ölçüm) | 0.00 | 5.6 | 1.13 |
| sessizken (2. ölçüm) | 0.00 | 0.0 | **0.00** |
| konuşurken | — | **19771** | — |

WASAPI, MME'nin aksine sahte bir gürültü tabanı uydurmuyor: sinyal yoksa gerçek
dijital sıfır veriyor. Yani **çalışan** mikrofon "ölü" görünüyordu.

İlk düzeltme denemesi "seviyeye değil DEĞİŞİME bak" idi (yayılım 1.13 vs ölü
MME'nin 0.01'i). İkinci ölçüm onu da çürüttü — yayılım da 0.00 çıkabiliyor.

**Kalıcı sonuç: ses olmadan bu ayrım YAPILAMAZ.** Eşik ayarı sorunu değil, bilgi
eksikliği. Sonda artık sessizliğe arıza demiyor; `describe_input_problem`
(kanıtlanmış arıza → sohbete ERR) ile `describe_input_observation` (gözlem →
yalnızca geliştirici akışı) ayrı fonksiyonlar. İkisini tek metne karıştırmak,
ölçülmemiş bir arızayı ölçülmüş gibi göstermek olurdu.

Bu, § Arayüzde dürüstlük kuralının teşhis mesajlarına uzanan hâli: **alınmamış
bir ölçümü asla iddia etme** — "hiçbir şey duymadım" ile "mikrofonun bozuk"
aynı cümle değil.

## "Mikrofon hatasi" her zaman mikrofon değildir

`_listen_audio` kapanış yarışında `RuntimeError: cannot schedule new futures
after shutdown` fırlatıyor: sohbet sıfırlanırken event loop'un thread havuzu
mikrofon döngüsünden önce kapanıyor. Bu ERROR seviyesinde, tam traceback ile,
`[AIRON] Mikrofon hatasi` başlığıyla loglanıyordu.

2026-08-06'da gerçek bir mikrofon sessizliği araştırılırken bu satıra takılıp
yanlış yere bakıldı — normal bir yeniden bağlanma, donanım arızası gibi
okunuyordu. Artık ayrı yakalanıp INFO olarak yazılıyor.

**Ders:** sessiz arıza kadar pahalı olan şey, arıza OLMAYANI arıza diye
raporlamaktır. İkisi de teşhisi yanlış yere götürüyor.

## Bir şeyi ÖRTEN cismi kaldırınca örttüğü hata ortaya çıkar

`ElectricArcs` paletin durum rengine yalnızca `speaking` durumunda çekiliyordu;
`automation` (kehribar) ve `memory` (mor) çekirdeklerin etrafında arklar buz
mavisi kalıyordu. Palet dosyasının en başında bu hatayı önlemek için yazılmış
bir kural var — ve kural çiğnenmiş olmasına rağmen **aylarca kimse görmedi**,
çünkü dolu plazma küre arkların yarısını örtüyordu.

Çekirdek tel kafese dönüp (2026-08-06) `depthWrite` kapanınca arklar cismin
içinden geçer oldu ve uyumsuzluk ilk ekran görüntüsünde apaçık çıktı.

**Ders:** bir bileşeni saydam/görünür yapan her değişiklik, o bileşenin ARKASINDA
duran her şeyin de gözden geçirilmesini gerektirir. Değişiklik onları bozmadı —
zaten bozuklardı, yalnızca görünür oldular. Bu yüzden "sadece çekirdeği
değiştirdim, arklara dokunmadım" demek yeterli değil: ekrana bakmak gerekiyor.

## Bir formu değiştirirken ışık modelini DEVRALMA

Tel kafes çekirdek, dolu kürenin fresnel kenar payını (0.75) olduğu gibi
devralmıştı. Dolu yüzeyde o pay yalnızca ince bir silüet şeridini boyuyor;
kafeste çizgilerin çoğu bakışa göre eğik olduğu için **tüm orb** platin beyaza
yıkandı ve durum renkleri (buz mavisi / turkuaz / kehribar / mor) birbirinden
ayırt edilemez oldu. Renk burada bilgi taşıyor — solması sessiz bir kayıp.

Aynı çekimde ikinci ders: küreye sarılan 13 sarımlı bir **spiral**, önden
bakınca spiral değil **yatay çizgi yığını** gibi okunuyor. Geometri doğruydu,
görüntü yanlıştı.

İkisi de yalnızca ekran görüntüsüyle yakalandı; `tsc` ve `eslint` temizdi.

## "Ekran durdu mu" MUTLAK eşikle ölçülemez

`gemini_automation.py` görsel üretiminin bitişini sabit 18 saniye bekleyerek
tahmin ediyordu. Yerine "ekran değişmeyi bırakınca bitmiştir" tespiti kondu:
ardışık ekran görüntülerinin 64x64 gri parmak izleri karşılaştırılıyor
(tamamen yerel, Gemini çağrısı harcamıyor).

İlk sürüm mutlak bir eşik kullandı (fark < 1.5 ise "durdu"). **Ölçümde çürüdü:**
hiçbir şey yapılmayan durgun bir masaüstünde ardışık kareler arasındaki fark
**15-71/255** aralığında geziyordu (imleç, saat, animasyonlu bileşenler). Eşik
hiç tetiklenmedi, fonksiyon her turda tavana kadar bekledi — yani sabit
beklemeden **daha kötü**.

Doğrusu göreli: üretim sürerken fark tepe yapar, bitince tabana iner. Tepenin
belirgin bir kesrine düşmek (`SETTLE_DROP_RATIO`) "durdu" demek. Aynı gürültülü
ortamda 45 sn tavan yerine 13 sn'de durdu.

**İkinci ders — hangi karar neye emanet:** aynı piksel farkı "yazı gönderildi
mi" sorusuna cevap veremez, çünkü taban gürültüsü gerçek bir değişiklikten
ayırt edilemiyor. Bölüm net: **piksel farkı ZAMANLAMA için, vision DOĞRULUK
için.** Yanlış zamanlama vakit kaybettirir; yanlış doğrulama "yaptım dedi ama
yapmadı" hatasını geri getirir (§ Arayüzde dürüstlük).

## İndirme "tıkladım"la değil "dosya geldi"yle doğrulanır

Aynı dosyada `_download_latest_image` başarıyı indirme ikonuna tıklayabilmekten
sayıyordu. Tıklama başarılı olup indirme hiç başlamayabilir — o durumda araç
kullanıcıya olduğundan fazla görsel indirdiğini söylerdi.

Artık yer gerçeği İndirilenler klasörü: tıklamadan önce dosya listesi alınıyor,
sonra yeni ve **yazılması bitmiş** (`.crdownload` değil, boyutu iki ölçümde
sabit) bir dosya belirene kadar bekleniyor. Sayaç artık dosya sayıyor.

## Kaydırma konumunu içerik eklendikten SONRA ölçme

`useEffect` yeni satır DOM'a girdikten sonra çalışıyor. Orada
`scrollHeight - scrollTop - clientHeight` hesaplamak "kullanıcı dipte miydi"
sorusunu **cevaplamıyor** — matematiksel olarak tam olarak yeni eklenen
içeriğin yüksekliğini veriyor:

```
mesafe = (H + yeni) - (H - clientHeight) - clientHeight = yeni
```

Sonuç sinsi: kısa mesajlarda eşiği geçtiği için çalışıyor gibi görünüyor,
uzun mesajlarda sessizce bozuluyor. Sohbette tam bu yaşandı (2026-08-01).

**Kural:** "kullanıcı dipteydi mi" bilgisi `onScroll` olayında, yani içerik
değişmeden ÖNCE bir ref'e yazılmalı; efekt o ref'e bakmalı.

## SwiftShader'da olaylar GECİKİYOR — 500 ms yetmez

Headless Chromium + SwiftShader'da 3D sahne ana iş parçacığını doyuruyor;
React olay işleme ve CSS geçişleri belirgin şekilde gecikiyor.

2026-08-01: hover sonrası 500 ms bekleyen bir test "imza sönmüyor" dedi ve
çalışan bir düzeltmeyi bozuk gösterdi. Aynı ölçüm **1500 ms** ile doğru sonucu
verdi. Ara değerler ele veriyordu: opaklık `0.6117`, etiket `0.456823` — yani
geçiş ortasında yakalanmıştı, hiç başlamamış değil.

**Kural:** SwiftShader altında etkileşim ölçerken CSS geçiş süresinin en az
5-6 katını bekle ve **ara değer** görürsen (0 ile 1 arasında) daha da uzat.
Ayrıca sınıfın uygulanıp uygulanmadığını `className` ile AYRI doğrula —
hesaplanan değer geçişten etkilenir, sınıf listesi etkilenmez.

İlgili: § Playwright `bounding_box()` CSS `scale`'i görmüyor. İkisi de aynı
dersin parçası — ölçüm aracının kendisi de test edilmeli.

## Stylesheet'i tarayıp "bu sınıf yok" deme

`document.styleSheets` üzerinde düz gezinip `.opacity-15` aramak
**URETILMEMIS** dedi, oysa `getComputedStyle(...).opacity` `0.15` döndürüyordu.
Tailwind v4 kuralları iç içe katmanlarda tutuyor; düz `cssRules` gezintisi
hepsini görmüyor.

Bir stilin uygulanıp uygulanmadığının yer gerçeği **`getComputedStyle`**, CSS
metnini aramak değil.

## Kare hızı ölçümü kendi kendini doğrulamalı

Halka tampon üzerinden alınan **ortanca** kare süresi tek başına yalan
söyleyebilir: tampon yalnızca son N kareyi tutar, arada uzun duraklamalar olsa
bile "tipik" kare hızlı görünür.

İlk ölçüm (2026-07-31) **142.9 FPS** dedi. Aynı çıktıda 10 saniyede yalnızca
738 örnek vardı — 143 FPS doğru olsaydı ~1430 kare olmalıydı. İki sayı
birbirini çürütüyordu. Doğru cevap ~70 FPS'ti.

Bu yüzden `FrameProbe` toplam kare sayısı ve geçen süreyi de tutuyor:
`avgFps` (toplam/süre) ile `fps` (ortancadan) ayrışıyorsa ölçüme
güvenilmez. Ölçüm protokolünde ayrıca:

- Tıklamadan **sonra oturma payı** bırak — panel açılış animasyonlarını ölçüme
  katmak "sahne yavaş" demek olur, oysa ölçülen tek seferlik bir geçiş.
- Karşılaştırılan turlar **aynı uzunlukta** olmalı.
- Aynı ölçümü **en az iki kez** al; tek tur arka plan yüküne fazla duyarlı
  (bu depoda iki tur 68.8 ve 77.6 FPS verdi).
- Headless Chromium + SwiftShader ile FPS ölçme: yazılım rasterleştirme, sayı
  anlamsız. Gerçek pencere (pywebview + `gui="edgechromium"`) ya da en azından
  donanım hızlandırmalı bir tarayıcı gerekiyor.

## Alt süreç ağacı "ebeveyni öldür + çocuklarını bul"la ölmez

2026-10-03, Claude iş yöneticisi (`backend/core/claude_jobs.py`), Astra incelemesi gerçek
Windows süreçleriyle gösterdi: ebeveyn çıkar, arka planda başlattığı bir torun stdout'u
miras alıp açık tutar. `for line in proc.stdout` EOF'u hiç görmez, `psutil` ile
`children()` artık ebeveyn olmadığı için torunu bulamaz, zaman aşımı "ebeveyn zaten
bitmiş" deyip hiçbir şey yapmaz — kuyruk sonsuza dek `running` kalır.

Çözüm **Windows Job Object**: süreç `CREATE_SUSPENDED` başlatılır, job'a atanır, sonra
uyandırılır (atamadan önce çocuk doğuramasın). `TerminateJobObject` bütün ağacı tek
çağrıda öldürür; `KILL_ON_JOB_CLOSE` sayesinde Aıron çökse bile Windows ağacı temizler.
Okuma ayrı thread'de; ana thread `proc.wait(timeout)` bekler, sonra job'u kapatır →
stdout'u tutan kalmaz → okuyucu EOF görür.

Aynı işte ikinci tuzak: npm'in kurduğu `claude` bir **`.CMD`**. Windows'ta .cmd/.bat'a
verilen argümanlar cmd.exe ayrıştırmasından geçer (`&`, `|`, `%` — "BatBadBut"); kullanıcı
metni asla argüman olmaz. Arkasındaki `claude.exe` doğrudan çağrılır, metin stdin'den gider.

## Hook cevabı Windows'ta cp1254 çıkar

Python hook'u (`bekci.py`) `sys.stdout.write` ile JSON cevap verdiğinde Windows varsayılanı cp1254;
Türkçe gerekçe ("Aıron bekçisi…") UTF-8 bekleyen tarafta bozuluyor/çözülemiyordu. İlk canlı deneme ASCII
gerekçeyle yapıldığı için görünmedi, Türkçe testte yakalandı (2026-10-26). **Kural:** Claude Code hook'u
yazan her Python betiği `sys.stdin`/`sys.stdout`'u `reconfigure(encoding="utf-8")` ile açar.

## Masaüstü Aıron derlenmiş kopyayı açar, geliştirme sunucusunu değil

Kısayol `desktop.py`'yi açar; o `frontend/out` (statik `next build` çıktısı) sunar. `AIRON.bat` yalnız `out`
yoksa derliyordu — 2026-10-26 03:11'den sonraki bütün arayüz işi (bekçi, 7/24, Komuta) Yunus'un Aıron'unda
görünmedi; denemeler `next dev`'de yapıldığı için fark edilmedi ("hâlâ aynı görünüyor", 2026-10-27).
**Çözüm:** `desktop.py` açılışta kaynak (`app`, `components`, `services`, `stores`… ve config) `out/index.html`'den
yeniyse `npm run build` çalıştırır (`_rebuild_frontend_if_stale`). **Kural:** arayüz işi bitince `npm run build`
de çalıştır; "çalışıyor" demeden önce derlenmiş kopyada (ya da Aıron'un kendisinde) bak.
