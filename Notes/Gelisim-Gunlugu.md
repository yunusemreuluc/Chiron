---
tags: [chiron, gelisim]
---

# Gelişim Günlüğü

Chiron'un kendini geliştirme döngüsünün (backend/core/dongu.py § Kendini geliştirme) kaydı. Her geliştirme
kartı en üste bir kayıt ekler: ne yaptı, neden daha iyi, ne öğrendi, kaynak. Sonraki kartlar bunu okuyup
tekrar etmez. Bağlı: [[Ajan-Ofisi]] · [[Istek-Listesi]]

## 2026-10-30 — "Terminalde yeni sekme aç ve Claude'a bağlan"
- **Ne yaptım:** PC'deki sesli Chiron'a `open_terminal` aracı (`actions/terminal.py`, [[Terminal]]): Windows
  Terminal'in son penceresinde, söylenen projenin klasöründe (`~/Projects` altı, ad/önek eşleşmesi) yeni sekme açar,
  içinde `claude` ya da "kaldığı yerden" denince `claude --continue` başlatır. İstek listesindeki İ-010.
- **Neden daha iyi:** Eskiden "terminal aç" eski `cmd` penceresini açıyordu, klasöre gitmek ve Claude'u başlatmak elle
  yapılıyordu. Şimdi "Dilcep'te Claude aç" tek cümle; yeni pencere değil, açık terminale sekme olarak eklenir.
- **Ne öğrendim:** `wt -w 0 new-tab -d <klasör>` son pencereye sekme ekler, pencere yoksa yenisini kurar; `;` wt'nin
  komut ayırıcısı, yolda geçerse komutu böler. npm'in `claude`'u `.cmd` kabuğu, wt onu doğrudan başlatamaz —
  `cmd /k claude` gerekiyor (`/k` Claude kapanınca sekmeyi açık tutar). Belirsiz proje adında (iki eşleşme) tahmin
  etmek yerine reddedip proje listesini döndürmek daha dürüst. Telefondan açmak mobil uygulamada iş istiyor (sırada).
- **Kaynak:** https://learn.microsoft.com/en-us/windows/terminal/command-line-arguments

## 2026-10-30 — "İş ne durumda?" sorusuna canlı cevap
- **Ne yaptım:** Sesle sorulabilen `check_pc_job` aracını ekledim. Komuta'daki son işin canlı durumunu
  söylüyor: sırada mı, kaç dakikadır çalışıyor, şu an hangi adımda; bittiyse ne zaman bitti ve sonucu ne;
  onay bekliyorsa neyi beklediği. Arka uçta `GET /api/remote/komuta/durum` ve `sohbet.job_status()`.
- **Neden daha iyi:** Yunus sesle iş verip başka işe geçiyor. "Dilcep işi ne alemde?" diye sorduğunda
  Chiron'un elinde yalnız oturum açılışındaki eski bilgi vardı; ya bayat cevap veriyor ya uyduruyordu.
  Artık Komuta ekranına bakmadan, gerçek iş kaydından gelen bir cümle duyuyor.
- **Ne öğrendim:** Ses arayüzünde ilerleme bildirirken yalnız arka ucun doğruladığı birkaç durum
  (sırada/çalışıyor/bitti) söylenmeli. "Ne zamandan beri" ve "şu anki adım" bilgisi, belirsiz bir
  "çalışıyor" sözünden çok daha fazla güven veriyor. Kodda: canlı mesajın `at` alanı işin verildiği an,
  iş bitince `_sync` onu bitiş anıyla değiştiriyor. Dock'taki Duraklat düğmesini Yunus 2026-07-30'da
  bilerek "Sohbeti sil" ile değiştirmiş. Yol haritasındaki "Duraklat düğmesi yok" maddesi bu yüzden
  geri eklenecek bir şey değil, yanıltıcı (AssistantDock.tsx'teki yoruma bak).
- **Kaynak:** digitalapplied.com/blog/voice-agent-background-tool-work-guide (doğrulanmış, az sayıda
  iş durumu); blog.logrocket.com/ux-design/ui-patterns-for-async-workflows-background-jobs-and-data-pipelines
  (şu anki adım, son güncelleme zamanı); appmaster.io/blog/background-tasks-progress-ui.

