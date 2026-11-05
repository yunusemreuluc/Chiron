"""Pencere yönetimi (manage_window, K-015). Gerçek pencerelere dokunmaz — liste ve eylem sahteyle değişir."""

from __future__ import annotations

from pathlib import Path

import pytest

from actions import windows
from actions.windows import Window

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CHROME = Window(1, "YouTube - Google Chrome", "chrome", 10)
SPOTIFY = Window(2, "Spotify Premium", "spotify", 20)
CODE = Window(3, "chrome-notes.md - Visual Studio Code", "code", 30)


@pytest.fixture
def desk(monkeypatch):
    state = {"windows": [CODE, CHROME, SPOTIFY], "applied": [], "result": True, "fg": 0}

    def apply(action, win):
        state["applied"].append((action, win.process))
        return state["result"]

    monkeypatch.setattr(windows.sys, "platform", "win32")
    monkeypatch.setattr(windows, "list_windows", lambda: list(state["windows"]))
    monkeypatch.setattr(windows, "apply", apply)
    monkeypatch.setattr(windows, "foreground", lambda: state["fg"])
    return state


def test_pick_prefers_process_name_over_title():
    # "chrome" başlığında geçen VS Code penceresi değil, Chrome'un kendisi seçilmeli.
    assert windows.pick([CODE, CHROME], "Chrome") == [CHROME, CODE]
    assert windows.pick([CODE, CHROME, SPOTIFY], "tarayıcı") == [CHROME]
    assert windows.pick([CODE, CHROME], "VS Code") == [CODE]
    assert windows.pick([CHROME], "youtube") == [CHROME]
    assert windows.pick([CHROME], "  ") == []


def test_list_reports_apps(desk):
    result = windows.manage_window("list")
    assert result["success"]
    assert "3 pencere" in result["message"] and "spotify" in result["message"]
    assert desk["applied"] == []


def test_action_targets_named_app(desk):
    result = windows.manage_window("minimize", "Spotify")
    assert result["success"]
    assert desk["applied"] == [("minimize", "spotify")]
    assert "küçülttüm" in result["message"]


def test_missing_app_lists_open_ones_and_does_nothing(desk):
    result = windows.manage_window("close", "discord")
    assert not result["success"]
    assert "chrome" in result["message"] and "spotify" in result["message"]
    assert desk["applied"] == []


def test_without_app_uses_foreground_window(desk):
    desk["fg"] = SPOTIFY.hwnd
    assert windows.manage_window("maximize")["success"]
    assert desk["applied"] == [("maximize", "spotify")]


def test_without_app_and_unknown_foreground_asks(desk):
    desk["fg"] = 999  # Chiron'un kendi penceresi ya da masaüstü — listede yok
    result = windows.manage_window("close")
    assert not result["success"]
    assert desk["applied"] == []


def test_unverified_close_is_not_reported_as_done(desk):
    desk["result"] = False  # uygulama "kaydedilsin mi?" sordu, pencere açık kaldı
    result = windows.manage_window("close", "code")
    assert not result["success"]
    assert "kapattım" not in result["message"] and "hâlâ açık" in result["message"]


def test_show_desktop_minimizes_all(desk, monkeypatch):
    monkeypatch.setattr(windows, "minimize_all", lambda ws: len(ws))
    result = windows.manage_window("show_desktop")
    assert result["success"] and result["data"]["count"] == 3


def test_unknown_action(desk):
    assert not windows.manage_window("fly", "chrome")["success"]


def test_registered_everywhere():
    """CLAUDE.md § Adding a new tool: dört yerin hepsi."""
    assert "manage_window" in (PROJECT_ROOT / "tool_defs.py").read_text(encoding="utf-8")
    assert "manage_window" in (PROJECT_ROOT / "core" / "prompt.txt").read_text(encoding="utf-8")
    assert "actions.windows" in (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
    assert (PROJECT_ROOT / "Notes" / "Araclar" / "Pencereler.md").exists()
