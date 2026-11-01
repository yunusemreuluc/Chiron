---
tags: [chiron, arac]
---

# Ekran İçeriği — actions/ekran_icerigi.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Video-Analizi]] · [[PC-Isi]] · [[Screen-Vision]]

**Ne:** "Ekranımda şu an açık olanı analiz et" → `analyze_open_content`; ardından "bunu nasıl yapmış, ben de
istiyorum" → `build_like_analyzed` işi Komuta'ya verir, bitince sesli haber gelir.

**Neden (2026-10-31):** Yunus Instagram'da başka birinin asistan arayüzünü (huwprosser, "ROSE") gördü: "Chiron'a
sesle de yazıyla da, tepsideyken de diyebileyim; analiz etsin, ben de istiyorum deyince yapsın."

## Üç kanal, tek araç

Ses, yazı (`_on_text_command` → `send_client_content`) ve tepsi aynı Gemini Live oturumundan ve aynı araçlardan
geçiyor; ayrı bir yol yazılmadı.

## analyze_open_content(question="")

1. **Hedef pencere:** öndeki pencereden Z-sırasında aşağı inilir; Chiron'un kendi süreci (`os.getpid()`), simge
   durumundakiler, araç pencereleri ve gizli (cloaked) UWP pencereleri atlanır. Yazıyla sorulduğunda öndeki
   pencere Chiron olduğu için bu şart.
2. **Tarayıcıysa link:** adres çubuğu = pencerenin ilk Edit denetimi, Windows PowerShell 5.1'in .NET UI
   Automation'ıyla okunur (Python'da comtypes/pywinauto yok). Ölçüldü: ~140 ms + PowerShell açılışı. Link
   yt-dlp ile inerse baştan sona, sesli izlenir.
3. **Değilse 10 sn ekran kaydı:** ffmpeg `gdigrab` tüm masaüstü, 8 fps, ≤1280 px, sessiz. Link video değilse
   (canlı yayın, video olmayan sayfa) da buraya düşer.

**Sınır:** Chiron penceresi öndeyken ve hedef bir tarayıcı videosu değilse kayıtta Chiron görünür; araç sonuca
"tepsiye alıp tekrar iste" notu ekler.

## Son analiz

`video_analysis.remember_analysis` — hem bu araç hem `analyze_video` yazar.
`%LOCALAPPDATA%\Chiron\son_analiz\` altında `son_analiz.json` (link, etiket, rapor, video yolu) +
`video.<uzantı>`. Yalnız en son analiz tutulur; kullanıcının kendi yerel dosyası taşınmaz, yolu tutulur.

## build_like_analyzed(request="", project="")

Son analizden brief yazar → `pc_isi.delegate_to_pc(new_topic=True)`. Brief'te video yolu var: işi alan taraf
ffmpeg ile kare çıkarıp kendisi bakar, Gemini raporu "iddia" olarak geçer. Proje söylenmezse Chiron
(`~/Projects/Chiron`), çünkü yeni Komuta sohbeti ev klasöründe açılıyor. Brief ≤ `MAX_TASK_CHARS` (4000);
rapor 2200 karakterde kırpılır.

## Test (2026-10-31)

- Adres çubuğu Chrome'da okundu (`youtube.com/watch?v=...` → https eklenir).
- 10 sn kayıt alındı (965 KB). Gemini `flash-latest` 10 sn'lik kaydı **177 sn**'de analiz etti; yavaşlık
  Gemini tarafında, yükleme 5 sn.
- Test sırasında açık sekme bir YouTube canlı yayınıydı: yt-dlp canlı yayını süresiz indirirdi (gözlenmedi,
  koddan). `_download_video` artık `is_live`'ı reddediyor, araç ekran kaydına düşüyor ([[Video-Analizi]]).
