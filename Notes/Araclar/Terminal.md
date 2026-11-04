---
tags: [chiron, arac]
---

# Terminal — `open_terminal`

Bağlı: [[Home]] · [[Open-App]] · [[PC-Isi]] · [[Istek-Listesi]] § İ-010

**Ne:** "Terminalde yeni sekme aç ve Claude'a bağlan", "Dilcep'te Claude aç" → Windows Terminal'in son
penceresinde, projenin klasöründe yeni sekme; içinde `claude` (ya da "kaldığı yerden" → `claude --continue`).
`run_claude=false` ile sadece klasörde sekme.

**Neden (2026-10-30):** Telefondan gelen İ-010. `open_app("Terminal")` eski `cmd` penceresini açıyordu, klasör ve
Claude elle. `delegate_to_pc`'den farkı: o işi Chiron yaptırır (Komuta), bu Yunus'un KENDİSİ terminalde çalışması için.

**Nasıl:** `actions/terminal.py`
- Klasör: boş → ev klasörü; yoksa `~/Projects` altındaki klasörlerden tam ad (harf farkı yok), sonra TEK önek, sonra
  TEK parça eşleşmesi. Birden çok eşleşmede tahmin yok — hata + proje listesi döner. Gizli (`.pano-worktrees`) proje değil.
- Komut: `wt -w 0 new-tab -d <klasör> --title Claude cmd /k claude`. `-w 0` = en son kullanılan pencere; pencere
  yoksa wt yenisini kurar.
- Serbest komut yok: sekmede yalnız sabit `claude` çalışır. Serbest komut `shell_run`'ın (iki adımlı onay).

**Tuzaklar:**
- `;` wt'de komut ayırıcı — yolda geçerse komut bölünür; öyle klasör reddedilir.
- npm'in `claude`'u `.cmd` kabuğu; wt onu doğrudan başlatamaz → `cmd /k`. `/k` Claude çıkınca sekmeyi açık tutar.
- `wt` bulunamazsa: Ayarlar > Uygulamalar > Uygulama yürütme diğer adları'nda Windows Terminal açık olmalı
  (`%LOCALAPPDATA%\Microsoft\WindowsApps`).
- Gerçek wt ile canlı denenmedi (2026-10-30, gece kartı); testler komutu ve klasör çözümünü doğruluyor.

**Eksik:** telefondan doğrudan açma — `backend/core/desktop_control.py` beyaz listesine eylem + mobil uygulamada
`send_desktop_command` seçeneği gerekiyor. Şimdilik telefon `delegate_to_claude` ile iş verebiliyor.

Kaynak: https://learn.microsoft.com/en-us/windows/terminal/command-line-arguments
