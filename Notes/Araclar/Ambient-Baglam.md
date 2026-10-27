---
tags: [chiron, arac]
---

# Ambient Bağlam — ambient_context.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Screen-Vision]] · [[Izleme-ve-Brifing]] · [[Arayuz]]

Chiron'un "kullanıcı şu an ne yapıyor" farkındalığı. **Araç:** `get_context`.

## Neden var

Chiron "bunu kaydet", "şurayı kapat", "burada ne yazıyor" dendiğinde neyden
bahsedildiğini bilmiyordu. Tek çare [[Screen-Vision]]'ın `analyze_screen`'ini
çağırmaktı — o da Gemini kotası harcıyor, ki kota bu projede gerçek bir kısıt.

`get_context` aynı sorunun **kotasız** cevabı: aktif pencere, onu çalıştıran
program ve klavye/fareye en son ne zaman dokunulduğu. Hepsi Win32'den.
Ölçüldü: **0.033 ms/çağrı.**

## Ne döner

| Alan | Örnek |
|---|---|
| `app` | `Google Chrome` |
| `window_title` | `Alchemy of Souls 1. Sezon 1. Bölüm İzle` |
| `process` | `chrome.exe` |
| `idle_seconds` | `12.8` |
| `away` | `false` (eşik 90 sn) |
| `time` / `date` | `03:07` / `01.08.2026 Cumartesi` |

Tek satır hâli: `03:07 · Google Chrome ("...") · kullanıcı aktif`

## Ekranın İÇİNİ görmez

Bu araç yalnızca hangi pencerenin açık olduğunu söyler. Pencerede **yazanı**
okumak için hâlâ [[Screen-Vision]] gerekiyor. `core/prompt.txt` bunu açıkça
söylüyor; ikisi rakip değil, `get_context` önce çağrılınca `analyze_screen`
daha isabetli kullanılıyor.

## Neden ÇEKME, sürekli enjeksiyon değil

İlk tasarım bağlamı oturuma sürekli beslemekti: pencere değişince
`send_client_content(turn_complete=False)` ile sessizce bildir. SDK bunun
sessiz bir yol olduğunu doğruluyor ("if false, the model will wait…") **ama
hemen üstünde uyarıyor:**

> Caution: Interleaving `send_client_content` and `send_realtime_input`
> in the same conversation is not recommended and can lead to unexpected
> results.

Chiron'un TÜM ses döngüsü `send_realtime_input`. `turn_complete=False` ayrıca
turu AÇIK bırakıyor — en kötü senaryoda model sese cevap veremez, yani **Chiron
susar.** [[Bilinen-Tuzaklar]] § Live oturum yapılandırmasına yeni alan eklemek
riskli maddesindeki kural birebir geçerli: *bir arayüz özelliği, sesli
asistanın çalışmasından önce gelmez.*

Bu yüzden bağlam itilmiyor, **çekiliyor**. Oturuma hiç dokunulmuyor,
kullanılmadığında sıfır token, araç Gemini'ye hiç istek atmıyor. Karşılığında
bir tur gidiş-dönüş gecikmesi var — makul takas.

**Açık soru:** enjeksiyon yolu canlı oturumda hiç denenmedi. Denenecekse
kotanın bol olduğu bir anda, `_thinking_supported` desenindeki gibi bir
güvenlik valfiyle yapılmalı.

## Arayüzde

Sol üstteki `BrandBadge`'in üçüncü satırı — CHIRON / durum / **bağlam**.
Uç nokta `GET /api/system/context`, aracı besleyen fonksiyonun **aynısını**
kullanıyor; ayrı yazılsalardı biri bayatlar ve arayüz olmayan bir farkındalığı
varmış gibi gösterirdi.

Okunamazsa satır hiç çizilmiyor ("bilinmiyor" yazılmıyor). Kullanıcı masada
değilse `· 12 dk uzakta` ekleniyor.

Yoklama 4 sn'de bir, WebSocket değil: bağlam olay değil **durum**, ve alt+tab
sırasında saniyede birkaç olay arayüzü titretirdi.

## Yan etki: CHIRON imzası artık raya yer açıyor

Rozet üç satıra çıkınca sol raydaki hover etiketiyle çakışması büyüdü
(19×9 → 37×30 px). Çözüm `stores/railHoverStore.ts`: raya yaklaşınca imza
%15 opaklığa çekiliyor, etiket öne çıkıyor. Ayrıntı ve elenen alternatifler
[[Arayuz]] § Sol ray içinde.
