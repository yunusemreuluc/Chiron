---
tags: [chiron, arac]
---

# Pencere Yönetimi — `manage_window`

Bağlı: [[Home]] · [[Open-App]] · [[Ekran-Mudahale]] · [[Gelisim-Gunlugu]]

**Ne:** "Chrome'a geç", "pencereyi küçült", "tam ekran yap", "eski haline getir", "Spotify'ı kapat", "bunu sola
yasla", "masaüstünü göster", "hangi pencereler açık?" → açık pencereler. Eylemler: `list`, `focus`, `minimize`,
`maximize`, `restore`, `close`, `left`, `right`, `show_desktop`. `app` boşsa öndeki pencere.

**Neden (2026-11-04, K-015):** Chiron uygulama açabiliyordu ([[Open-App]]) ama açık pencerelere dokunamıyordu;
"Chrome'a geç" yalnız `intervene_screen`'in `app_hint`'iyle, tıklama akışının içinde vardı.

**Nasıl:** `actions/windows.py` — saf ctypes (user32/dwmapi), yeni bağımlılık yok.
- Liste Alt+Tab'a yakın: görünür + başlıklı + sahipsiz (ya da `WS_EX_APPWINDOW`) + `WS_EX_TOOLWINDOW` değil +
  `DWMWA_CLOAKED` değil (askıdaki mağaza uygulamaları) + kabuk sınıfı değil (Progman, Shell_TrayWnd). Chiron'un
  kendi süreci (`os.getpid()`, masaüstü penceresi sesle aynı süreçte) hariç — "bu pencereyi kapat" kendini kapatmaz.
- Eşleşme: önce süreç adı (`chrome`), sonra başlık parçası. "VS Code chrome-notes.md" başlıklı pencere "Chrome"
  isteğini çalmasın diye sıra önemli. Kısa adlar: tarayıcı, terminal, not defteri, gezgin, vs code.
- EnumWindows z-sırasıyla döner → ilk eşleşme en son kullanılan pencere.
- Her eylemden sonra durum GERİ OKUNUR (IsIconic / IsZoomed / ön plan / IsWindow); doğrulanmazsa `success=false`.
- Kapatma `WM_CLOSE` — uygulamanın "kaydedilsin mi?" sorusunu atlamaz; pencere 2 sn'de kapanmazsa "hâlâ açık" denir.
- Yaslama: `MonitorFromWindow` + `GetMonitorInfo.rcWork` (görev çubuğu hariç, sol üst 0,0 olmayabilir), önce
  büyütülmüş/küçültülmüş pencere eski haline alınır, sonra `SetWindowPos`.
- 64 bit'te her Win32 imzasına `argtypes`/`restype` verildi — verilmezse tanıtıcılar int'e kırpılır.
- Gerçek pencerede doğrulandı (yeni açılan Not Defteri): küçült, eski haline, tam ekran, sol, sağ, öne getir, kapat.

**Tuzaklar / eksik:**
- Öne getirme Windows'un ön plan kilidine takılabilir (arka plan süreci); `screen_control._force_foreground`
  (AttachThreadInput) kullanılıyor, yine de bir denemede başarısız oldu ve dürüstçe söylendi.
- Win11 yaslama düzeni (Snap Layouts) değil, düz yarım ekran; pencerenin görünmez DWM kenarlığı yüzünden kenarda
  birkaç piksel boşluk kalabilir.
- Telefondan ("PC'de Chrome'a geç") açmak mobil uygulamada eylem listesi ister — chiron-mobile işi.

**Kaynak:** devblogs.microsoft.com/oldnewthing/20071008-00/?p=24863 (Alt+Tab kuralları) ·
learn.microsoft.com/windows/win32/gdi/positioning-objects-on-a-multiple-display-setup (rcWork)
