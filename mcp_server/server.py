"""
Airon MCP server — Airon'un dört salt-okunur aracını Model Context Protocol
üzerinden (stdio) dışarı açar.

Çalıştırma:  venv\\Scripts\\python.exe -m mcp_server
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path
from typing import Annotated, Literal

# Claude Code / Desktop server'ı dosya yoluyla ve KENDİ çalışma klasöründen
# başlatıyor (`python <repo>/mcp_server/server.py`). O durumda sys.path[0]
# mcp_server/ olur, repo kökü değil — `mcp_server` paketi bulunamıyordu.
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

# stdio transport'ta stdout PROTOKOLÜN kendisi: oraya yazılan tek bir satır
# istemcinin JSON-RPC ayrıştırmasını bozar. mcp 2.x servis sırasında fd 1'i
# zaten stderr'e çeviriyor, ama Airon modülleri run()'dan ÖNCE import ediliyor —
# import anında bir şey basan bir kütüphane olursa diye o pencereyi de kapatıyoruz.
with contextlib.redirect_stdout(sys.stderr):
    from mcp_server import tools

# Hepsi salt-okunur: Claude Code / Desktop bu ipuçlarına bakarak onay isteyip
# istemeyeceğine karar verebiliyor. openWorldHint=False: ağa çıkan araç yok.
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

server = MCPServer(
    name="airon",
    title="Airon local tools",
    version="0.1.0",
    instructions=(
        "Read-only tools from Airon, a Windows desktop assistant. They run fully "
        "locally (no API keys, no network). Use read_screen_text to see what is on the "
        "user's screen, get_active_context to learn which app they are in, "
        "search_memory to recall facts Airon stored about them, and "
        "get_notifications for pending Windows notifications."
    ),
)


@server.tool(annotations=READ_ONLY)
async def read_screen_text(
    source: Annotated[
        Literal["screen", "image"],
        Field(description="'screen' captures the primary monitor now; 'image' reads the file at image_path."),
    ] = "screen",
    image_path: Annotated[
        str | None,
        Field(description="Absolute path to a PNG/JPG/BMP/WEBP/TIFF file. Required when source='image'."),
    ] = None,
) -> tools.ReadTextResult:
    """Read text from the user's screen or from an image file using local OCR (EasyOCR, Turkish + English).

    Returns the text in reading order plus each line with its confidence and a
    normalized bounding box. The first call loads the OCR model and takes a few
    seconds; later calls take about one second per image.
    """
    # OCR CPU'da saniyeler sürüyor — event loop'u bloklamamak için thread'de.
    return await anyio.to_thread.run_sync(tools.read_text, source, image_path)


@server.tool(annotations=READ_ONLY)
async def get_active_context() -> tools.ActiveContext:
    """Return what the user is doing right now: foreground app, window title and how long they have been idle.

    Use it to resolve references like "this file" or "the window I'm in".
    """
    return await anyio.to_thread.run_sync(tools.active_context)


@server.tool(annotations=READ_ONLY)
async def search_memory(
    query: Annotated[str, Field(min_length=2, max_length=200, description="Words to look for, Turkish or English.")],
    limit: Annotated[int, Field(ge=1, le=50, description="Maximum number of matches.")] = 10,
) -> tools.MemorySearchResult:
    """Search the long-term memory Airon keeps about the user (name, preferences, projects, notes, learned objects).

    Matching is accent- and case-insensitive. Contact phone numbers are never returned.
    """
    return await anyio.to_thread.run_sync(tools.search_memory, query, limit)


@server.tool(annotations=READ_ONLY)
async def get_notifications(
    limit: Annotated[int, Field(ge=1, le=50, description="Maximum number of notifications.")] = 10,
) -> tools.NotificationsResult:
    """List the toast notifications currently waiting in the Windows Action Center (app, title, message)."""
    return await tools.recent_notifications(limit)


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
