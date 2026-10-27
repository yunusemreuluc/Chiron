# MCP Server

Chiron'un dört salt-okunur aracını Model Context Protocol üzerinden (stdio) dışarı
açar — Claude Code, Claude Desktop veya herhangi bir MCP istemcisi kullanabilir.
Kod `mcp_server/`, kurulum ve kayıt komutları `mcp_server/README.md`.

| MCP aracı | Sardığı Chiron kodu |
|---|---|
| `read_screen_text` | [[OCR]] (`read_text_in_jpeg`) + [[Screen-Vision]] ekran yakalama |
| `get_active_context` | [[Ambient-Baglam]] (`read_context`) |
| `search_memory` | `memory/memory_manager.py` (`_entry_matches`) |
| `get_notifications` | [[Bildirimler-ve-Guc]] (`get_recent_notifications`) |

## Neden bunlar

Ölçüt: Claude'un kendi başına yapamadığı şey. Claude resim görebiliyor ve Claude
Code shell çalıştırabiliyor — o yüzden YOLO, `sys_info` elendi. Ekranı, aktif
pencereyi, Chiron'un hafızasını ve Windows bildirimlerini göremiyor.
`get_calendar_events`/`get_reminders` Windows'ta sadece tarayıcı açıyor, veri yok.

## Güvenlik sınırı

- İki adımlı onaylı (`confirm`) hiçbir araç açılmadı; `tests/test_contract.py` kilitliyor.
- `image_path`: UNC / ağ sürücüsü / ağa yönlenen bağlantı dosya sistemine
  dokunmadan reddedilir (UNC'ye `is_file()` bile NTLM özetini sızdırır).
- `search_memory`: `whatsapp_contacts` hiç dönmez, diğer kategorilerde telefon
  benzeri diziler (10–15 rakam) maskelenir.
- OCR okuyucusu MCP'de `download_enabled=False` ile kurulur — Chiron'un kendi
  `_get_reader()`'ı eksik modeli sessizce indiriyor ve hatayı yutuyor.

## Bilinen

- mcp 2.x'te `FastMCP` → `MCPServer` (`mcp.server.mcpserver`) olarak yeniden adlandırıldı.
- `screen_vision._capture_active_window` PNG kaydı başarısız olursa geçici dosyayı
  bırakıyor (Chiron'un kendi kodu, MCP tarafında düzeltilemez — ayrıca bakılmalı).
- Bu makinede pytest `%TEMP%\pytest-of-yunus`'a erişemiyor → `--basetemp` gerekiyor.
