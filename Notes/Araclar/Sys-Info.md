---
tags: [chiron, arac]
---

# Sys-Info — actions/sys_info.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Mimari]]

`sys_info(query)` — `battery/cpu/ram/disk/time/date/network/all` sorgularını destekler.
`psutil` varsa onu kullanır, yoksa PowerShell/`wmic`/`netsh`/`ipconfig` fallback'leri devreye girer
(`_battery, _cpu, _ram, _disk, _network`). WiFi SSID `netsh wlan show interfaces` ile okunur.

Tool: `sys_info`. `main.py._focus_ui_section_for_tool` bu aracın sonucuna göre UI panelini
odaklar (`time` sorgusu → "time" paneli, diğerleri → "system" paneli) — [[Arayuz]].
