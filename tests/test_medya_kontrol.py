"""Medya kontrolü (control_media, K-016). Gerçek medyaya dokunmaz — oturumlar ve komutlar sahteyle değişir."""

from __future__ import annotations

from pathlib import Path

import pytest

from actions import medya_kontrol as mk

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def session(app="Spotify.exe", status="Playing", title="Şarkı", artist="Sanatçı", current=False) -> dict:
    return {"app": app, "status": status, "title": title, "artist": artist, "current": current}


class FakeWindows:
    """Oturumları tutar; komut gelince `effect` ile değiştirir, ne gönderildiğini kaydeder."""

    def __init__(self, sessions, accept=True, effect=None):
        self.sessions = sessions
        self.accept = accept
        self.effect = effect
        self.calls: list[tuple[str, list[str]]] = []

    def read(self):
        return mk._usable(self.sessions)

    def apply(self, verb, targets):
        self.calls.append((verb, targets))
        if not self.accept:
            return [], mk._usable(self.sessions)
        if self.effect:
            self.sessions = [self.effect(dict(s)) if s["app"] in targets else s for s in self.sessions]
        return list(targets), mk._usable(self.sessions)


def install(monkeypatch, fake: FakeWindows) -> FakeWindows:
    monkeypatch.setattr(mk, "read_sessions", fake.read)
    monkeypatch.setattr(mk, "apply", fake.apply)
    return fake


def set_status(status):
    def effect(item):
        item["status"] = status
        return item
    return effect


def test_friendly_names():
    assert mk.friendly("Spotify.exe") == "Spotify"
    assert mk.friendly("SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify") == "Spotify"
    assert mk.friendly("MSEdge") == "Edge"
    assert mk.friendly("Chrome") == "Chrome"
    assert mk.friendly("Chrome._crx_abcdef") == "Chrome"


def test_own_and_closed_sessions_are_never_targets():
    raw = [session("Chiron"), session("python.exe"), session("Microsoft.WebView2!msedgewebview2"),
           session("Spotify.exe", status="Closed"), session("Chrome")]
    assert [s["app"] for s in mk._usable(raw)] == ["Chrome"]


def test_title_is_single_line_and_bounded():
    cleaned = mk._usable([session(title="satır\n bir\t" + "x" * 500)])[0]["title"]
    assert "\n" not in cleaned and len(cleaned) == mk._TITLE_LIMIT


def test_choose_pause_hits_everything_playing_only():
    a, b, c = session("A"), session("B"), session("C", status="Paused")
    assert mk.choose("pause", [a, b, c]) == [a, b]
    assert mk.choose("pause", [c]) == []


def test_choose_single_target_prefers_playing_then_current():
    playing = session("A", status="Playing")
    paused_current = session("B", status="Paused", current=True)
    assert mk.choose("next", [paused_current, playing]) == [playing]
    assert mk.choose("play", [paused_current, session("C", status="Paused")]) == [paused_current]
    assert mk.choose("play", [paused_current, playing]) == []


def test_browser_words_match_browser_sessions():
    chrome, spotify = session("Chrome"), session("Spotify.exe")
    assert mk.matches("youtube", chrome) and not mk.matches("youtube", spotify)
    assert mk.matches("Spotify", spotify) and not mk.matches("spotify", chrome)


def test_status_reads_without_sending_commands(monkeypatch):
    fake = install(monkeypatch, FakeWindows([session(title="Gülümse", artist="Sezen Aksu")]))
    result = mk.control_media("status")
    assert result["success"] and "çalıyor" in result["message"] and "Gülümse" in result["message"]
    assert fake.calls == []


def test_pause_confirmed_by_readback(monkeypatch):
    fake = install(monkeypatch, FakeWindows([session()], effect=set_status("Paused")))
    result = mk.control_media("pause")
    assert result["success"] and result["message"] == "Durduruldu: Spotify."
    assert fake.calls == [("pause", ["Spotify.exe"])]


def test_pause_that_did_not_stop_is_not_claimed(monkeypatch):
    install(monkeypatch, FakeWindows([session()]))  # kabul etti ama hâlâ çalıyor
    result = mk.control_media("pause")
    assert not result["success"] and "hâlâ çalıyor" in result["message"]


def test_refused_command_is_a_failure(monkeypatch):
    install(monkeypatch, FakeWindows([session()], accept=False))
    result = mk.control_media("next")
    assert not result["success"] and "kabul etmedi" in result["message"]


def test_already_paused_sends_nothing(monkeypatch):
    fake = install(monkeypatch, FakeWindows([session(status="Paused")]))
    result = mk.control_media("pause")
    assert result["success"] and "Zaten çalmıyor" in result["message"]
    assert fake.calls == []


def test_already_playing_sends_nothing(monkeypatch):
    fake = install(monkeypatch, FakeWindows([session()]))
    assert "Zaten çalıyor" in mk.control_media("play")["message"]
    assert fake.calls == []


def test_next_reports_new_title(monkeypatch):
    def advance(item):
        item["title"], item["artist"] = "Yeni", "Biri"
        return item

    install(monkeypatch, FakeWindows([session()], effect=advance))
    result = mk.control_media("next")
    assert result["message"] == "Şimdi: «Yeni», Biri." and result["data"]["changed"] is True


def test_previous_with_same_title_is_said_honestly(monkeypatch):
    install(monkeypatch, FakeWindows([session()]))
    result = mk.control_media("previous")
    assert result["success"] and result["data"]["changed"] is False and "değişmedi" in result["message"]


def test_named_app_only_touches_that_app(monkeypatch):
    fake = install(monkeypatch, FakeWindows(
        [session("Chrome"), session("Spotify.exe")], effect=set_status("Paused")))
    assert mk.control_media("pause", app="spotify")["success"]
    assert fake.calls == [("pause", ["Spotify.exe"])]
    assert fake.sessions[0]["status"] == "Playing"


def test_unknown_app_lists_what_is_open(monkeypatch):
    fake = install(monkeypatch, FakeWindows([session("Chrome")]))
    result = mk.control_media("pause", app="discord")
    assert not result["success"] and "Chrome" in result["message"]
    assert fake.calls == []


def test_nothing_open_is_spoken(monkeypatch):
    install(monkeypatch, FakeWindows([]))
    assert mk.control_media("status")["success"]
    assert not mk.control_media("next")["success"]


def test_unknown_action_and_synonym(monkeypatch):
    fake = install(monkeypatch, FakeWindows([session()], effect=set_status("Paused")))
    assert not mk.control_media("explode")["success"]
    assert mk.control_media("stop")["success"]  # eşanlam → pause
    assert fake.calls[0][0] == "pause"


def test_powershell_failure_is_spoken_not_raised(monkeypatch):
    def broken():
        raise OSError("WinRT yok")

    monkeypatch.setattr(mk, "read_sessions", broken)
    result = mk.control_media("pause")
    assert not result["success"] and "WinRT yok" in result["message"]


def test_values_never_embedded_in_script(monkeypatch):
    """Hedef adı betiğe değil ortam değişkenine gider: PowerShell enjeksiyonu yolu yok."""
    seen = {}

    class Done:
        returncode = 0
        stdout = '{"accepted":[],"sessions":[]}'
        stderr = ""

    def fake_run(cmd, **kwargs):
        seen["script"], seen["env"] = cmd[-1], kwargs["env"]
        return Done()

    monkeypatch.setattr(mk.subprocess, "run", fake_run)
    evil = "x'; Remove-Item C:\\ -Recurse; '"
    mk.apply("pause", [evil])
    assert "Remove-Item" not in seen["script"]
    assert "Remove-Item" in seen["env"]["CHIRON_MEDIA_TARGETS"]


def test_tool_is_declared_and_prompted():
    from tool_defs import TOOL_DECLARATIONS

    decl = next(d for d in TOOL_DECLARATIONS if d["name"] == "control_media")
    assert set(decl["parameters"]["properties"]) == {"action", "app"}
    prompt = (PROJECT_ROOT / "core" / "prompt.txt").read_text(encoding="utf-8")
    assert "control_media" in prompt
    assert (PROJECT_ROOT / "Notes" / "Araclar" / "Medya-Kontrol.md").exists()


@pytest.mark.parametrize("word", ["youtube", "Tarayıcı"])
def test_browser_word_without_browser_open(monkeypatch, word):
    install(monkeypatch, FakeWindows([session("Spotify.exe")]))
    assert not mk.control_media("pause", app=word)["success"]
