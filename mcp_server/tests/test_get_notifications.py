from __future__ import annotations

import pytest

from actions import notifications
from actions.tool_result import fail, ok
from mcp_server.tests.conftest import error_text

pytestmark = pytest.mark.anyio


def fake_listener(result, calls=None):
    async def get_recent_notifications(limit: int = 10) -> dict:
        if calls is not None:
            calls.append(limit)
        return result

    return get_recent_notifications


async def test_lists_notifications(client, monkeypatch):
    items = [
        {"id": 1, "app": "Outlook", "title": "Toplantı", "message": "15:00 — Sprint review"},
        {"id": 2, "app": "Discord", "title": "Yeni mesaj", "message": ""},
    ]
    calls: list[int] = []
    monkeypatch.setattr(notifications, "get_recent_notifications", fake_listener(ok("2 bildirim", notifications=items), calls))

    result = await client.call_tool("get_notifications", {"limit": 5})

    assert not result.is_error
    assert calls == [5]
    data = result.structured_content
    assert data["count"] == 2
    assert data["notifications"][0] == {"app": "Outlook", "title": "Toplantı", "message": "15:00 — Sprint review"}


async def test_empty_action_center(client, monkeypatch):
    monkeypatch.setattr(notifications, "get_recent_notifications", fake_listener(ok("yok", notifications=[])))
    result = await client.call_tool("get_notifications", {})
    assert not result.is_error
    assert result.structured_content == {"count": 0, "notifications": []}


async def test_permission_denied_is_reported(client, monkeypatch):
    denied = fail("Bildirimlere erişim izni verilmedi.")
    monkeypatch.setattr(notifications, "get_recent_notifications", fake_listener(denied))
    result = await client.call_tool("get_notifications", {})
    assert "erişim izni verilmedi" in error_text(result)


@pytest.mark.parametrize("limit", [0, 51, -3])
async def test_limit_out_of_range_rejected(client, limit):
    result = await client.call_tool("get_notifications", {"limit": limit})
    assert "limit" in error_text(result)
