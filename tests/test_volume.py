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


# --- Uygulama başına ses (K-012) ---

def test_match_app_prefers_exact_then_contains():
    names = ["Spotify", "chrome", "msedge", "msedgewebview2"]
    assert volume.match_app("Spotify'ı", names) == ["Spotify"]  # Türkçe ek atılır
    assert volume.match_app("SPOTIFY.exe", names) == ["Spotify"]
    assert volume.match_app("Microsoft Edge", names) == []  # yanlışlıkla eşleşmez — liste döner
    assert volume.match_app("edge", names) == ["msedge", "msedgewebview2"]  # belirsiz
    assert volume.match_app("msedge", names) == ["msedge"]  # tam eşleşme içermeyi yener
    assert volume.match_app("Discord", ["Discord", "Discord"]) == ["Discord"]  # tekrarsız
    assert volume.match_app("İTunes", ["iTunes"]) == ["iTunes"]  # Türkçe büyük İ
    assert volume.match_app("  ", names) == []


class _FakeSessions:
    def __init__(self, sessions):
        self.sessions = sessions

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None


class _FakeApp(_FakeEndpoint):
    def __init__(self, name, level=100, muted=False):
        super().__init__(level=level, muted=muted)
        self.name = name


def test_app_volume_changes_only_that_app(monkeypatch):
    spotify_a, spotify_b, chrome = _FakeApp("Spotify", 80), _FakeApp("Spotify", 60), _FakeApp("chrome", 70)
    monkeypatch.setattr(volume, "_AppSessions", lambda: _FakeSessions([spotify_a, chrome, spotify_b]))
    result = volume.set_volume("down", step=30, app="spotify")
    assert result["success"]
    assert result["message"] == "Spotify sesi yüzde 50."  # en yüksek oturum 80 → 50, hepsi aynı
    assert (spotify_a.level(), spotify_b.level(), chrome.level()) == (50, 50, 70)
    assert result["data"] == {"level": 50, "muted": False, "app": "Spotify"}

    result = volume.set_volume("mute", app="Spotify")
    assert result["message"] == "Spotify sesi yüzde 50, sessizde."
    assert not chrome.muted()


def test_app_volume_missing_or_ambiguous_lists_apps(monkeypatch):
    sessions = [_FakeApp("chrome"), _FakeApp("msedge"), _FakeApp("msedgewebview2")]
    monkeypatch.setattr(volume, "_AppSessions", lambda: _FakeSessions(sessions))
    missing = volume.set_volume("down", app="Spotify")
    assert not missing["success"] and missing["data"]["apps"] == ["chrome", "msedge", "msedgewebview2"]
    assert "Ses çıkaranlar: chrome, msedge, msedgewebview2." in missing["message"]
    ambiguous = volume.set_volume("down", app="edge")
    assert not ambiguous["success"] and ambiguous["data"]["apps"] == ["msedge", "msedgewebview2"]
    assert all(s.level() == 100 for s in sessions)  # belirsizken hiçbirine dokunulmaz


def test_blank_app_means_master_volume(monkeypatch):
    monkeypatch.setattr(volume, "_Endpoint", lambda: _FakeEndpoint(level=40))
    monkeypatch.setattr(volume, "_AppSessions", lambda: pytest.fail("ana ses için oturumlara bakılmamalı"))
    assert volume.set_volume("get", app="  ")["message"] == "Ses yüzde 40."


def test_app_parameter_is_declared():
    from tool_defs import TOOL_DECLARATIONS

    decl = next(d for d in TOOL_DECLARATIONS if d["name"] == "set_volume")
    assert "app" in decl["parameters"]["properties"]
