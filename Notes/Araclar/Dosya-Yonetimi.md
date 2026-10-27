---
tags: [chiron, arac]
---

# Dosya Yönetimi — file_manager.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Dosya]] · [[Ekran-Mudahale]] · [[Bilinen-Tuzaklar]]

Araç: `manage_files`. Kullanıcı isteği (2026-08-01).

Öncesinde Chiron'da dosya **değiştiren** hiçbir şey yoktu — [[Dosya]]'daki iki
araç sadece okuyordu (`search_files` bulur, `summarize_file` okur). `shell_run`
ile `ren` komutu uydurulabilirdi ama her çağrıda onay istediği için toplu işte
kullanılamazdı.

## İşlemler

| `action` | Davranış | Onay |
|---|---|---|
| `sequence` | Toplu sıralı adlandırma (`1.jpg, 2.jpg...`), uzantı korunur | Önizleme + onay |
| `rename` | Tek dosyanın adı | Hayır |
| `move` / `copy` | Klasörler arası | Birden fazla dosyada onay |
| `delete` | **Geri Dönüşüm Kutusu'na** | **Hayır** |
| `delete_permanent` | Kalıcı | **Her zaman** |

`sort_by`: `name` (varsayılan) · `date` · `size`. `start`: başlangıç numarası.
`pattern`: hangi dosyalar (`*.jpg`). Tek çağrıda en fazla **500** dosya.

## Silme neden onay istemiyor

Kullanıcının istediği prensip şuydu: *"hedef belirsizse onay al, belirginse
doğrudan yap."* İtiraz edilen nokta: "belirgin" kararını çoğu zaman ekranı
yorumlayan bir vision modeli veriyor ve yanılabiliyor ([[Bilinen-Tuzaklar]]
§ Bir güvenlik kapısı, denetlediği şeye güvenemez). Yanlış tıklama geri
alınabilir, yanlış **silme** alınamaz.

Çözüm onay eklemek değil, **işlemi geri alınabilir yapmak**: `delete` artık
Geri Dönüşüm Kutusu'na gönderiyor (`send2trash`) ve onay istemiyor. Kullanıcının
istediği akıcılık korunuyor, hata telafi edilebilir kalıyor. `delete_permanent`
ayrı bir işlem ve her zaman iki adımlı onay istiyor.

Bu, projedeki "yıkıcı işlem = iki adımlı onay" desenine bir istisna değil,
**aynı hedefe başka yoldan varış**: amaç kullanıcıyı korumaktı, geri alınabilirlik
onu onaydan daha iyi sağlıyor.

## Çakışma tuzağı — iki fazlı adlandırma

`a.jpg → 1.jpg` yapılırken hedefte zaten `1.jpg` varsa üzerine yazılır ve o
dosya **sessizce kaybolur**. Ve bu istisna değil kural: bir klasörü ikinci kez
sıralarken hedef adların hepsi zaten mevcuttur.

Bu yüzden `sequence` iki fazlı çalışıyor:

1. Her kaynak, çakışması imkânsız geçici bir ada taşınır (`.chiron-<uuid>-<ad>`)
2. Geçici adlar nihai hedeflere taşınır

Test edildi: içinde `1.jpg`, `2.jpg`, `adana.jpg` olan bir klasör sıralandığında
**hiçbir dosyanın içeriği kaybolmadı**.

## Diğer korumalar

- **Sistem klasörleri reddediliyor** — `C:\Windows`, `Program Files`,
  `ProgramData` ve sürücü kökü. Sebep: hedef bazen ekran analizinden geliyor ve
  yanlış bir yol üretebiliyor; sistem klasöründe hata onarılabilir olmaktan çıkar.
- **Taşımada üzerine yazılmıyor** — aynı adlı dosya varsa `rapor (1).txt`.
- **Doğal sıralama** — `foto10.jpg`, `foto9.jpg`'den *sonra* gelir. Düz alfabetik
  sıralama olsaydı 10 < 9 sayılırdı ve numaralandırma karışırdı.
- **500 dosya sınırı** — kazara bir kök klasör verilirse binlerce dosyayı
  sessizce işlemesin.

## Bağımlılık

`send2trash` (requirements.txt). Kurulu değilse `delete` çalışmıyor ve
kullanıcıya `delete_permanent` seçeneğini söylüyor — sessizce kalıcı silmeye
düşmüyor.
