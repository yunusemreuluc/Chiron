---
tags: [chiron, arayuz]
---

# Arayüz — frontend/ (Next.js + Three.js)

Bağlı: [[Home]] · [[Mimari]] · [[Kurulum-ve-Baslatma]] · [[Nesne-Tanima]] · [[OCR]] · [[Izleme-ve-Brifing]] · [[Bellek-ve-Config]]

3D sahne + üzerinde yüzen cam paneller. Tasarım kuralları `CLAUDE.md` içinde;
kalan işler `Docs/CHIRON_UI_ROADMAP.md`. Bu not **ne yapıldığını ve neden öyle
yapıldığını** özetliyor.

## Yerleşim

> **2026-10-29:** Dönen yörünge düğümleri (`OrbitNodes`), aralarındaki çizgiler (`NodeConnections`), şimşek
> (`ElectricArcs`) ve düğüm odak kartı (`NodeFocusCard`) kullanıcı isteğiyle silindi; sahnede çekirdek, tendriller
> ve toz kaldı. Vision paneli kamera açıkken gelir. Pencere **küçük, normal** açılır (kullanıcı: "açılışta küçük
> olsun"): kayıt yoksa ekranın %60x%70'i ortada, büyütülmüş kapatılsa da son normal boyut. Kök neden: `min_size`
> 1280x800 %125 ölçekte 1600x1000 fiziksel (ekranın %83'ü) ve 1600x950 başlangıç boyutu ekrandan büyük olduğu için
> WinForms pencereyi "büyütülmüş" işaretliyordu → ikisi küçültüldü. **F11** tam ekran (görev çubuğu dahil), tekrar
> F11 ya da Esc ile geri — `desktop.py FullscreenToggle` (Win32; pywebview `toggle_fullscreen` hiçbir şey
> yapmıyordu) + `_watch_fullscreen_keys`: tuş Windows'tan okunuyor, çünkü WebView2 F11'i sayfaya ulaştırmadı
> (Playwright'ta sayfa dinleyicisi çalıştı, gerçek pencerede çalışmadı). Yalnız Chiron öndeyken.
> **Asıl F11 hatası:** `FindWindowW("Chiron")` Chiron'u değil Windows 11 görev çubuğunun aynı başlıklı
> `TabProxyWindow`'unu buluyordu — "Chiron önde mi" hep hayır, boyut kaydı da vekilin dikdörtgeni. `_handle()`
> artık pywebview formunun tanıtıcısını (yoksa bu sürecin penceresini) kullanıyor. Açılış boyutu kullanıcının
> elle ayarladığı 1575x945 @ 284,33 (fiziksel); varsayılan oran 0.82x0.875. Ölçüldü: F11 → 1920x1080, F11/Esc → geri. **Kenar boşluğu (aynı gün):** ham Win32 tam ekranında pencere büyüyor ama WebView2'nin
> iç tarayıcı penceresi (`Chrome_WidgetWin_1`) eski boyutta kalıyordu — sağ/altta boş zemin. Şimdi WinForms
> özellikleriyle (UI iş parçacığı, Invoke) + `_sync_webview`: denetleyiciye (`_coreWebView2Controller`, yansıma)
> `Bounds` + `NotifyParentWindowPositionChanged()`. Ölçüldü: tüm alt pencereler 1920x1080, dönüşte 1557x898.

| Konum | Ne var |
|---|---|
| Sol üst | CHIRON imzası + canlı durum (`BrandBadge.tsx`) |
| Sol, imzanın altı | Ayarlar paneli (`LeftPanel.tsx`) |
| Sol alt | Ajanlar + Ayarlar düğmeleri (`Sidebar.tsx`) — sohbet dock'unun aynası |
| Sağ üst | Telemetri şeridi + tepsi düğmesi (aynı satır) |
| Sağ | Vision paneli, altında düğüm odak kartı |
| Sağ alt | Sohbet dock'u (`AssistantDock.tsx`) |
| Orta | 3D sahne (`three/Scene.tsx`) |
| Orta, çekirdeğin çevresi | Oturum yörüngeleri — her canlı Claude oturumu küçük bir çekirdek (`three/SessionOrbits.tsx`), bkz. § Oturum yörüngeleri ve Gözetim |
| Üst orta (yalnız araştırma sürerken) | Araştırma canlı kartı; "göster" ile pano — çekirdek küçülüp sağ kolona kayar, kartlar öne gelir — [[Arastirma-Panosu]] |

Sağ taraf **tek bir flex kolon** (`AppShell.tsx`). Önceden her panel kendini
`absolute right-7` ile konumlandırıyordu ve üst üste biniyorlardı.

## Veri akışı

Tek WebSocket (`useAIStateConnection.ts`) her şeyi taşıyor. Backend'den gelen
olaylar `backend/models/events.py` içindeki `EventType` listesinde tanımlı.

> **Tuzak:** yeni bir olay eklerken üç yeri birden yapmak gerekiyor — `EventType`
> listesi, yayınlayan taraf, ve arayüzdeki `switch`. Biri atlanırsa olay
> **sessizce düşer**: `WebUI._emit` Pydantic doğrulama hatasını yutuyor.
> 2026-07-30'da `vision_detections` tam olarak böyle kaybolmuştu.

Soket **olayları** taşıyor; **istekler** (komut gönderme, ayar yazma, telemetri
okuma) HTTP ile gidiyor ve hepsi tek bir yerden geçiyor: `services/apiClient.ts`.
Orada üç şey var — taban adres (`apiBase()`: masaüstünde boş string, `npm run
dev`'de `localhost:8000`), backend'in `{success, message, data}` zarfı ve
backend kapalıyken arayüzü çökertmeyen sarmalayıcılar (`request` / `post` /
`fetchData`).

`fetchData` başarısızlıkta `null` döner — çağıran taraf "veri yok" ile "backend
yok" arasında ayrım yapmadığı için ikisi de aynı sonuca çıkıyor: gösterilecek
bir şey yok, uydurma da yok (bkz. [[Bilinen-Tuzaklar]] § Arayüzde dürüstlük).

Bu dosya 2026-08-06'da açıldı: aynı üç şey beş servis dosyasında ayrı ayrı
yazılıydı ve `apiBase` gereksiz yere `voiceApi.ts` içinde oturuyordu — görü,
ayarlar ve ses efektleri onu sesli asistan modülünden import ediyordu.

## Açılış sahnelemesi — "Ateşleme"

Kullanıcı isteğiyle (2026-07-31) yeniden tasarlandı. Önceki sürüm siyah ekranda
CHIRON yazısı ve **dolan bir ilerleme çubuğuydu** — bu bir yükleme ekranı dili ve
`CLAUDE.md § PROJECT`'in "gösterge paneli DEĞİLDİR" maddesiyle çelişiyordu.
Sonrasındaki 3D kuruluş zaten iyiydi; sorun ondan öncesiydi.

Yeni akış tek bir fikir üzerine kurulu: **çekirdek ateşleniyor.**

| Zaman | Ne olur | Nerede |
|---|---|---|
| 0 – 0.3 sn | Karanlıkta tek bir ışık noktası | `BootOverlay.tsx` |
| 0.3 – 0.8 sn | Nokta yanlara **enerji hattı** olarak açılır | " |
| 0.6 – 1.2 sn | CHIRON ışıktan **çözülür** (bulanıklık dağılır, harf aralığı toplanır) | " |
| 1.05 sn | Gerçek bağlantı durumu ("Bağlanıyor" / "Sistem hazır") | " |
| 1.2 – 2.7 sn | **İsim durur** | " |
| 2.5 – 3.5 sn | **Korona** — ısı yayan parçacıklar | `three/EnergyTendrils.tsx` |
| 2.7 – 3.8 sn | Karanlık **merkezden delinir**; isim aynı anda çözülerek gider | `BootOverlay.tsx` |
| 3.4 sn | Enerji çekirdeği (top) | `three/EnergyCore.tsx` |
| 4.0 sn + | Yörünge düğümleri (sırayla) | `three/OrbitNodes.tsx` |
| 4.2 sn | Bağlantı ağı | `three/NodeConnections.tsx` |
| 4.6 sn | Elektrik arkları | `three/ElectricArcs.tsx` |
| 5.0 sn + | HUD panelleri (0.12 sn aralıkla) | `AppShell.tsx` |

**Sıralama bilinçli** (kullanıcı isteği, 2026-07-31 ikinci tur): önce ısı yayan
korona, sonra top. Korona perde delinirken belirmeye başlıyor, yani açılan
delikten ilk görünen şey o oluyor; çekirdek arkasından geliyor.

Korona 2026-07-31'e kadar **hiç açılış animasyonu taşımıyordu** — ilk kareden
itibaren tam güçteydi ve perde kalkınca hazır bir bulut olarak "patlıyordu".

### İsmin çıkışı ayrı

Delik tam merkezden açılıyor ve isim de merkezde duruyor; maskeye bırakılsaydı
isim ~300 ms'de **kesilip** yok olurdu — perde 1.1 sn boyunca açılsa bile
izleyicinin baktığı şey aniden gidiyordu.

Bu yüzden isim kendi çıkış variant'ına sahip (`WORD_VARIANTS.pierced`): geldiği
gibi gidiyor — bulanıklaşarak ve harf aralığı açılarak, yani ışığa geri
çözülüyor. `AnimatePresence` çıkış etiketini çocuklara yaydığı için `pierced`
adı üstteki perdeyle eşleşiyor; bu yüzden çocukların `variants` kullanması
şart (satır içi `initial`/`animate` propları yayılımı almıyor).

Durum satırı `conversationStore.connected`den geliyor, yani **gerçek**; sahte
bir yüzde göstergesi değil (bkz. [[Bilinen-Tuzaklar]] § Arayüzde dürüstlük).

### Maske tuzağı

Delinme `mask-image: radial-gradient(... transparent var(--hole), #000
calc(var(--hole) + 18%))` ile yapılıyor; `--hole` framer-motion variant'ından
animasyonlanıyor (satır içi nesnede hesaplanmış anahtar olarak yazılınca
TypeScript framer-motion'ın hedef tipine oturtamıyor — variant'lar kabul ediyor).

**`--hole` sıfırdan değil `-25%`ten başlıyor.** Sıfır verilirse gradyan
`transparent 0% → siyah 18%` olur ve merkezde **kalıcı bir yumuşak delik** kalır;
sahne daha ilk kareden görünür. İlk denemede tam olarak bu oldu, ölçerek
yakalandı: `--hole` zamanlaması doğruydu ama %0'ın kendisi şeffaflık üretiyordu.

### Sahnelemenin dışında kalanlar (düzeltildi)

Zaman çizelgesi ve sohbet dock'u eskiden ilk kareden itibaren tam görünürdü —
logo daha çıkmadan ekranda duruyorlardı. Artık sıraya dahiller.

Dikkat: bu iki panel alt kenara yapışık (`bottom-7`) ve `y` animasyonu bir
**transform** yaratıyor; transform "containing block" kurduğu için içindeki
mutlak konumlu kartlar sahnenin altına değil sarmalayıcının tepesine hizalanır.
Bu yüzden `fadeOnlyVariants` ile **yalnızca opacity** üzerinden beliriyorlar.

### Hareket azaltılmışsa

Ateşleme, hat, delinme — hiçbiri yok. Statik CHIRON yazısı 400 ms görünüp
kayboluyor. Doğrulandı: `prefers-reduced-motion: reduce` ile hiçbir hareket
çalışmıyor.

## Vision paneli

Canlı kamera + [[Nesne-Tanima]] + [[OCR]]. `webcam_frame` olayı ~8 FPS base64
JPEG taşıyor (yıllardır yayınlanıyordu, arayüzde tüketen yoktu).

**Görünürlük:** her zaman durmuyor — kamera açıkken **veya** sahnedeki "Görme"
düğümüne tıklanınca geliyor. Kapalı kamerayla sürekli duran siyah 16:9 kutu sağ
kolonun yarısını hiçbir şey söylemeden yiyordu. "Görme" düğümüne tıklanınca
genel odak kartı yerine bu panel açılıyor (`NodeFocusCard` o düğümü bilerek
atlıyor).

**Çerçeveler:** nesne ve metin kutuları aynı normalize `[x1,y1,x2,y2]`
sözleşmesini paylaşıyor, tek bileşen ikisini de çiziyor. Panel her zaman **en son
çalışan işin** sonucunu gösteriyor (`mode: 'objects' | 'text'`) — ikisi üst üste
çizilince kare okunmaz hâle geliyordu.

**Tazelik:** tarama tek kare üzerinde yapılıyor ama görüntü akmaya devam ediyor,
yani çerçeveler çizildikleri andan itibaren gerçeklikten uzaklaşıyor. Kareyi
dondurmak kamerayı bozuk gösterirdi; çözüm çerçevelerin 6 saniyede solması.

## Alt zaman çizelgesi

> **Kaldırıldı (2026-10-29, kullanıcı isteği).** `Timeline.tsx` ve `timelineStore.ts` silindi;
> backend `task_started`/`task_finished`/`debug`/`reasoning` olaylarını yayınlamaya devam ediyor,
> arayüz artık dinlemiyor. Aşağısı tarihçe.

Araç çağrıları + `debug` logları tek kronolojik akışta. `task_started` /
`task_finished` olayları `events.py`'de tanımlıydı ama **hiçbir yerden
yayınlanmıyordu**; 2026-07-30'da `main.py._execute_tool` içine bağlandı.

Varsayılan **kapalı** — alt kenarda tek satırlık şerit, son olayı gösteriyor.
Sürekli açık duran bir log paneli sahnenin alt üçte birini yutardı.

Biten görev **kendi satırını güncelliyor**, yeni satır açmıyor. Şeridin "son
olay"ı bu yüzden dizinin sonu değil, `lastTouchedId` ile takip ediliyor.

### Muhakeme (2026-07-31)

Akışta üçüncü bir tür var: `reasoning` — modelin düşünme adımları. İtalik ve
beyin ikonuyla gösteriliyor, başlık satırı taşımıyor (her satırın üstüne
"Muhakeme" yazmak akışı ikiye katlardı; ayrımı ikon taşıyor).

Sonuç, görev satırlarıyla birlikte **nedensel bir iz** oluşturuyor:

```
🧠  Kullanıcı hava durumunu sordu, konum hafızada İstanbul.
✓   get_weather — İstanbul 24°, açık
🧠  Sonuç geldi; kısa bir cümleyle özetleyeceğim.
```

Veri `LiveConnectConfig.thinking_config` ile isteniyor ve `model_turn.parts`
içinde `thought=True` bayraklı parçalar olarak geliyor — normal metinle aynı
listede, bayrakla ayrışıyorlar. **Sohbete yazılmıyor:** sohbet Chiron'un
söyledikleri için, muhakeme ne söyleyeceğine nasıl karar verdiği.

Düşünceler transcript gibi parça parça akıyor. `_flush_reasoning` cümle
sınırında yayınlıyor: her parçayı tek tek yayınlamak akışı yarım kelimelerle
doldurur, `turn_complete`'e kadar biriktirmek ise muhakemeyi cevaptan SONRA
gösterirdi — oysa değeri cevaptan önce görünmesinde.

Modelin bu ayarı gerçekten desteklediği **canlı oturumda doğrulanmadı**
(bkz. `Docs/YAPILACAKLAR.md` #13).

## Uyku modu

Çekirdeğe tıklamak Chiron'u uyutuyor: ortam kararıyor, HUD çekiliyor, ağ soluk
iskelete düşüyor, çekirdek yavaş nefes almaya devam ediyor. Her yere tıklamak
uyandırıyor.

**Uygulama kapanmıyor, uyuyor** — çekirdek ekrandaki en büyük tıklama hedefi,
yanlışlıkla tıklamanın bedeli "oturumu kaybetmek" olmamalı.

Perde düz siyah değil, **merkezi açık** radyal gradyan; tam opak olsa uygulama
çökmüş gibi görünürdü.

## Sol panel modülleri

> **2026-10-29:** Hafıza, Otomasyon, Tarayıcı modülleri ve bildirim/profil düğmeleri kaldırıldı
> ("boş olan şeyleri kaldır, ayarlar ve ajanlar kalsın"). Sol panelde yalnız Ayarlar var;
> Ajanlar tam ekran ofis. Hafıza verisi hâlâ `backend/api/memory.py`'de. Aşağısı tarihçe.

- **Hafıza** — `memory.json`'ı doğrudan okuyor (`backend/api/memory.py`), yani
  ses döngüsü kapalıyken de çalışıyor. Salt okunur: silme Chiron'a söylenerek
  yapılıyor, çünkü `delete_memory` iki adımlı onay istiyor ([[Bellek-ve-Config]]).
- **Otomasyon** — aktif izlemeler ses döngüsünün belleğinde
  ([[Izleme-ve-Brifing]]), bu yüzden `commands.read_provider` üzerinden okunuyor.
- **Ajanlar / Tarayıcı** — bağlanacak veri yok, dürüst boş durum gösteriyorlar.

## Durum renkleri

Çekirdek konuşurken **turkuaz-yeşile** dönüyor (`three/palette.ts`,
`PLASMA_TEAL`). Beş ton karşılaştırıldıktan sonra seçildi; yeşilin en soğuk ucu
olduğu için buz mavisiyle aynı sıcaklıkta kalıyor ve `idle → speaking` geçişi
renk kavgası değil, aynı ailenin içinde bir kayma gibi okunuyor.

Palet **tek kaynak**: çekirdek, korona ve elektrik arkları hepsi oradan
besleniyor — ayrı yazılsalardı biri geride kalır ve yeşil çekirdeğin etrafında
mavi bir korona dönerdi.

**Arklar 2026-08-06'ya kadar bu kuralın yarısını çiğniyordu:** `ElectricArcs`
paletin kenar rengine YALNIZCA `speaking` (ve uykuda) çekiliyordu, karışım diğer
durumlarda 0'dı. Yani kehribar `automation` ve mor `memory` çekirdeklerin
etrafında arklar buz mavisi kalıyordu — kuralın önlemek için yazıldığı hatanın
ta kendisi. Görünmüyordu çünkü dolu plazma küre arkların yarısını örtüyordu;
çekirdek tel kafese dönüp arklar cismin içinden geçer olunca uyumsuzluk ekranda
apaçık ortaya çıktı. Karışım artık her durumda uygulanıyor (`CORE_COLOR_BLEND`).

## Tel kafes çekirdek

Çekirdek 2026-08-06'da (kullanıcı isteği) **dolu plazma küreden tel kafes
hologramına** geçti. Değişen geometri ve ışık modeli; davranış sözleşmesinin
tamamı — nefes, beş tepki, uyku, açılış zamanlaması, fare tepkisi, tıklayınca
uyuma — korundu.

Üç katman, dışarıdan içeri opaklık artıyor:

| Katman | Yarıçap / detay | Üçgen | Rol |
|---|---|---|---|
| Dış kafes | 1.62 / 1 | 80 | cismin sınırı — görünür ama bakılan şey değil |
| Orta kafes | 1.24 / 2 | 320 | dalgalanmayı (`uDistortion`) taşıyan katman |
| Çekirdek | 0.58 / 3 | 1280 | küçük ve yoğun: "içeride bir şey var" |

Katmanlar ters yönlerde ve farklı hızlarda dönüyor, eksenleri eğik — hepsi aynı
eksende dönseydi kesişim çizgileri sabit kalır ve moiré üretirdi.

**Detay seviyesi dolu küredekinin TERSİ mantıkla seçiliyor.** Dolu küre
detail=5 kullanıyordu (20480 üçgen) çünkü orada üçgenler görünmüyordu, yalnızca
yüzey pürüzsüzleşiyordu. Kafeste her üçgen çiziliyor. Toplam üçgen sayısı bu
yüzden 20480'den **1680'e düştü** (3 çizim çağrısı, 1 yerine).

### Ekrana bakarak düzeltilen üç şey

Tip kontrolü hiçbirini yakalamazdı (bkz. [[Bilinen-Tuzaklar]] § Bakarak doğrula):

1. **Kafes beyaza yıkanıyordu.** Fresnel kenar payı dolu küreden devralınmıştı
   (0.75). Dolu kürede o pay yalnızca ince bir silüet şeridini boyuyor; kafeste
   çizgilerin çoğu eğik olduğu için TÜM orb platin beyaz oldu ve buz mavisi /
   kehribar / mor ayrımı kayboldu. 0.45'e indirildi.
2. **Spiral spiral değildi.** İlk tasarımda üçüncü katman küreye sarılan tek bir
   çizgiydi (13 sarım). Önden bakınca spiral değil **yatay çizgi yığını** gibi
   okunuyordu — bir bobin, akan enerji değil. Yerine küçük ve sık bir kafes küre
   kondu.
3. **Arklar renk uyumunu bozuyordu** — yukarıdaki § Durum renkleri.

Ölçüm düzeneği: statik export'u 8000'den sunan sahte backend + gerçek WebSocket,
durumlar `/emit` ile test sürecinden tetiklendi, her durum için ekran görüntüsü.

### Beş tepki

Başlıkta tarih YOK bilerek: koddaki altı yorum `§ Beş tepki` diye atıf yapıyor,
başlığa ek koymak o atıfları kırar.

2026-07-31. Tasarım kuralı çekirdeğin beş şeye tepki vermesini istiyordu;
gerçekte **üçü** çalışıyordu. Her araç çağrısı `THINKING` yayınlıyordu, yani Chiron'un ekranı ele
geçirmesiyle hava durumuna bakması sahnede birebir aynı görünüyordu. `VISION`
ise `STATE_MAP`'te duruyor ama `main.py` hiç göndermiyordu — **ölü bir daldı**.

| Durum | Etiket | Renk | Hareket |
|---|---|---|---|
| `listening` / `speaking` | Dinliyor / Konuşuyor | buz mavisi / turkuaz-yeşil | nabız hızlanır, çekirdek büyür |
| `thinking` | Düşünüyor | buz mavisi, kısık | yavaş, sakin yüzey |
| `vision` | Görüyor | buz mavisi, parlak | türbülanslı yüzey |
| `automation` | **Uyguluyor** | kehribar (`SOLAR_AMBER`) | dönüş **2.4×**, yüzey pürüzsüz, hafif küçülme |
| `memory` | **Hatırlıyor** | mor (`DEEP_VIOLET`) | dönüş **0.4×**, derin nefes, dalgalı yüzey |

Kehribar seçildi çünkü kullanılmayan tek aile oydu — ama asıl gerekçe anlamsal:
kehribar her arayüzde "dikkat, makine hareket ediyor" demek. Chiron fareyi ele
aldığı an bunun **anında** fark edilmesi gerekiyor; bu dekorasyon değil uyarı.
Kırmızıya kaçılmadı, kırmızı "hata" der.

Renk tek başına yetmiyor: hız da bilgi taşıyor. Otomasyon sahnenin en hareketli
hâli, hafıza en durgunu. Göz ucuyla bakıldığında ya da renk körlüğünde ayrımı
taşıyan şey bu.

**Hangi araç hangi durumu tetikliyor:** `core/web_ui.py` → `state_for_tool`.
Ayrım okuma/yazma: `get_calendar_events` düşünme, `add_calendar_event`
otomasyon. Liste **beyaz liste** — adı geçmeyen araç `thinking`e düşüyor, yani
yeni bir araç eklenip yazılmazsa davranış bugünküne eşit olur, sessizce yanlış
bir durum göstermez. Kapsamlı eşleme zorunlu tutulsaydı araç eklemenin maliyeti
beşinci bir dosya olurdu.

**Ölçüm** (kaydırılmış çekirdek pikselleri, en parlak %15): otomasyon 33° ton,
hafıza 257°, geri kalan her şey 161-219° arasında. Hafızanın en yakın komşusuna
uzaklığı 38°. İlk denemede kenar rengi `#ece4ff` idi ve doygunluk %15'e
düşüyordu — fresnel kenarı parlak piksellere hâkim olduğu için mor durum
sahnenin en soluk hâli oluyordu. Kenar mora boyanınca %22'ye çıktı.

## Sol ray

> **Kaldırıldı (2026-10-29).** Yerine sol altta iki düğmelik cam çubuk; aktiflik hattı düğmenin
> altında. `railHoverStore` ve imzanın geri çekilmesi gereksizleşti, silindi. Aşağısı tarihçe.

Sadece ikon, hover olmadıkça etiket yok. Aktiflik göstergesi rayın **sol
kenarında** kayan ince bir hat (`layoutId` ile modüller arasında akıyor).

**Hover büyümesi (2026-07-31):** düğme `1.08` ölçekleniyor — 40 px'de ~3 px,
hissedilen ama ölçülmesi zor. `active:scale-95` de eklendi: büyüme varsa
basmanın da karşılığı olmalı, yoksa düğme hover'da canlı, tıklamada ölü.

Bunun için `RailButton`'ın yapısı değişti: **aktiflik hattı ve etiket balonu
artık butonun DIŞINDA**, saran kutuda. İkisi de içeride kalsaydı ölçekle
birlikte büyürlerdi — `layoutId` ile animasyonlu hat, ölçeklenmiş bir kutuda
ölçüldüğü için modül değişiminde yanlış konuma akardı; etiketteki 11 px yazı
da oynardı. Doğrulandı: hover'da buton 40 → 43.2 px, etiket `scale: none` ve
11 px, hat 2×20 sabit.

**Etiket çakışması — çözüldü (2026-08-01).** Ray etiketi ile sol üstteki CHIRON
imzası aynı yerde çiziliyordu (ilk düğmede 19×9 px; imzaya ambient bağlam satırı
eklenince 37×30 px'e çıktı). Her ikisi de kendi bileşeninde yaşadığı için
biri diğerinin varlığını bilmiyordu.

Elenen alternatifler: imzayı **sağa** itmek "Otomasyon" gibi uzun etiketlerde
yine çakışıyor; **aşağı** itmek ikinci düğmenin etiketine denk geliyor; rayın
üstüne **boşluk** koymak rayın başında koca bir delik bırakıyor.

Seçilen yol `stores/railHoverStore.ts`: raya yaklaşınca imza %15 opaklığa
çekiliyor. Bu bir kaçamak değil, kasıtlı bir etkileşim — aynı anda iki şeyin
dikkat istemesi yerine o an bakılan şey kazanıyor. Ölçüldü: hover'da imza 0.15,
etiket 1.0; hover bitince imza 1.0.

`onMouseLeave` koşulsuz `null` yazmıyor: bir düğmeden komşusuna geçerken
tarayıcı `leave(A)`/`enter(B)` sırasını garanti etmiyor, `leave` sonra gelirse
imza B'nin üstündeyken geri parlardı. Yalnızca hâlâ kendisi yazılıysa temizliyor.

## Sohbet kaydırma

`ConversationLog.tsx`. Üç kural:

1. **Açılışta** doğrudan en alta atlar (animasyonsuz — kayarak inmesi gereksiz
   gösteri olurdu). `hasJumpedToLatest` ref'i ile, panel her açılışta yeniden
   mount edildiği için sıfırlanıyor.
2. **Kullanıcının kendi mesajı** her zaman alta çeker, yukarıda bir şey
   okuyor olsa bile — mesajı gönderen onu görmek ister.
3. **Diğer mesajlar** yalnızca kullanıcı zaten dipteyse kaydırır; yukarı
   kaydırıp bir şey okuyorsa rahatsız etmez.

### "Dipte miyim" ölçümü ÖNCEDEN yapılmalı

Kullanıcı bildirdi (2026-08-01): *"msj atıyorum altta kalıyor."*

Hata şuydu: alta olan mesafe `useEffect` içinde, yani **yeni satır DOM'a
girdikten sonra** ölçülüyordu. O anda ölçülen şey "kullanıcı alta ne kadar
yakındı" değil, tam olarak **yeni eklenen içeriğin yüksekliği**:

```
mesafe = (H + yeni) - (H - clientHeight) - clientHeight = yeni
```

Kısa bir satır (~40px) `< 80` eşiğini geçtiği için kaydırma çalışıyor, uzun
bir cevap 80px'i aştığı için **çalışmıyordu**. Panel `max-h-56` (224px)
olduğundan bu çok kolay oluyor — yani hata mesaj uzadıkça ortaya çıkıyordu.

Çözüm: dipte olup olmama `onScroll` olayında, yani **içerik eklenmeden önce**
ölçülüp `isPinnedToBottom` ref'inde tutuluyor. Efekt artık geçmişteki bu
değere bakıyor, yeni içerikten etkilenen bir hesaba değil.

Ölçüldü (224px panel, ~420 karakterlik cevap): dipteyken uzun mesaj görünür,
yukarı kaydırılmışken kendi mesajı alta çekiyor, başkasının mesajı `scrollTop`
0'da bırakıyor.

## Tepsi konuşma göstergesi

`core/speaking_overlay.py`. Chiron tepsiye alındığında pencere görünmüyor, yani
konuştuğunu anlamanın hiçbir görsel yolu kalmıyordu. Artık sağ üstte küçük bir
ses dalgası çıkıyor, susunca kapanıyor.

### 2026-11-01: gerçek saydam göstergeler (`core/tray_indicator.py`)

İlk deneme: ana sahnenin 3D çekirdeği ikinci bir pywebview penceresinde. WebView2'de gerçek saydamlık alınamadı
(pywebview `transparent` beyaz zemin + her yüklemede odak çalıyor; LWA_COLORKEY WebView2'ye uygulanmadı), daire
bölgesiyle kesilince sert kenarlı koyu bir küre çıktı — Yunus "çok kötü" dedi, kaldırıldı. 15 taslak gösterildi
(artifact DG2Z8UCzQVK7mzUzNT3W3r); seçilenler 07 parçacık, 08 kayan kart, 10 imleç arkadaşı, 12 osiloskop, 15 2D çekirdek.

- **Win32 katmanlı pencere + UpdateLayeredWindow:** kare numpy ile önceden çarpılmış BGRA → kenar, ışıma, gölge
  gerçekten saydam. WS_EX_TRANSPARENT (tıklama geçer) + NOACTIVATE + TOOLWINDOW + TOPMOST. Pencere, mesaj
  döngüsü ve çizim tek iş parçacığında. 64 bit tanıtıcılar için tüm GDI/User32 argtypes tanımlı — yoksa
  `OverflowError: int too long` (yaşandı).
- **Işık modeli:** parlak öğeler renk*yoğunluk olarak toplanır, alfa da yoğunluk kadar artar; kart (08) normal
  PIL bileşimi. 2x çizip küçültme = kenar yumuşatma (PIL çizgileri yumuşatmasız).
- **Ölçüldü (150 px, %125):** kare başına parçacık 3.3 ms, kart 5.7, imleç 0.3, osiloskop 2.1, çekirdek 4.6; 40 FPS.
- **Seçim:** `config` → `tray_indicator`: `parcacik | kart | imlec | osiloskop | cekirdek` (varsayılan cekirdek) ya da
  `dalga` (eski Tk). 2 sn'de bir okunur, değişince anında geçer. Kart, Chiron'un o an söylediğini gösterir
  (`push_caption`, main.py çıkış transkripti; 3 sn sessizlikte yeni cümle).
- **Deneme:** `venv\Scripts\python.exe -m core.tray_indicator --demo [stil...]` beşini 9'ar sn simüle konuşmayla
  gerçek ekranda oynatır. Kilit ekranında ilk deneme: pencere görünür/stil/konum doğru, beşi hatasız döndü; gözle
  bakış Yunus'ta.
- **Evreler (aynı gün, Yunus: "konuşma başlamadan belirsin, sonra biraz durup gitsin, beni dinlerken de
  görünsün"):** `dinliyor` (giriş transkripti, 1.2 sn; dalgalanma mikrofondan) → `dusunuyor` (kullanıcı sustu ve
  cevap yok, en fazla 12 sn; ya da araç çalıştı, 4 sn) → `konusuyor` → `bitti` (3 sn, yarı parlaklıkta söner).
  Renk evreye göre: ICE / DEEP_VIOLET / PLASMA_TEAL (çekirdekle aynı). Kullanıcı konuşması ham mikrofondan değil
  transkriptten anlaşılıyor — oda gürültüsü göstergeyi açmasın. Varsayılan stil artık `parcacik` (07); 15 seçenek.

**Yalnızca tepsideyken.** Pencere açıkken gereksiz — çekirdek zaten konuşurken
turkuaza dönüyor ([[Arayuz]] § Beş tepki). İki gösterge aynı anda aynı şeyi
söylerse biri gürültü olur.

**Dalga GERÇEK sesten besleniyor.** Süsleme amaçlı bir döngü değil: çubuklar
`_play_audio` içindeki PCM parçasının genliğinden geliyor (`_mic_level` ile,
mikrofonla aynı hesap — çıktı da 16-bit mono). Chiron susunca düzleşiyor,
yüksek sesle konuşurken yükseliyor. Sahte bir animasyon, bağlantı koptuğunda
da neşeyle oynamaya devam ederdi ([[Bilinen-Tuzaklar]] § Arayüzde dürüstlük).

Görüntü kaydırmalı: en yeni değer sağda, geçmiş sola akıyor — sabit bir
ekolayzer değil, "az önce ne söyledi"nin izi.

### Tkinter neden geri geldi

Tkinter arayüzü 2026-07-29'da **bilerek silinmişti** ([[Home]] § Kaldırılan):
Canvas gerçek blur/bloom üretemediği için orb'u yaklaşık çiziyordu ve CPU'yu
tek çekirdekte ~%100 yakıyordu.

Buradaki iş o değil. 14 dikdörtgenin yüksekliğini saniyede 25 kez güncellemek
Canvas'ın zorlanmadan yaptığı bir şey. Karar "Tkinter kötüdür" değildi,
"shader kalitesinde bir sahneyi Canvas ile taklit etmek kötüdür"di.

**Elenen alternatif:** ikinci bir pywebview penceresi. HUD'la görsel olarak
tutarlı olurdu ama küçücük bir gösterge için ayrı bir WebView2 örneği
(~50-150 MB) açmak gerekiyordu; bellek profili zaten ~1.25 GB
([[Kurulum-ve-Baslatma]]).

`tkinter` **tembel import**: modül açılışta değil, gösterge ilk kez
etkinleştiğinde yükleniyor — Chiron tepsiye hiç alınmazsa hiç yüklenmiyor
([[Bilinen-Tuzaklar]] § Ağır Python import'ları tembel olmalı).

### İş parçacığı kuralı

Tk kendi thread'inde yaşıyor ve Tk nesnelerine **sadece o thread** dokunuyor.
Dışarıdan gelen `set_speaking`/`push_level` kilitli bir duruma yazıyor, Tk
döngüsü onu `after()` ile okuyor. Widget'lara başka thread'den dokunmak
Windows'ta sessiz donmalara yol açıyor.

Ölçüldü: tepside değilken görünmüyor, tepsideyken sessizken görünmüyor,
konuşurken çıkıyor, bitince kapanıyor.

## Ambient bağlam satırı

`BrandBadge`'in üçüncü satırı: **CHIRON → durum → kullanıcının ne yaptığı.**
Durum satırından bir kademe daha kısık, çünkü bu Chiron'un değil kullanıcının
ne yaptığı — aynı vurguyla yazılsaydı ikisi tek cümle gibi okunurdu.

Kaynak `GET /api/system/context`, `get_context` aracını besleyen fonksiyonun
**aynısı** — ayrı yazılsalardı biri bayatlar ve arayüz olmayan bir farkındalığı
varmış gibi gösterirdi. Okunamazsa satır hiç çizilmiyor.

Ayrıntı: [[Ambient-Baglam]].

## Telemetri şeridi

Tepsi düğmesinin yanında tek satır: **CPU · RAM · Disk · Pil · İnternet · Saat**
(286×38 px, yatay taşma yok).

İnternet **gerçek**: backend 1.1.1.1:53'e TCP bağlanıp süreyi ölçüyor
(`backend/api/system.py` → `_probe_internet`). `psutil.net_io_counters`
kullanılmadı — o yalnızca arayüzden kaç bayt geçtiğini söyler, kablo takılı ama
internet yokken de artar, yani "bağlı" demek için yanlış ölçüt.

Detaylar:

- Sonda **asenkron** (`asyncio.open_connection`). Bloklayan bir soket, 1.5 sn
  boyunca olay döngüsünü ve onunla birlikte tüm WebSocket yayınlarını dondururdu.
- **15 sn önbellek** — kart 3 sn'de bir sorguluyor, her sorguya bir TCP el
  sıkışması bindirmek gereksiz.
- Gecikme **en az 1 ms** gösteriliyor. Ölçüm bir kez 0'a yuvarladı; "0ms"
  ekranda "kusursuz bağlantı" diye okunurdu, oysa hiçbir el sıkışması 0 sürmez.
- **Uyarı:** bu sayı "1.1.1.1'e bağlanma süresi", internet kalitesinin tamamı
  değil. Şeffaf vekil/güvenlik duvarı olan ağlarda SYN'i o cihaz yanıtlar ve
  süre gerçekte olduğundan iyi görünür. Ulaşılabilirlik için doğru, hız testi
  için değil.
- Çevrimdışıyken alan **gizlenmiyor**, üstü çizili ikon + "yok" gösteriliyor.
  GPU/sıcaklıktan farkı bu: onları ölçemiyoruz, bunu ölçebiliyoruz ve cevap
  "hayır" — bu bir eksiklik değil, bilgi.

Saat dakika başına **hizalı** uyanıyor (`setInterval(1000)` değil): gösterilen
değer dakikada bir değişiyor, saniyede bir render etmek 59 boş render demekti.
Sahne 60 FPS hedefliyor, aynı ana iş parçacığında boş render biriktirilmez.

## Kare hızı — ölçüldü

`three/FrameProbe.tsx` kalıcı bir sonda: kare başına tek `Float32Array` yazması,
ayırma yok. `window.__chironFps()` ile okunuyor, `window.__chironFpsReset()` ile
sıfırlanıyor.

**Ölçüm (2026-07-31, gerçek WebView2 penceresi, 1540×844 @ 1.25 DPR, 144 Hz):**

| | En yoğun¹ | Sade (yalnızca sahne) |
|---|---|---|
| Gerçek ortalama FPS | **68.8** / **77.6** | 74.5 / 76.7 |
| Kare süresi p50 | 14.3 / 12.8 ms | 13.0 / 12.9 ms |
| p95 | 18.8 / 15.9 ms | 16.3 / 16.5 ms |
| En kötü kare | 32.2 / 24.3 ms | 23.3 / 26.1 ms |
| 16.7 ms bütçesini aşan | %15.6 / %2.9 | %3.4 / %4.4 |

¹ vision durumu + 8 FPS webcam karesi + 8 tespit çerçevesi + tüm paneller açık.
İki bağımsız tur, ikisi de kendi içinde tutarlı (ortalama ≈ ortancadan türetilen).

**Sonuç: 60 FPS hedefi tutuyor** — en yoğun hâlde bile ~69-78 FPS, ortanca kare
14 ms civarı, bütçe 16.7 ms. Ama pay sanıldığı kadar geniş değil: ekran 144 Hz
(6.94 ms) ve sahne onu yakalayamıyor, kareler iki vsync aralığına oturuyor.
Yani gerçek iş süresi 7-14 ms arasında bir yerde; vsync kuantalaması yüzünden
daha kesin söylenemez.

### Uyarlanır kare hızı (2026-10-02)

Yukarıdaki ölçüm "60'ı tutuyor mu" sorusuydu. Faz 0'ın sorusu tersi: **gerekmediğinde
ne kadar çiziyor?** Cevap: boşta bile ekran tazeleme hızında — 144 Hz ekranda 111 FPS,
WebView2 GPU süreci 3D motoru %69,5. Kimse bakmazken ve hiçbir şey olmazken.

`three/FrameGovernor.tsx` + `Canvas frameloop="demand"`:

| Durum | FPS |
|---|---|
| Açılış sahnelemesi (ilk 9 sn), Chiron dinliyor/düşünüyor/konuşuyor, fare/klavye girdisi (2,5 sn tutar) | 60 |
| Boşta, pencere odakta | 30 |
| Pencere odakta değil | 20 |
| Uyku perdesi | 15 |

Sonuç (görünür Edge, gerçek GPU, 45 sn boşta): GPU %69,5 → **%22,5**, tarayıcı CPU %5,7 → %2,7.

- **Birikimli zamanlama şart.** İlk sürüm "son kareden beri ≥ 1000/hedef" diyordu; 144 Hz'de
  vsync aralığı 6,94 ms olduğu için 60 hedefi üç vsync'e (20,8 ms) yuvarlanıp **48 FPS**
  oluyordu. Şimdi bir sonraki kare zamanı `son + aralık`, uzun vadede ortalama tam hedef.
- **Bütün useFrame'ler zamana bağlı olmalı** (`delta` / `elapsedTime`). 2026-10-02'de hepsi
  kontrol edildi. Kare başına sabit artış yapan yeni bir animasyon, düşük FPS'te yavaşlar.
- Tanı: `window.__chironGovernor()` → `{rule, target, ticks, requested}`. FrameProbe artık
  gerçek çizim hızını ölçüyor — boşta ~30 görmek beklenen, hata değil.
- İlk denemede bir kez boşta 0,5 FPS görüldü; kök nedeni kesinleşmedi, birikimli zamanlama +
  tanıdan sonra tekrar etmedi. Gerçek pencerede `__chironGovernor()` ile doğrulanmalı.

## İnsan görünümü

2026-11-01, Yunus'un isteği (Instagram'daki "Opening Humanoid view" referansı): **çift parmak
şıklatması** (ya da arayüzde **H**; **Esc** çıkar) çekirdeği parçacıklardan bir insansı robota çeviriyor.

- **Biçim: "Krom"** (2026-11-02). İlk sürüm elipslerden çizilmiş bir büsttü, Yunus "güzel olmamış" dedi.
  Sonra 3 tur taslak yapıldı (10 soyut/robot, 10 film/anime esinli, 6 insansı). Yunus "insansı robot"
  dedi ve 6 insansıdan Krom'u seçti. Taslaklar: claude.ai/artifact/3bzbjjjnmGMq5J8L9fJaob (ilk iki tur),
  claude.ai/artifact/SnG67xU7wjc5PxP5gp3v9s (insansı; diğer beşi Kontur/Ava/Siborg/Neon/Altın orada duruyor).
- **Kafa elle çizilmiyor:** gerçek kafa taraması (`public/models/head-scan.glb`, Lee Perry-Smith, **CC BY 3.0**,
  three.js örnek modeli — lisans `head-scan-LICENSE.txt`, atıf satışa/yayına çıkarken gerekli) yüzeyinden
  150k nokta örnekleniyor (`three/humanoidKrom.ts`, MeshSurfaceSampler). Tarama yalnız mod ilk açılınca iniyor.
- **Tuzak:** taramada ağız boşluğu gibi iç yüzeyler var; ışıkla toplanınca ağzın çevresinde parlak bir kutu
  çıkıyordu. Önden ızgarada dış yüzeyin 0.12 gerisinde kalan örnekler atılıyor.
- **Krom:** ışıkla gölgelenmiş gümüş (sol üst önden ışık — heykel gibi okunmasını sağlayan bu), mavi panel
  dikişleri (alın ortası, alın bandı, çene hattı, boyun halkaları), buz mavisi gözler, göğüste turuncu çekirdek.
  Aynı geometri iki kez çiziliyor: normal + 3.4 kat büyük soluk parlama geçişi (ucuz bloom).
- **Canlı:** kafa+boyun imleci izliyor (omuz sabit, pivot boyunda), 2.5–6.5 sn'de bir göz kırpıyor,
  konuşurken çene açılıp kapanıyor ve gözler/dikişler parlıyor, dinlerken mikrofona tepki.
- **Akış:** çekirdek sönerken sürü fışkırıyor, aşağıdan yukarı toplanıyor (3 sn, kapanış 1.8 sn). HUD çekiliyor;
  altta kısa duyuru, sonra sönük ipucu. Ses: WebAudio sentezi (`playMaterialize`), SFX ayarına uyuyor.
- **Şıklatma** `core/snap_detector.py` (numpy, model yok): ani atak (+15 dB), tiz (fark enerjisi oranı),
  ~50 ms'de sönüp yeniden yükselmeme. Konuşma ve masa vuruşu testte elenir; **alkış da tetikler**.
  Chiron konuşurken ve uzak modda kapalı; susturulmuş/duraklatılmışken açık (ses dışarı gitmiyor).
  Ayar `snap_gesture`: `false` kapalı, `1` tek şıklatma, varsayılan `2`.
- **Durum** backend'de (`web_ui.humanoid`, `assistant_status` anlık görüntüsünde). `POST /api/voice/humanoid {value}`.
  İlerleme kare başına `humanoidProgress` düz nesnesinde (store değil).
- **Henüz yok:** webcam ile yüz takibi (şimdilik imleç), sesli komutla açma aracı. Şıklatma eşikleri sentetik
  sesle ayarlandı — gerçek mikrofonda sorun olursa `[SNAP]` debug loguna bak.

## Oturum yörüngeleri ve Gözetim

2026-11-04. Kaynak fikir: Atalay Karahan'ın açık kaynak "Atalay's Terminal"i (Claude Code oturumları
yörünge haritasında). Taslak: claude.ai artifact `VEkhnxY622pqRZgHnXPNuM` (6 ekran).
Kullanıcı isteği: **"şu anki yörüngeme, o animasyonuma dokunma; yanlarına onun gibi küçük ve farklı
renkte yörüngeleri diz, sonra bu arayüzü yap."**

**Ana sahne — `three/SessionOrbits.tsx`.** `EnergyCore.tsx` değişmedi. Her canlı şef oturumu (officeStore,
`office_update`) iki katmanlı küçük bir tel kafes çekirdek: aynı shader'lar, oturumun kendi tonunda.
- Renk = **hangi oturum** (`gozetimApi.hueMap`: kimliğin kendi tonu, alınmışsa sıradaki boş ton — iki canlı
  oturum aynı renge düşmez). Buz mavisine yakın camgöbekleri listeden çıkarıldı: ana çekirdekle karışıyordu.
- Durum = **hareket**: çalışıyor tam parlak · onay bekliyor nabız + kehribar halka · boşta kısık ve yavaş.
  Alt ajanlar uydu noktaları.
- Yörünge **ekran düzleminde** basık bir elips (`ORBIT_SQUASH`). İlk deneme derinlikteydi ve küçük çekirdek
  ana çekirdeğin önünden geçip onu örtüyordu (ekran görüntüsünde yakalandı).
- Hepsi **ortak bir çark** (`wheelAngle`, `performance.now()`), eşit aralıklı. Önce her biri kendi hızındaydı,
  ikisi üst üste biniyordu. Sayı değişince yerine sönümle kayar.
- 6 saattir olayı olmayan oturum gösterilmez (SessionEnd gelmeyebiliyor; `STALE_S`, backend'de de aynı).
- Tıklama → Ofis › Gözetim, o oturumun detayı açık.

**Komuta › görsel ekleri (2026-11-04).** Yazı alanında resim düğmesi; Ctrl+V ile yapıştırma ve sürükle-bırak da
çalışır. En fazla 4 görsel, 8 MB, PNG/JPEG/GIF/WebP (tür içerikten anlaşılır, uzantıdan değil). Görseller gönderilirken
`POST /api/sohbet/{id}/ek` (base64) ile `config/sohbet_ekler/<sohbet>/` altına yazılır (gitignore'da); mesaj ek adlarını
taşır, göreve dosya yolları eklenir, Claude'a `--add-dir`, Gemini'ye `--include-directories` ile o klasör açılır.
Balonda küçük resim, tıklayınca tam boy (`GET .../ek/{ad}`). Sohbet silinince/budanınca ekleri de silinir.
Yalnız metinsiz görsel gönderilirse metin "Ekteki görsele bak." olur.

**Ana ekran Chiron sohbeti › görsel ekleri (2026-11-04).** Dock'taki Sohbet panelinde (`VoicePanelContent.tsx`) aynı
düğme/yapıştır/sürükle. `POST /api/voice/text` `{text, images: dataURL[]}` → görseller `config/sohbet_ekler/sesli/`'e
(son 40 tutulur) → `main._on_text_command` aynı turda `inline_data` part olarak Gemini Live'a yollar. Chiron o turdan
sonraki 10 dk içinde `delegate_to_pc` çağırırsa `pc_isi` görsel ADLARINI `/api/remote/komuta`'ya geçer, `phone_task`
onları Komuta sohbetinin klasörüne kopyalar (yol değil ad gelir — uzak istemci keyfi dosya okutamaz). Ortak yardımcı
`services/imageAttach.ts`. Telefon web arayüzündeki (/m) kutuda görsel yok.

**Ofis › Gözetim — `components/office/gozetim/`.** Backend `backend/core/gozetim.py`, uç `GET /api/office/gozetim`
(3 sn'de bir). Yerleşim: üst sayı şeridi · sol oturum kartları (bağlam doluluğu, 30 dk aktivite, model, maliyet,
"DÖNGÜ?" = son 24 izde ≥5 hata) · orta **Yörünge** (kendi küçük Canvas'ı, 30 FPS; ofis açıkken ana sahne durduğu
için tek WebGL) ya da **Şerit** (son 30 dk, araç başına bir iz) · sağ araştırma, sıcak dosyalar (iki oturum aynı
dosyaya yazınca ÇAKIŞMA), araç karışımı · alt canlı akış, alt ajanlar, harcama, senin sıran. Karta tıklayınca
detay: akış, alt ajanlar, yazılan dosyalar, **Son cevabı kopyala** (kayıttan, ekrana sığmayan dahil) ve
**Komuta'da sürdür** (`sohbet.takeover`; terminalde açıksa ikinci tıklamayla).

Veri: oturum/araç/onay/araştırma/dosya ısısı `ofis.py` hook olaylarından (`tool_category`, `_radar`,
`Worker.marks`); token/bağlam/model/maliyet şefin Claude Code kaydından (`transcript_path`), artımlı okuma,
yanıt kimliğine göre teke indirme (bir yanıt içerik bloğu başına ayrı satır). **Maliyet API liste fiyatıyla
eşdeğer** — abonelikte ödenen bu değil; fiyatı bilinmeyen model `?`/`+`. Fiyatlar `PRICES` (claude-api
referansı, 2026-10-06), önbelleğe yazma 5 dk ×1.25, 1 sa ×2.

**Kaçak süreç bandı:** psutil — sahibi ölmüş geliştirici süreci (node/python/…) 2 dk boyunca bir çekirdeğin
%50'sini yakıyorsa ya da port tutuyorsa. Chiron'un kendisi, ataları, çocukları hariç. Sonlandırma yalnız tıkla,
aynı pid + aynı başlangıç zamanı doğrulanır, bütün alt ağaç (TaskStop alt süreçleri bırakıyordu).

Gözetim'in yörünge paneli (aynı gün, kullanıcı isteği): zemin düz siyah, iki katman tohumlu yıldız alanı
(1400 sönük + 160 parlak, yarıçap 18–34 — döndürünce çekirdeğin önüne düşmesin), **fareyle döndürme**
(drei `OrbitControls`: kaydırma kapalı, yakınlaşma 6–18, dikey açı sınırlı). Sürükleme küçük çekirdeğin
üstünde biterse tıklama sayılmaz (`e.delta > 4`). Playwright'ta sürükleyip ölçüldü: görüş değişti, detay açılmadı.

Ekrana bakarak düzeltilenler: alt şerit grid satırı kayınca eziliyordu (flex sütuna geçildi) · şerit izi
`span` olduğu için 0 px'ti ve `<button>` içindeki grid sütunu genişlemiyordu (satır div, ad düğme).

**Yörünge ekleri (aynı gün, Yunus dördünü de seçti):** veri `GET /api/office/gozetim/yorunge` (`orbit_view`,
5 sn, `stores/orbitStore.ts` — iki sahne tek yoklayıcı).
- Etiketin ikinci satırı: oturumun şu an / en son ne yaptığı (`doing()`; onay bekliyorsa hangi araç, kehribar).
- **Araç kıvılcımı:** oturum (şef + alt ajanları) her araçta küçük çekirdekten Chiron'a kavisli bir ışık; rengi araç
  türü (`last_cat`, `CAT_COLOR`). Sayaç anlık görüntüden (`syncToolStats`), ilk karede geçmiş için patlama yok.
- **Bağlam halkası:** küçük çekirdeğin çevresinde doluluk yayı, %80'de kehribar.
- **Uydular:** arka plana atılan shell komutları (`ofis.bg_jobs`, bitişi task-notification'dan) beyaz tel elmas;
  oturumun klasöründe port dinleyen dev sunucusu nane dolu elmas + `:port`.
- **Kaçak süreç meteoru:** dış yörüngede kuyruklu kızıl taş; tıklama Gözetim'i açar, sonlandırma orada (sahneden yok).
- Kare döngüsünde değişen her şey `ref`'te, tamponlar JSX `<bufferGeometry>` + points ref üzerinden
  (React Compiler `useMemo` değerini değiştirmeye izin vermiyor).

**Onay:** yörüngede/kuyrukta onay bekleyen oturuma tıklayınca detayın üstünde **onay terminali** — ayrıntı
[[Onay]]. Ses: `answer_approval`.

Yapılmayan: telefondaki özet (taslak F).

## Onay merkezi (ana ekran)

2026-11-04, kullanıcı isteği: Komuta'daki "Senden bekleyenler" ana ekranda da görünsün, tıklayınca
pencere açılsın, birleştirme oradan yapılsın. `components/onay/OnayMerkezi.tsx` + `app/onay.css`.

- Kutu sağ kolonda Vision'ın altında, **yalnız bekleyen varsa** görünür (6 sn'de bir `/api/pano` +
  `/api/sohbet`, sekme gizliyse yoklamaz). Birleştir/onay kartları ve onay bekleyen sohbetler.
- Kart → pencere (portal, z 70): ne yapıldı, test (çıktı açılır), dosya/satır sayısı, bekçi uyarıları,
  dosya listesi + diff (`GET /api/pano/{id}/changes`, `pano.changes` → `pano_git.diff_files/diff_patch`,
  400k karakterde kesilir). Dosyaya tıklayınca diff o dosyaya kayar. "Ana dala al" / "Reddet" (reddet
  iki tık: kopya silinir, dal kalır). Çakışmada backend başarı döner ama kart `hata` olur — pencere
  kapanmaz, hatayı gösterir. Esc / dışa tık kapatır (iş sürerken değil).
- Sohbet satırı pencere açmaz, Komuta'da o sohbeti açar (onay Claude oturumunda verilir).
- Boyut (aynı gün, "küçült" isteği): 760 px genişlik, en çok 640 px yükseklik; özet iki satır ("Tamamı" açar), diff 260 px (kısa ekranda 200).

## Küçük parçalar

- **Ses dalga formu** — veri tarayıcıdan değil backend'den (`mic_level`, ~12 FPS).
  `getUserMedia` ile ikinci bir mikrofon akışı açmak pyaudio ile yarışırdı;
  seviye Chiron'un gerçekten duyduğu ham PCM'den hesaplanıyor.
- **Telemetri** — CPU/RAM/Disk/Pil. GPU ve sıcaklık **yok**: Windows'ta psutil
  ikisini de güvenilir vermiyor, uydurmak yerine hiç gösterilmiyor.
- **Think.mp3** — durum bazlı döngü (tek atış değil), %35 seste.
- **Tepsiye al** — ayarlar panelinden çıkarıldı, sağ üstte sabit kontrol.
- **İkon** — `make_icon.py` prosedürel üretiyor; 16px ve 256px için **ayrı
  çizim** (tek görseli küçültmek 16px'te lapa üretiyordu).
- **Duraklat** — arayüzde **düğmesi yok**. Zincirin geri kalanı tam: uç
  (`POST /api/voice/pause`), köprü (`web_ui.on_pause_toggle`), çekirdek
  (`main.py` `_paused` — mikrofonu ve araç çağrılarını durduruyor), hatta
  durumun soketten dönüşü (`assistant_status`). Yalnızca kullanıcının
  basacağı şey eksik; `services/voiceApi.ts` içindeki `setPaused` bu yüzden
  hiçbir yerden çağrılmıyor. Sessize alma (mute) düğmesi `AssistantDock`'ta.

## Doğrulama notu

Arayüz Playwright ile test ediliyor. Tercih edilen düzenek: statik export'u
8000 portundan sunan **sahte bir backend** ve gerçek bir WebSocket — böylece
Pydantic zarfı ve arayüzün ayrıştırıcısı da yolun içinde kalıyor. Soketi sahte
bir sınıfla değiştirip olay enjekte etmek backend'i atlıyor.

Ayrıntı ve tuzakları için [[Bilinen-Tuzaklar]] § Arayüzü nasıl test ediyoruz.
