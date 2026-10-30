---
tags: [chiron, gelisim]
---

# Gelişim Günlüğü

Chiron'un kendini geliştirme döngüsünün (backend/core/dongu.py § Kendini geliştirme) kaydı. Her geliştirme
kartı en üste bir kayıt ekler: ne yaptı, neden daha iyi, ne öğrendi, kaynak. Sonraki kartlar bunu okuyup
tekrar etmez. Bağlı: [[Ajan-Ofisi]] · [[Istek-Listesi]]

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

