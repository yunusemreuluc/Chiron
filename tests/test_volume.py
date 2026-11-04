"""PC ses seviyesi (set_volume, K-011). Gerçek aygıta dokunmaz — `_Endpoint` sahtesiyle."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from actions import volume  # noqa: E402


def test_plan_clamps_and_unmutes_when_raising():
    assert volume.plan("set", 50, 30, None) == (30, False)
    assert volume.plan("set", 50, 150.0, None) == (100, False)  # NUMBER float gelebilir, 100'e kırpılır
    assert volume.plan("set", 50, 0, None) == (0, None)  # sıfıra çekmek sessiz durumunu değiştirmez
    assert volume.plan("up", 95, None, None) == (100, False)
    assert volume.plan("down", 3, None, 5) == (0, None)
    assert volume.plan("down", 40, None, -20) == (20, None)  # işaret karışırsa yine kısar
    assert volume.plan("mute", 40, None, None) == (None, True)
    assert volume.plan("unmute", 40, None, None) == (None, False)
    assert volume.plan("get", 40, None, None) == (None, None)


def test_plan_rejects_bad_input():
    with pytest.raises(ValueError):
        volume.plan("set", 50, None, None)
    with pytest.raises(ValueError):
        volume.plan("zıpla", 50, None, None)


class _FakeEndpoint:
    def __init__(self, level=40, muted=False, ignore_writes=False):
        self._level, self._muted, self._ignore = level, muted, ignore_writes

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def level(self):
        return self._level

    def muted(self):
        return self._muted

    def set_level(self, percent):
        if not self._ignore:
            self._level = percent

    def set_muted(self, muted):
        if not self._ignore:
            self._muted = muted


def test_set_volume_reports_device_readback(monkeypatch):
    fake = _FakeEndpoint(level=40, muted=True)
    monkeypatch.setattr(volume, "_Endpoint", lambda: fake)
    result = volume.set_volume("up", step=15)
    assert result["success"] and result["data"] == {"level": 55, "muted": False}
    assert result["message"] == "Ses yüzde 55."


def test_set_volume_says_what_is_not_what_was_asked(monkeypatch):
    # Aygıt yazmayı yok sayarsa söylenen değer istenen 80 değil, gerçekte olan 40'tır.
    monkeypatch.setattr(volume, "_Endpoint", lambda: _FakeEndpoint(level=40, muted=True, ignore_writes=True))
    result = volume.set_volume("set", level=80)
    assert result["data"] == {"level": 40, "muted": True}
    assert result["message"] == "Ses yüzde 40, sessizde."


def test_set_volume_errors_are_spoken_not_raised(monkeypatch):
    def no_device():
        raise OSError("Varsayılan hoparlör başarısız", volume._HRESULT_NOT_FOUND)

    monkeypatch.setattr(volume, "_Endpoint", no_device)
    assert volume.set_volume("get") == {
        "success": False, "message": "PC'de etkin bir hoparlör ya da kulaklık bulunamadı.", "data": {}}
    monkeypatch.setattr(volume, "_Endpoint", lambda: _FakeEndpoint())
    assert not volume.set_volume("set")["success"]  # seviye söylenmedi


def test_tool_is_declared():
    from tool_defs import TOOL_DECLARATIONS

    names = {decl["name"] for decl in TOOL_DECLARATIONS}
    assert "set_volume" in names
    prompt = (PROJECT_ROOT / "core" / "prompt.txt").read_text(encoding="utf-8")
    assert "set_volume" in prompt
