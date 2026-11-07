from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core import commands
from core import otomatik_tepsi as ot


@pytest.fixture()
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr(ot, "_hold_until", 0.0)
    monkeypatch.setattr(ot, "_last_sent", -100.0)
    monkeypatch.setattr(ot, "enabled", lambda: True)
    monkeypatch.setattr(commands, "dispatch", lambda name, payload: calls.append(name) or True)
    return calls


@pytest.mark.parametrize("text", ["", "hmm", "<noise>", "<noise> ııı", "[müzik]", "a b c"])
def test_noise_does_not_count_as_speech(text):
    assert not ot.real_speech(text)


@pytest.mark.parametrize("text", ["bu ne", "Word'de tablo nasıl eklenir", "<noise> dosya nerede"])
def test_real_speech_counts(text):
    assert ot.real_speech(text)


def test_speech_sends_tray_command(sent):
    assert ot.on_user_speech("dosya nerede", now=100.0)
    assert sent == ["tray"]


def test_noise_keeps_window_open(sent):
    assert not ot.on_user_speech("<noise>", now=100.0)
    assert sent == []


def test_transcript_chunks_do_not_spam(sent):
    ot.on_user_speech("dosya nerede", now=100.0)
    ot.on_user_speech("dosya nerede acaba", now=101.0)
    assert sent == ["tray"]
    ot.on_user_speech("başka bir soru", now=104.0)
    assert sent == ["tray", "tray"]


def test_hold_after_user_opens_window(sent):
    ot.hold_for(ot.HOLD_AFTER_OPEN, now=100.0)
    assert not ot.on_user_speech("dosya nerede", now=129.0)
    assert ot.on_user_speech("dosya nerede", now=131.0)


def test_hold_never_shortens(sent):
    ot.hold_for(ot.HOLD_AFTER_BOARD, now=100.0)
    ot.hold_for(ot.HOLD_AFTER_OPEN, now=101.0)
    assert not ot.on_user_speech("dosya nerede", now=200.0)


def test_showing_ignores_hold(sent):
    ot.hold_for(ot.HOLD_AFTER_BOARD, now=100.0)
    assert ot.go_to_tray(force=True, now=101.0)


def test_before_showing_waits_only_if_sent(sent, monkeypatch):
    waits = []
    monkeypatch.setattr(ot.time, "sleep", waits.append)
    ot.before_showing(0.25)
    assert waits == [0.25]
    monkeypatch.setattr(commands, "dispatch", lambda name, payload: False)  # pencere yok: tek başına ses döngüsü
    ot.before_showing(0.25)
    assert waits == [0.25]


def test_setting_turns_it_off(sent, monkeypatch):
    monkeypatch.setattr(ot, "enabled", lambda: False)
    assert not ot.on_user_speech("dosya nerede", now=100.0)
    assert not ot.go_to_tray(force=True, now=100.0)
    assert sent == []


@pytest.mark.parametrize("value,expected", [(True, True), (False, False), ("false", False), ("0", False), (None, True), ("evet", True)])
def test_enabled_reads_setting(monkeypatch, value, expected):
    import app_config

    monkeypatch.setattr(app_config, "get_app_config_value", lambda key, default=None: value)
    assert ot.enabled() is expected


def test_no_window_is_not_an_error(monkeypatch):
    monkeypatch.setattr(ot, "_last_sent", -100.0)
    monkeypatch.setattr(ot, "_hold_until", 0.0)
    monkeypatch.setattr(ot, "enabled", lambda: True)

    def boom(name, payload):
        raise RuntimeError("yok")

    monkeypatch.setattr(commands, "dispatch", boom)
    assert ot.on_user_speech("dosya nerede", now=100.0) is False


def test_wired_into_voice_loop_and_window():
    main = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
    desktop = (PROJECT_ROOT / "desktop.py").read_text(encoding="utf-8")
    assert "otomatik_tepsi.on_user_speech" in main
    assert "HOLD_AFTER_OPEN" in desktop and "HOLD_AFTER_BOARD" in desktop
