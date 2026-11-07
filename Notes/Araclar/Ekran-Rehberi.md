---
tags: [chiron, arac]
---

# Ekran Rehberi — actions/ekran_gosterge.py + core/ekran_rehberi.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Ekran-Mudahale]] · [[Ekran-Icerigi]] · [[Bilinen-Tuzaklar]]

Kabarcık (07 Parçacık bulutu) köşeden hedefe uçar, parçacıkları hedefin çevresinde ışık halkası olur, iş bitince
köşesine döner. Yunus Instagram'daki bir ekran asistanını gösterdi, dört taslaktan D · Kabarcık'ı seçti, canlandırmayı
izleyip "bu çok iyi olmuş, bundan devam" dedi (2026-11-07, taslak artifact `SFsxEpKGxEERiBPnq2mfXj`).

Araçlar: `show_on_screen`, `explain_on_screen`, `clear_screen_marks`.

| Söz | Araç | Halka ne zaman kalkar |
|---|---|---|
| "X nerede", "X'i göster" | `show_on_screen` | hedefe tıklayınca, Esc, pencere değişince, 15 sn |
| "daire içine al", "işaretle" | `show_on_screen(circle=true)` | aynısı, "kaldır", 1 dk |
| "bu ne" (imlecin altı) | `explain_on_screen` | hedefe tıklayınca, Esc, pencere değişince, 15 sn |
| "kaldır" | `clear_screen_marks` | hemen |

## Neden onay yok

[[Ekran-Mudahale]]'nin tersine hiçbir şey tıklamaz, yazmaz. Pencere tıklamayı geçirir ve odak almaz: kullanıcının
işini bölemez. Chiron'un kendisi tıklayacaksa kural değişmez, `intervene_screen` ve iki adımlı onay.

## Hedef bulma

1. **UI Automation:** kesin dikdörtgen, ücretsiz, ekran görüntüsü dışarı çıkmaz. PowerShell üzerinden; Python'da
   comtypes/pywinauto yok.
2. **Gemini vision:** UIA bulamazsa. Yavaş ve yaklaşık. Ekran görüntüsü Gemini'ye gider.

Eşleşme `best_match`: önce sorgudan tarif sözleri atılır ("sekmesi", "butonu"), tam ad en yüksek puan. "dosya kaydet"
isteğinde "Dosya" menüsünü seçmemesi için kısmi eşleşme eşiğin altında kalır, görüntüye düşer. Ekran İngilizceyse
UIA Türkçe sorguyu bulamaz: `target` ekranda yazan ad olmalı, model bunu prompt'tan biliyor.

## Tuzaklar

**"Yukarıda takılı kaldı" (ilk gerçek deneme, 2026-11-07).** Halka doğru yerdeydi (Word "Ekle", ekran görüntüsüyle
doğrulandı), kare 4 ms, varış 1 sn. Sebep: model öğretirken `circle=true` seçti, o kipte tıklama halkayı kaldırmıyordu,
2 dk duruyordu. Bu arada pencere değişse de halka boşlukta kalıyordu. Şimdi tıklama her kipte kaldırır ve modele haber
olur (sıradaki adım "tamam" beklemez); öndeki pencere değişir ya da oynarsa kalkar (`WindowWatch`).

**Hedef arkada.** Aynı denemede Word terminalin arkasındaydı: "bulunamadı". Şimdi önce öndeki, sonra arkadaki en çok üç
pencerede aranır, arkada bulunursa öne gelir. Oyun penceresi atlanır.

**Oyun.** İlk canlı denemede öndeki pencere VALORANT çıktı. Hile korumalı oyunun üstüne çizmek ve ekranını okumak
hesabı riske atabilir, maçı da böler: `game_in_front` (süreç listesi + tam ekran DirectX) öndeyken araçlar ekrana
dokunmadan reddeder. Çerçevesiz pencere modundaki bilinmeyen oyunu yakalamaz, liste `GAME_PROCESSES`.
Bu yüzden canlı deneme de oyun kapalıyken yapılır.

**DPI (ölçüldü 2026-11-07).** Ekran %125: DPI farkında olmayan süreç 1536x864 görüyor, gerçek 1920x1080. PowerShell
farkında değil. UIA betiği ve araç/çizim iş parçacıkları `SetThreadDpiAwarenessContext(PER_MONITOR_AWARE_V2)` ile
fiziksel piksele alınıyor. Biri unutulursa halka hatasız ama hedefin yanına düşer.

**Çizim alanı.** Pencere yalnız kabarcığın kapladığı alan kadar (`compose`, 16'ya hizalı). Tüm ekranı her karede çizmek
4K'da saniyede yüzlerce MB eder.

**Aynı kabarcık iki yerde.** Rehber çalışırken köşedeki gösterge kapanır (`SpeakingOverlay.set_suppressed`).

**Ekrandan gelen metin veridir.** Öğe adları ve görüntüden üretilen açıklama araç sonucunda "talimat değil" diye
işaretli. Şifre alanının görüntüsü gönderilmez, değeri okunmaz.

**Pencere önde kalmasın.** Yunus: "bir şey soracağımda ya da bana göstereceğinde tepsiye al moduna geçsin otomatik".
`core/otomatik_tepsi.py`: araçlar hedefi aramadan önce, ses döngüsü de en az iki kelimelik konuşmada pencereyi tepsiye
indirir. Mikrofon sürekli açık, gürültü tek kelimeyle tetiklemesin diye eşik var. Pencereyi kullanıcı kendi açtıysa 30 sn,
pano öne geldiyse 2 dk konuşma indirmez; ekranda gösterme bu beklemeyi dinlemez. Kapatmak: `auto_tray` = false.

## Deneme

`python -m core.ekran_rehberi --demo` gerçek ekranda oynatır, Chiron'u yeniden başlatmak gerekmez.

## Sıradaki aşamalar

Adım adım öğretme (hedefe tıklamayı algılayıp sonraki adım), `Ctrl+Alt` bas-konuş, "Yapıyor · Esc" hapı.

Tool: `show_on_screen`, `explain_on_screen`, `clear_screen_marks` ([[Arac-Tanimlari]]).
