---
tags: [chiron, arayuz]
---

# Arayüz — frontend/ (Next.js + Three.js)

Bağlı: [[Home]] · [[Mimari]] · [[Kurulum-ve-Baslatma]] · [[Nesne-Tanima]] · [[OCR]] · [[Izleme-ve-Brifing]] · [[Bellek-ve-Config]]

3D sahne + üzerinde yüzen cam paneller. Tasarım kuralları `CLAUDE.md` içinde;
kalan işler `Docs/CHIRON_UI_ROADMAP.md`. Bu not **ne yapıldığını ve neden öyle
yapıldığını** özetliyor.

## Yerleşim

| Konum | Ne var |
|---|---|
| Sol üst | CHIRON imzası + canlı durum (`BrandBadge.tsx`) |
| Sol, imzanın altı | Ayarlar paneli (`LeftPanel.tsx`) |
| Sol alt | Ajanlar + Ayarlar düğmeleri (`Sidebar.tsx`) — sohbet dock'unun aynası |
| Sağ üst | Telemetri şeridi + tepsi düğmesi (aynı satır) |
| Sağ | Vision paneli, altında düğüm odak kartı |
| Sağ alt | Sohbet dock'u (`AssistantDock.tsx`) |
| Orta | 3D sahne (`three/Scene.tsx`) |

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
