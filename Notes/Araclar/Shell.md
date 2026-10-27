---
tags: [chiron, arac]
---

# Shell — actions/shell.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Mimari]]

`shell_run(command, timeout=30)` — `subprocess.run(command, shell=True, ...)` ile cmd/PowerShell
komutu çalıştırır. Çıktı 800 karakterle kırpılır.

`BLOCKED` listesiyle basit bir güvenlik filtresi var (`format c:`, `shutdown`, `diskpart`,
`bcdedit`, `net user administrator`, `reg delete hklm` vb. — alt-string eşleşmesi, case-insensitive
ama kolayca atlatılabilir çünkü tam komut değil substring kontrolü yapıyor). Bu bir güvenlik
sınırı değil, kaza önleyici; `shell=True` ile keyfi komut çalıştırma riski hâlâ var.

Tool: `shell_run` ([[Arac-Tanimlari]]).
