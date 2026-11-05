"""Ekran parlaklığı (set_brightness, K-013). Gerçek panele dokunmaz — okuma/yazma sahteyle değişir."""

from __future__ import annotations

from pathlib import Path

import pytest

from actions import brightness

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class FakePanel:
    """Bazı yüzdeleri desteklemeyen panel: yazılanı 10'un katına yuvarlayarak bildirir."""

    def __init__(self, level: int, rounding: int = 1):
        self.level = level
        self.rounding = rounding
        self.writes: list[int] = []

    def read(self) -> int:
        return self.level

    def write(self, level: int) -> None:
        self.writes.append(level)
        self.level = round(level / self.rounding) * self.rounding


@pytest.fixture
def panel(monkeypatch):
    fake = FakePanel(60)
    monkeypatch.setattr(brightness, "read_level", fake.read)
    monkeypatch.setattr(brightness, "write_level", fake.write)
    monkeypatch.setattr(brightness.time, "sleep", lambda _s: None)
    return fake


def test_plan_steps_and_clamps():
    assert brightness.plan("get", 50, None, None) is None
    assert brightness.plan("down", 50, None, None) == 40
    assert brightness.plan("up", 95, None, 20) == 100
    assert brightness.plan("down", 8, None, None) == brightness.MIN_LEVEL
    assert brightness.plan("set", 50, 0, None) == brightness.MIN_LEVEL
    assert brightness.plan("set", 50, 140, None) == 100
    with pytest.raises(ValueError):
        brightness.plan("set", 50, None, None)
    with pytest.raises(ValueError):
        brightness.plan("blink", 50, None, None)


def test_get_does_not_write(panel):
    result = brightness.set_brightness("get")
    assert result == {"success": True, "message": "Ekran parlaklığı yüzde 60.", "data": {"level": 60}}
    assert panel.writes == []


def test_down_writes_and_reports_readback(panel):
    panel.rounding = 25  # panel 45'i desteklemiyor, 50 bildiriyor
    result = brightness.set_brightness("down", step=15)
    assert panel.writes == [45]
    assert result["data"]["level"] == 50
    assert result["message"] == "Ekran parlaklığı yüzde 50."


def test_asking_for_black_screen_is_floored_and_said(panel):
    result = brightness.set_brightness("set", level=0)
    assert panel.writes == [brightness.MIN_LEVEL]
    assert "kararmasın" in result["message"]


def test_unsupported_panel_is_spoken_not_raised(monkeypatch):
    def unsupported():
        raise brightness.Unsupported("Not supported")

    monkeypatch.setattr(brightness, "read_level", unsupported)
    result = brightness.set_brightness("down")
    assert not result["success"]
    assert "harici monitör" in result["message"]


def test_missing_level_is_a_spoken_error(panel):
    assert not brightness.set_brightness("set")["success"]
    assert panel.writes == []


def test_tool_is_declared_and_prompted():
    from tool_defs import TOOL_DECLARATIONS

    decl = next(d for d in TOOL_DECLARATIONS if d["name"] == "set_brightness")
    assert set(decl["parameters"]["properties"]) == {"action", "level", "step"}
    prompt = (PROJECT_ROOT / "core" / "prompt.txt").read_text(encoding="utf-8")
    assert "set_brightness" in prompt
