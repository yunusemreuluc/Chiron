"""Server'ın dışarıya ne açtığına dair sözleşme — güvenlik sınırı burada kilitli."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.anyio

EXPECTED_TOOLS = {"read_screen_text", "get_active_context", "search_memory", "get_notifications"}

# Chiron'da iki adımlı onay (confirm=false → confirm=true) isteyen ya da fare/
# klavye/dosya/güç üzerinde etkisi olan araçlar. Hiçbiri MCP'de görünmemeli.
CHIRON_GATED_TOOLS = {
    "shell_run", "manage_files", "control_power", "intervene_screen", "delete_memory",
    "delete_calendar_event", "gemini_desktop_task", "send_whatsapp_message",
    "save_memory", "save_whatsapp_contact", "open_app", "browser_control", "play_media",
}


async def test_exposes_exactly_the_approved_tools(client):
    tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == EXPECTED_TOOLS


async def test_no_gated_chiron_tool_and_no_confirm_parameter(client):
    tools = (await client.list_tools()).tools
    assert not {t.name for t in tools} & CHIRON_GATED_TOOLS
    for tool in tools:
        assert "confirm" not in tool.input_schema.get("properties", {}), tool.name


async def test_every_tool_is_marked_read_only_and_documented(client):
    for tool in (await client.list_tools()).tools:
        assert tool.annotations.read_only_hint is True, tool.name
        assert tool.annotations.destructive_hint is False, tool.name
        assert tool.annotations.open_world_hint is False, tool.name
        assert tool.description and len(tool.description) > 30, tool.name
        assert tool.output_schema and tool.output_schema.get("properties"), tool.name


async def test_unknown_tool_is_an_error_not_a_crash(client):
    result = await client.call_tool("shell_run", {"command": "dir"})
    assert result.is_error
    # Server hâlâ ayakta mı: sonraki çağrı çalışmalı.
    assert len((await client.list_tools()).tools) == len(EXPECTED_TOOLS)


async def test_network_guard_catches_swallowed_attempts(no_network):
    # Ağ korumasının kendisinin testi: hatayı yutan kod bile kayda geçmeli.
    import socket

    try:
        socket.create_connection(("example.com", 80), timeout=1)
    except Exception:
        pass  # OCR gibi hatayı yutan bir katmanı taklit ediyor
    assert no_network, "Yutulan ağ denemesi kaydedilmedi"
    no_network.clear()  # bu test bilerek denedi; teardown'da düşmesin
