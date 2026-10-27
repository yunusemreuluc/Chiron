---
tags: [chiron, arac]
---

# Otonom Düzeltme — auto_fix.py

Bağlı: [[Home]] · [[Izleme-ve-Brifing]] · [[Ekran-Mudahale]] · [[Screen-Vision]] · [[Bilinen-Tuzaklar]]

Chiron ekranda gördüğü hatayı **kendisi düzeltir**. Araç: `set_auto_fix`.

Kullanıcı isteği (2026-08-01): *"hata buluyorsa çözümü de bulsun ve kendi
yapsın."* Çözüm ÖNERME zaten vardı — eksik olan son adımdı: proaktif mesaj
açıkça **"kendiliğinden tıklama/yazma yapma"** diyordu.

## Akış

```
_watch_screen_for_issues (25 sn'de bir)
  └─ check_for_issue          → sorun var mı + tam hata metni
      └─ plan_fix             → teşhis + en fazla 3 adımlık plan + risk puanı
          └─ apply_plan       → politikaya göre uygula
              └─ proaktif mesaj: NE YAPTIM / NEYİ YAPMADIM
```

## Politika: `auto_fix_mode`

`config/api_keys.json` içinde, varsayılan **`safe`**.

| Mod | Davranış |
|---|---|
| `off` | Yalnızca haber verir ve tavsiye eder (eski davranış) |
| `safe` | Geri alınabilir **tıklamaları** kendi yapar, riskliyi sorar |
| `all` | Sormadan uygular — ama yıkıcı adımlar yine sorulur |

Sesle değiştirilebiliyor: "kendin düzelt" → `all`, "bana sor" → `safe`,
"otomatik düzeltmeyi kapat" → `off`.

## Üç kapı — ve neden üç tane

Bir vision modelinin kendi tahminiyle tıklaması gerçek bir risk: "Yeniden
Dene" ile "Sil" aynı diyalogda yan yana durur. Otomatik uygulama üç bağımsız
kapıdan geçiyor, **üçü de** geçilmeden hiçbir şey tıklanmıyor:

1. **Eylem türü** — `safe` modda yalnızca `click`. `type`/`type_enter` asla
   otomatik değil: bir terminale yazılan metin, Enter'la birlikte keyfi komut
   çalıştırmak demek.
2. **Yerel yasak listesi** — `DESTRUCTIVE_PATTERNS`. Bu kapı **Python'da ve
   modelden bağımsız**: modelin "risk: low" demesi burayı açmıyor. Tek
   güvenlik ağının, hakkında karar verilen şeyin kendisi olması kabul
   edilemezdi.
3. **Modelin risk puanı** — yalnızca `low` geçer.

`all` modunda 1 ve 3 gevşer, **2 gevşemez**: "sormadan yap", "verimi yok et"
demek değil.

## İki fazlı uygulama — asıl koruma burada

Yasak listesi tek başına kandırılabilir: model "Sil" düğmesini *"kırmızı
buton"* diye tarif ederse kapı açılırdı, çünkü kapı yalnızca **tarifi**
görüyor. Bu yüzden her adım iki fazda yürüyor:

1. `intervene_screen(confirm=False)` — hiçbir şey yapmaz, hedefi **bulur** ve
   ne bulduğunu `data.target` içinde döndürür.
2. **Bulunan şeyin** tarifi yasak listesinden geçirilir; temizse
   `confirm=True` ile gerçekten tıklanır.

Yani karar, modelin ne demek istediğine değil ekranda **gerçekten bulunan**
şeye göre veriliyor. Test edildi: model "kırmızı buton" derken ekranda "'Sil'
onay butonu" bulunduğunda **tıklama yapılmadan** engellendi.

Bedeli adım başına fazladan bir vision çağrısı — otomatik düzeltme nadir
çalıştığı için kabul edilebilir kota maliyeti.

## Diğer korumalar

- **İlk engelde durur.** Adımlar sıralı; ikincisi birincinin ekranı
  değiştirmesine bağlı. Atlayıp devam etmek, var olmayan bir ekranda tıklamak
  olurdu.
- **Kullanıcı yazarken tıklamaz.** `AUTO_FIX_MIN_IDLE_S = 2.0` — yazmanın
  ortasında odak çalmak, düzelttiği sorundan rahatsız edici olurdu
  ([[Ambient-Baglam]]'ın boşta ölçümünü kullanıyor).
- **En fazla 3 adım.** Daha uzunsa bu bir düzeltme değil kurulum sihirbazıdır;
  orada kullanıcı olmalı (`can_fix_on_screen:false` döner, tavsiyeye düşer).
- **Her zaman duyurur.** Yapılan iş Timeline'a `auto_fix` görevi olarak
  düşüyor ve Chiron sesli olarak "şunu yaptım" diyor — izin ister gibi değil,
  olmuş bir şeyi haber verir gibi.

## Diakritik tuzağı

Yasak listesi ilk yazımında **"satın al"** içeriyordu ama model hedefi
`"Satin Al"` diye diakritiksiz yazınca eşleşme olmuyor ve **kapı sessizce
açılıyordu**. Aynısı `gönder`/`Gonder`, `devre dışı`/`devre disi` için de
geçerliydi — testte yakalandı (bkz. [[Bilinen-Tuzaklar]]).

Artık hem liste hem gelen metin `_normalize` ile ASCII'ye katlanıyor. Türkçe
metinle çalışan **her** güvenlik karşılaştırması bunu yapmak zorunda.

Listede bilerek **olmayan** bir sözcük: yalın `"yükle"`. Türkçede hem
"install" hem "load" demek; konsaydı *"Sayfayı yeniden yükle"* — en yaygın
zararsız düzeltme — bloklanırdı. Karşıya veri gönderen anlamı için
`"karşıya yükle"`/`"upload"` yeterli.
