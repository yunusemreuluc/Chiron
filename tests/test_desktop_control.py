"""Telefondan gelen PC medya komutları (K-018). Gerçek medyaya ve tuşlara dokunmaz — hepsi sahteyle değişir."""

from __future__ import annotations

import subprocess

import pytest

from actions import medya_kontrol as mk
from backend.core import desktop_control as dc


def session(app="Spotify.exe", status="Playing", title="Şarkı", artist="Sanatçı") -> dict:
    return {"app": app, "status": status, "title": title, "artist": artist, "current": False}


class Fake:
    """Oturumları tutar; komut gelince `effect` uygular. Gönderilen eylemleri ve basılan tuşları kaydeder."""

    def __init__(self, monkeypatch, sessions, effect=None, read_error=None):
        self.sessions = sessions
        self.effect = effect
        self.read_error = read_error
        self.verbs: list[str] = []
        self.keys: list[int] = []
        monkeypatch.setattr(mk, "read_sessions", self.read)
        monkeypatch.setattr(mk, "apply", self.apply)
        monkeypatch.setattr(dc, "_press_media_key", self.keys.append)

    def read(self):
        if self.read_error:
            raise self.read_error
        return mk._usable(self.sessions)

    def apply(self, verb, targets):
        self.verbs.append(verb)
        if self.effect:
            self.sessions = [self.effect(dict(s)) if s["app"] in targets else s for s in self.sessions]
        return list(targets), mk._usable(self.sessions)


def to_status(status):
    def effect(s):
        s["status"] = status
        return s

    return effect


def to_title(title):
    def effect(s):
        s["title"] = title
        return s

    return effect


def test_play_pause_pauses_what_is_playing_without_a_key(monkeypatch):
    fake = Fake(monkeypatch, [session()], effect=to_status("Paused"))
    success, message = dc.execute("media_play_pause")
    assert success and "Durduruldu" in message and "Spotify" in message
    assert fake.verbs == ["pause"] and fake.keys == []


def test_play_pause_resumes_when_nothing_is_playing(monkeypatch):
    fake = Fake(monkeypatch, [session(status="Paused")], effect=to_status("Playing"))
    success, message = dc.execute("media_play_pause")
    assert success and "Devam ediyor" in message
    assert fake.verbs == ["play"] and fake.keys == []


def test_play_pause_with_two_players_silences_both(monkeypatch):
    """Kör tuş birini durdurup ötekini başlatabilirdi; burada çalan ne varsa durur."""
    fake = Fake(
        monkeypatch,
        [session(), session(app="chrome.exe", status="Paused", title="Video")],
        effect=to_status("Paused"),
    )
    success, _ = dc.execute("media_play_pause")
    assert success and fake.verbs == ["pause"]
    assert all(s["status"] == "Paused" for s in fake.sessions)


def test_failed_pause_is_reported_as_failure(monkeypatch):
    fake = Fake(monkeypatch, [session()])  # komut gidiyor ama oturum hâlâ çalıyor
    success, message = dc.execute("media_play_pause")
    assert not success and "hâlâ çalıyor" in message
    assert fake.keys == []


@pytest.mark.parametrize("action,verb", [("media_next", "next"), ("media_previous", "previous")])
def test_track_change_reports_the_new_title(monkeypatch, action, verb):
    fake = Fake(monkeypatch, [session()], effect=to_title("Yeni Parça"))
    success, message = dc.execute(action)
    assert success and "Yeni Parça" in message
    assert fake.verbs == [verb] and fake.keys == []


def test_next_does_not_claim_a_change_when_title_stays(monkeypatch):
    Fake(monkeypatch, [session()])
    _, message = dc.execute("media_next")
    assert "değişmedi" in message


@pytest.mark.parametrize(
    "action,key",
    [
        ("media_play_pause", dc.VK_MEDIA_PLAY_PAUSE),
        ("media_next", dc.VK_MEDIA_NEXT_TRACK),
        ("media_previous", dc.VK_MEDIA_PREV_TRACK),
    ],
)
def test_no_session_falls_back_to_key_and_says_it_is_unknown(monkeypatch, action, key):
    fake = Fake(monkeypatch, [])
    success, message = dc.execute(action)
    assert success and "bilmiyorum" in message
    assert fake.keys == [key] and fake.verbs == []


@pytest.mark.parametrize(
    "error",
    [OSError("powershell yok"), ValueError("bozuk json"), subprocess.TimeoutExpired("powershell", 15)],
)
def test_read_failure_falls_back_to_key_and_says_it_is_unverified(monkeypatch, error):
    fake = Fake(monkeypatch, [session()], read_error=error)
    success, message = dc.execute("media_next")
    assert success and "doğrulayamadım" in message
    assert fake.keys == [dc.VK_MEDIA_NEXT_TRACK] and fake.verbs == []


def test_whitelist_is_unchanged_and_unknown_actions_are_refused():
    assert dc.ACTIONS == ("lock", "sleep", "media_play_pause", "media_next", "media_previous", "clipboard")
    assert dc.execute("shutdown") == (False, "Bilinmeyen komut: shutdown")
