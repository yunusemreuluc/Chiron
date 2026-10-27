# Chiron MCP server

Exposes four read-only tools from Chiron (a Windows desktop voice assistant) over the
[Model Context Protocol](https://modelcontextprotocol.io), so Claude Code, Claude Desktop
or any MCP client can use them.

Everything runs locally: no API keys, no network calls. The server imports Chiron's
existing functions and wraps them — Chiron's own code is not modified.

## Tools

| Tool | What it does | Wraps |
|---|---|---|
| `read_screen_text` | OCR of the primary monitor (`source="screen"`) or an image file (`source="image"`, `image_path`). Turkish + English. Returns text in reading order plus per-line confidence and normalized boxes. | `actions/ocr.py` (EasyOCR), `actions/screen_vision.py` (mss) |
| `get_active_context` | Foreground app, window title, idle time. | `actions/ambient_context.py` (Win32) |
| `search_memory` | Accent/case-insensitive search over Chiron's long-term memory. | `memory/memory_manager.py` |
| `get_notifications` | Toast notifications waiting in the Windows Action Center. | `actions/notifications.py` (WinRT) |

All tools carry `readOnlyHint=true`, `destructiveHint=false`, `openWorldHint=false`
and return structured output with a JSON output schema.

### Safety boundary

- None of Chiron's confirmation-gated tools (`shell_run`, `manage_files`,
  `control_power`, `intervene_screen`, `delete_memory`, …) are exposed, and no tool
  takes a `confirm` parameter. `tests/test_contract.py` locks this in.
- `search_memory` never returns the `whatsapp_contacts` category (phone numbers).
- Screenshots taken for OCR are deleted from disk right after reading.
- Failures come back as MCP tool errors (`isError: true`) with a readable message;
  the server keeps running.

## Requirements

- Windows 10/11, Python 3.11
- Chiron's own dependencies (`requirements.txt` in the repo root: `easyocr`, `mss`,
  `winsdk`, `Pillow`, …)
- EasyOCR models in `~/.EasyOCR/model` (downloaded once on first Chiron OCR run)

## Install

From the repo root, in Chiron's virtualenv:

```powershell
venv\Scripts\python.exe -m pip install -r mcp_server\requirements.txt
```

Pinned: `mcp==2.2.0`. In the 2.x SDK, `FastMCP` was renamed to `MCPServer`
(`from mcp.server.mcpserver import MCPServer`); the decorator API is the same idea.

## Add to Claude Code

```powershell
claude mcp add --scope user chiron -- "<repo>\venv\Scripts\python.exe" "<repo>\mcp_server\server.py"
claude mcp get chiron   # should show: Status: ✔ Connected
```

## Add to Claude Desktop

Edit `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "chiron": {
      "command": "C:\\path\\to\\Chiron\\venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\Chiron\\mcp_server\\server.py"]
    }
  }
}
```

Restart Claude Desktop.

## Try it with MCP Inspector

```powershell
npx @modelcontextprotocol/inspector "<repo>\venv\Scripts\python.exe" "<repo>\mcp_server\server.py"
```

Or headless:

```powershell
npx @modelcontextprotocol/inspector --cli "<python>" "<server.py>" --method tools/list
```

## Tests

```powershell
venv\Scripts\python.exe -m pytest mcp_server
```

Tests talk to the server through a real in-process MCP client, so schema
validation and error mapping are covered, not just the Python functions. They are
deterministic: OCR runs on committed fixture images (`tests/fixtures/`, regenerated
by `make_fixtures.py`), while screen, window, notifications and memory are
monkeypatched. The real `memory.json` is never read, and any non-loopback network
connection fails the test.

If pytest cannot access your system temp folder, add `--basetemp <some-writable-dir>`.
