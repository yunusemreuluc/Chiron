---
tags: [chiron, arac]
---

# OCR — actions/ocr.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Nesne-Tanima]] · [[Webcam]] · [[Arayuz]]

Kameradaki **yazıyı** okur (Türkçe + İngilizce). Eklenme: 2026-07-31.

## Neden Gemini değil

Gemini vision bu işi yapabilirdi ama her okuma günlük kotadan yerdi ve kota bu
projede gerçek bir kısıt. EasyOCR tamamen yerel: kotaya dokunmuyor, internet
gerektirmiyor (ilk çalıştırmadaki model indirmesi hariç).

## Tembel yükleme

`easyocr` modül seviyesinde import EDİLMİYOR — aynı gerekçe [[Nesne-Tanima]]
notundaki ultralytics açıklamasında. Kurulu olup olmadığı `find_spec` ile
bakılıyor, gerçek import ilk okumada.

**İlk çağrı yavaştır:** tanıma modelleri (~100 MB) `~/.EasyOCR/` altına
indiriliyor ve belleğe yükleniyor — ölçülen ~10-14 sn. Sonrakiler CPU'da **~1 sn**
(projedeki torch CPU sürümü, `2.13.0+cpu`; bu yüzden `gpu=False`).

## Okuma sırası — dikkat

EasyOCR aynı görsel satırdaki kelimeleri **ayrı parçalar** olarak döndürüyor ve
bunların üst kenarları birkaç piksel oynuyor. Ham `(y, x)` sıralaması bu yüzden
"Çilek şeftali üzüm" → "şeftali çilek üzüm" üretiyordu. `_sort_reading_order()`
parçaları önce satırlara kümeleyip (`ROW_TOLERANCE`, satır yüksekliğinin %60'ı)
her satırı kendi içinde soldan sağa sıralıyor. Metin sesli okunduğu ve
kopyalanabildiği için bu gerçek bir hataydı.

## Çıktı sözleşmesi

`read_text_in_jpeg()` → `[{text, confidence, box}]`, `box` normalize
`[x1, y1, x2, y2]` — [[Nesne-Tanima]] ile **birebir aynı** sözleşme. EasyOCR dört
köşe (dönmüş olabilir) veriyor; eksene hizalı sınır kutusuna indirgeniyor, çünkü
arayüzde kutular CSS ile çiziliyor.

`MIN_CONFIDENCE = 0.35` altındaki okumalar atılıyor — OCR düşük güvende gerçekte
olmayan kelimeler uyduruyor ve yanlış metin, metin olmamasından kötü.
`MAX_LINES = 40`.

`lines_to_text()` satırları tek metne birleştiriyor (sesli cevap ve "Kopyala" için).

## Bilinen sınır

Türkçe noktasız `ı` ile büyük `I` birçok fontta birebir aynı göründüğü için
karışabiliyor ("ışığı" → "ışığI"). Modelin doğal sınırı.

## Arayüz bağlantısı

Sonuçlar `vision_text` olayıyla Vision paneline akıyor ([[Arayuz]]): kutular kare
üzerine çiziliyor, birleşik metin altta gösteriliyor ve kopyalanabiliyor.

Tool: `read_text` ([[Arac-Tanimlari]]).

## Ekran mı, kamera mı

`core/prompt.txt` 2026-08-06'ya kadar `read_text`'ten hiç söz etmiyordu —
şema (`tool_defs.py`) ve fonksiyon vardı, modele "ne zaman çağıracağı"
söylenmemişti (CLAUDE.md § Adding a new tool, üçüncü yer). Eklenirken asıl
mesele ayrımdı: "bunu oku" hem ekrandaki bir hata kutusu hem kameraya tutulan
bir kâğıt için söyleniyor. Prompt artık ikisini ayırıyor — yazı **ekrandaysa**
`analyze_screen`, **kameradaysa** `read_text`, nesne tanıma ise ikisi de değil
`recognize_objects`.
