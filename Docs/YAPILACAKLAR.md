# Chiron — Yapılacaklar

**Vizyon (2026-07-26):** Chiron sadece "sesli asistan" değil — Iron Man'deki Jarvis gibi
ortamı sürekli/proaktif algılayıp gerektiğinde kendiliğinden harekete geçen bir sistem
olacak. Aşağıdaki maddeler bu hedefe giden adımlar; **tek tek** yapılacak, her biri
bitip test edilip onaylanınca bu dosyadan silinecek.

---

## 3. El hareketi tanıma ile masaüstü kontrolü
Görüntü işleme ile eli algılayıp, el hareketleriyle masaüstündeki dosyaları
açma/kapama gibi işlemler yapabilme ("ve daha fazlası" — genişleyebilir).
**Şimdilik ertelendi** — sırada değil, ileride dönülecek.

**Referans (2026-08-06):** `SAGAR-TAMANG/ultron-by-sagar-builds` (MIT) aynı
işi tarayıcıda **MediaPipe Hands** ile yapıyor — `lib/handTracker.ts`, kıstırma
(pinch) hareketiyle 3D orb'u döndürüyor/yakınlaştırıyor. O depoda YALNIZCA
arayüz var (Next.js + Three.js); ses ve cihaz kontrolü tarafı açık değil.
Bizim için değerli olan kısım el algılamanın yeri: tarayıcıda, zaten açık olan
kamera akışı üzerinde, Python'a hiç uğramadan. Asıl iş bundan sonrası —
hareketi masaüstü eylemine çevirecek köprü (WebSocket → araç çağrısı), ki o
depoda karşılığı yok.

## 5. Proaktif takvim/hatırlatıcı bildirimi
**Şimdilik ertelendi** (2026-07-26) — gerçek engel bulundu: Windows'taki
`get_calendar_events`/`get_reminders` gerçek veri OKUMUYOR, sadece tarayıcıda
Google Calendar/Microsoft To-Do açıyor (macOS'un EventKit entegrasyonu Windows'a
hiç taşınmamış). Proaktif bildirim için önce Google Calendar API + (muhtemelen)
Microsoft Graph API ile gerçek OAuth entegrasyonu gerekiyor — bu kullanıcının da
tarafında iş (Google Cloud Console / Azure'da uygulama kaydı) gerektiren ayrı,
daha büyük bir görev. İleride dönülecek.

## 22. Görsel üretimini tarayıcıdan API'ye taşıma
**Şimdilik ertelendi (2026-08-07)** — engel para değil, ödeme kurulumu.

**İstenen:** "şu promptla 20 görsel üret" denince Chiron'un donmadan, fareyi
işgal etmeden, arka planda üretip indirmesi.

**Bugünkü yol neden yetmiyor:** `gemini_desktop_task` ([[Gemini-Masaustu]])
işi yapıyor ama kullanıcının canlı denemesinde iki sorun çıktı — fare yanlış
yerlere tıklıyor ve akış çok yavaş. Teşhis: DPI ölçekleme **değil** (ölçüldü,
tıklama uzayı ile görüntü uzayı 1920x1080 örtüşüyor, süreç SYSTEM_AWARE).
Sebep vision'ın konum hassasiyeti: 0-1000 normalize koordinat 1920 pikselde
~2 piksel/birim çözünürlük demek ve bir görselin köşesindeki küçük indirme
ikonu için yetmiyor. Yavaşlık da yöntemin doğasında — her adım bir ekran
görüntüsü + model çağrısı. İkisi de ayarla düzelecek hatalar değil.

**API yolunun engeli:** kullanıcının anahtarıyla ölçüldü — görsel üretim
modellerinin üçünde de ücretsiz katman `limit: 0`
(`gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image`, `gemini-3-pro-image`),
`imagen-4.0-*` ise 404. Gemini Pro aboneliği web arayüzünü kapsıyor, API'yi
değil. Yani faturalandırma açmak şart: AI Studio → API keys → Set up billing,
Prepay'de minimum $10.

**Maliyet:** ~$0.045/görsel (flash) → 20 görsel ~$0.90; pro ~$0.134 → ~$2.68.
Batch API'de %50 indirim.

**Devam edilirse yapılacak:** `generate_images` aracı (Gemini image API,
tarayıcı ve fare yok, paralel üretim, dosyaya yazma). Kod faturalandırmadan
bağımsız yazılabilir, aktifleşince çalışır.

**Faturalandırma açılırsa ilk iş:** `aistudio.google.com/spend` üzerinden aylık
tavan koymak. Tier 1 varsayılanı $250 ve bir döngü hatası bunu gecede yakar —
ekran bekçisi dersinin para hâli ([[Bilinen-Tuzaklar]]).

**Bu arada yapıldı:** tarayıcı yolunun güvenilirliği artırıldı (sabit 18 sn
bekleme yerine ekranın durmasını bekleme, indirmeyi dosya sisteminden
doğrulama, tur başına bir vision çağrısı azaltma, dürüst sayaç). Bu
iyileştirmeler yukarıdaki iki temel sorunu çözmüyor ama araç API'ye geçilene
kadar kullanılacaksa daha az yalan söylüyor. Canlı testi yapılmadı.

---

# CLAUDE.md'ye göre eksikler

2026-07-31'de `CLAUDE.md` madde madde kodla karşılaştırıldı; aşağıdakiler
sözleşmede yazıp gerçekte olmayanlar. Numaralar 13'ten başlıyor: 1-12 arası
kaynak kodun içinden atıf alıyor (ör. `actions/screen_watch.py` → "#7"),
tekrar kullanılırsa o atıflar yanlış maddeye işaret eder.

## 13. Muhakeme akışı (Reasoning) — alt panel
**Yapıldı (2026-07-31), CANLI ONAY BEKLİYOR.**

Yapılanlar: `_build_config()` artık `thinking_config=ThinkingConfig(
include_thoughts=True)` gönderiyor; `_receive_audio` içinde `model_turn.parts`
listesindeki `thought=True` işaretli parçalar toplanıyor, cümle sınırında
`reasoning` olayı olarak yayınlanıyor ve Timeline'da italik + beyin ikonuyla
gösteriliyor. `TimelineKind` içindeki ölü `'reasoning'` üyesi canlandı.

**Not:** ilk plan yanlış yeri işaret ediyordu — `out_buf` Chiron'un SÖYLEDİĞİ
şey, o zaten sohbette görünüyor. Gerçek muhakeme `model_turn.parts` içinde
ayrı bir bayrakla geliyor.

**Neden hâlâ silinmedi:** `models/gemini-2.5-flash-native-audio-latest`
modelinin düşünce parçası gerçekten yayınlayıp yayınlamadığı canlı oturumda
DOĞRULANMADI. Boru hattının tamamı (yayın, tampon, olay, arayüz) sahte veriyle
test edildi ve çalışıyor; eksik olan tek şey modelin gerçekten düşünce
göndermesi.

Model bu ayarı reddederse `_is_thinking_rejection` yakalayıp
`_thinking_supported = False` yapıyor ve hemen yeniden bağlanıyor — sesli
asistanın çalışması muhakeme akışına feda edilmiyor. Timeline'da muhakeme
satırı hiç görünmüyorsa sebep budur; `debug` akışında uyarı satırı çıkar.

### İlk canlı deneme (2026-08-06) — sonuçsuz, teşhis eklendi

Çok adımlı planlama sorusu soruldu (üç iş, üç kısıt, tek doğru sıra). Chiron
doğru cevabı verdi ama **muhakeme satırı hiç çıkmadı**.

Elenen ihtimal: valf devreye girmedi. Log'da 19:52:42'de tek bir "Bağlandı"
var, yeniden bağlanma yok, `thinking_config` reddi yok — yani ayar **kabul
edildi**.

Elenmeyen iki ihtimal ve neden ayırt edilemedi: Temmuz log'larında SDK'nın
`non-data parts in the response: ['text', 'thought']` uyarısı var ve bunlar
vision çağrılarından DEĞİL, Live oturumundan geliyor (her biri bir araç
çağrısıyla aynı saniyede). Ama o uyarı yalnızca **alanın var olduğunu**
söylüyor, **değerini değil** — `thought=False` taşıyan sıradan bir metin parçası
da aynı uyarıyı üretir. Yani "model düşünce gönderiyor ama biz kaçırıyoruz" ile
"model hiç göndermiyor" ihtimalleri log'dan ayrılmıyor.

Bu yüzden `_receive_audio` içine bağlantı başına **bir kez** çalışan bir teşhis
kondu: metin taşıyan ilk parçanın gerçek `thought` değerini yazıyor
(`🧠 model_turn parçası: thought=...`). Bir sonraki oturumda:

- `thought=True` → model gönderiyor, hata bizde; boru hattı incelenecek.
- `thought=False` → model düşünce göndermiyor, kod doğru. Madde silinir,
  "bu model sürümü desteklemiyor" olarak kasaya yazılır.
- Satır **hiç yok** → `model_turn` metin parçası hiç gelmiyor (yalnızca ses +
  araç çağrısı). O zaman muhakeme başka bir alandan aranmalı.

## 14. Yüz tanıma
`CLAUDE.md` § RIGHT PANEL: Camera ✓, Object Detection ✓, OCR ✓, **Face
Recognition ✗**.

Yeni ve ağır bir bağımlılık gerekiyor (InsightFace ya da dlib) ve gizlilik
açısından hassas — kimin yüzünün nerede saklanacağı ayrıca kararlaştırılmalı.

## 20. Ambient bağlamı oturuma İTME yolu denenmedi
`get_context` bugün **çekme** modelinde: model ihtiyaç duyunca çağırıyor
(bkz. [[Ambient-Baglam]]). Sürekli enjeksiyon
(`send_client_content(turn_complete=False)`) bilerek yapılmadı — SDK
`send_realtime_input` ile karıştırmaya karşı uyarıyor ve açık bırakılan bir tur
Chiron'u sese sağır bırakabilir.

Denenecekse: kotanın bol olduğu bir anda, `_thinking_supported` desenindeki gibi
bir güvenlik valfiyle (reddedilirse/susarsa anında kapat ve yeniden bağlan).
Kazancı, modelin bağlamı çağırmayı unutamaması olurdu.

## 21. Mikrofon — düzeltildi, CANLI ONAY BEKLİYOR

Ölçüm yapıldı (2026-08-06): iki WASAPI mikrofonu da konuşurken yanıt veriyor
(kulaklık tepe 19771, dizi 3911). Donanım sağlam, sorun tamamen koddaydı;
düzeltme yazıldı ve bileşen bileşen test edildi.

Yapılanlar ve ölçümler: [[Bilinen-Tuzaklar]] § Mikrofon: host API'yi de ölç ve
§ Sessiz mikrofonla ölü mikrofon ayırt edilemez.

Test edilen: aşağı örnekleyici (48k/44.1k→16k, uzunluk + RMS korunumu + uç
durumlar), cihaz seçimi (boş config → WASAPI kulaklık; `"Microphone Array"` →
WASAPI dizi, artık MME kopyası değil), hız uzlaşması (16 kHz reddedildi →
48 kHz'de açıldı, 427 ms ham → 427 ms @16k).

**Doğrulanmayan tek şey: Chiron gerçekten duyuyor mu.** Boru hattının tamamı
ayrı ayrı çalışıyor ama uçtan uca canlı bir oturumda konuşulup yanıt alınmadı.
Chiron'u aç, konuş; yanıt veriyorsa bu madde silinir.

---

**Çalışma şekli:** Bu listeden birini seçip beraber yapıyoruz, test edip onaylandıktan
sonra maddeyi buradan siliyoruz, sıradakine geçiyoruz.
