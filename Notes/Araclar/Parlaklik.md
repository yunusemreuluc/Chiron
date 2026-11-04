---
tags: [chiron, arac]
---

# Ekran Parlaklığı — `set_brightness`

Bağlı: [[Home]] · [[Ses-Seviyesi]] · [[Gelisim-Gunlugu]]

**Ne:** "Parlaklığı kıs", "ekranı karart", "parlaklığı yüzde kırk yap", "parlaklık kaç?" → dizüstü panelinin
parlaklığı. Eylemler: `get`, `set` (level), `up`/`down` (step, varsayılan 10). Söylenen yüzde panelden GERİ
OKUNAN değerdir.

**Neden (2026-11-04, K-013):** Ses sesle ayarlanabiliyordu ([[Ses-Seviyesi]]) ama ekran değil; gece ya da sunumda
en sık elle yapılan ayar buydu.

**Nasıl:** `actions/brightness.py` — WMI `root/WMI`: okuma `WmiMonitorBrightness.CurrentBrightness`, yazma
`WmiMonitorBrightnessMethods.WmiSetBrightness(Timeout=1, Brightness)`. Yeni bağımlılık yok: pencere açmayan
(`CREATE_NO_WINDOW`) `powershell -NoProfile` + `Get-CimInstance`/`Invoke-CimMethod`. Yönetici izni gerekmiyor.
- Panel bazı yüzdeleri desteklemeyebilir ve yeni değeri gecikmeli bildirir → yazdıktan sonra 5 kez/150 ms aralıkla
  hedefe ulaşana kadar geri okunur (`_settle`).
- Alt sınır yüzde 5 (`MIN_LEVEL`): sıfır bazı panellerde ekranı karartır, sesle geri açmak isteyen ekranı göremez.
  Daha aşağısı istenirse bu söylenir.
- Gerçek panelde doğrulandı (Victus 16, CMN162D): okuma, %99'a yazıp geri okuma, %100'e geri alma.

**Tuzaklar / eksik:**
- Harici monitörde WMI sınıfı yoktur → "Bu ekranın parlaklığı yazılımla ayarlanamıyor" cümlesi. Harici monitör
  DDC/CI ister (`dxva2.SetVCPFeature` VCP 0x10) — ayrı iş.
- Her çağrı bir PowerShell başlatır (~0,5-1 sn); sesli kullanımda kabul edilebilir.

**Kaynak:** learn.microsoft.com/windows/win32/wmicoreprov/wmisetbrightness-method-in-class-wmimonitorbrightnessmethods ·
devblogs.microsoft.com/scripting/use-powershell-to-report-and-set-monitor-brightness/
