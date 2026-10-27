---
tags: [chiron, arac]
---

# Video Analizi — actions/video_analysis.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Screen-Vision]]

`analyze_video(source, question="")` — bir YouTube linkini veya bilgisayardaki bir video
dosyasını baştan sona (görüntü + ses) Gemini'ye "izletip" Türkçe rapor aldırır.

## Akış
1. `_is_url()` — `source` YouTube/http(s) linki mi yoksa yerel dosya yolu mu ayırt eder.
2. Linkse `_download_video()`: `yt-dlp` ile indirir. **ffmpeg bu makinede kurulu değil** —
   bu yüzden format seçici bilerek zaten ses+görüntüsü birleşik ("muxed") tek dosya formatlarını
   istiyor (`best[height<=720][ext=mp4][acodec!=none][vcodec!=none]/...`), ffmpeg ile
   ayrı akışları birleştirmeye hiç gerek kalmıyor. Süre 60 dakikayı aşan videolar reddediliyor
   (Gemini'nin varsayılan ayarlardaki pratik sınırı).
3. Yerel dosyaysa `_resolve_local_path()` — varlık + uzantı kontrolü, **kullanıcının dosyası
   hiçbir zaman silinmiyor** (sadece indirilenler siliniyor).
4. `_upload_and_wait()` — Gemini Files API'sine yükler (`client.files.upload`), `PROCESSING`
   → `ACTIVE` olana kadar 3sn aralıklarla polling yapar (azami 5dk).
5. `_analyze_with_gemini()` — `VIDEO_MODELS` listesini sırayla dener, `screen_vision.py`'deki
   gibi geçici hatalarda (503/429/timeout) retry yapar.
6. `finally` bloklarında hem Gemini'ye yüklenen dosya (`client.files.delete`) hem (varsa)
   indirilen geçici klasör silinir.

## Model seçimi — 2026-07-25'te gerçek testle bulundu
`gemini-2.5-flash` bu hesapta **404** veriyor ("no longer available to new users" —
model teknik olarak var ama yeni API anahtarlarına kapatılmış). `gemini-2.0-flash` da
testte **429 kota** hatası verdi. Bu yüzden `VIDEO_MODELS` bilerek şunları kullanıyor:
`gemini-flash-latest` (Google'ın sürekli güncel tuttuğu takma ad, model deprecate olsa
bile bozulmaz) → `gemini-2.5-flash-lite` → `gemini-3.5-flash`. Üçü de gerçek bir videoyla
(ilk YouTube videosu "Me at the zoo") test edildi, doğru ve tutarlı sonuç verdiler.

## Test notu
Gerçek uçtan uca test edildi — hem YouTube linki hem yerel dosya yoluyla, ikisi de doğru
çalıştı (yerel dosyanın silinmediği ayrıca doğrulandı). `screen_vision.py`'nin aksine burada
tek bir sabit resim değil, gerçekten tüm video (görüntü+ses) Gemini'ye gidiyor — rapor
zaman damgalı önemli noktalar içeriyor, uydurma değil videodan gerçekten "görüp duyduğu" şeyler.

Tool: `analyze_video` ([[Arac-Tanimlari]]). Yeni bağımlılık: `yt-dlp` (`requirements.txt`).
