from __future__ import annotations

import pytest

from actions import ambient_context
from mcp_server.tests.conftest import error_text

pytestmark = pytest.mark.anyio

FAKE_CONTEXT = {
    "window_title": "server.py",
    "process": "Code.exe",
    "app": "Visual Studio Code",
    "idle_seconds": 3.0,
    "away": False,
    "time": "14:05",
    "date": "28.09.2026 Pazartesi",
}


async def test_returns_foreground_app(client, monkeypatch):
    monkeypatch.setattr(ambient_context, "read_context", lambda: dict(FAKE_CONTEXT))
    result = await client.call_tool("get_active_context", {})
    assert not result.is_error
    data = result.structured_content
    assert data["app"] == "Visual Studio Code"
    assert data["window_title"] == "server.py"
    assert data["away"] is False
    # Özet Chiron'un kendi describe_context'inden geliyor.
    assert "Visual Studio Code" in data["summary"]


async def test_win32_failure_is_reported(client, monkeypatch):
    def boom():
        raise OSError("GetForegroundWindow başarısız")

    monkeypatch.setattr(ambient_context, "read_context", boom)
    result = await client.call_tool("get_active_context", {})
    assert "Aktif pencere bilgisi okunamadı" in error_text(result)

