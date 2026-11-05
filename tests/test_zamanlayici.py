"""Sesli zamanlayıcı (set_timer, K-014)."""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from actions import zamanlayici  # noqa: E402


@pytest.fixture(autouse=True)
def _clean():
    zamanlayici._timers.clear()
    yield
    zamanlayici._timers.clear()


def test_spoken_duration_and_suffix():
    assert zamanlayici.spoken_duration(40) == "40 saniye"
    assert zamanlayici.spoken_duration(600) == "10 dakika"
    assert zamanlayici.spoken_duration(3900) == "1 saat 5 dakika"
    assert zamanlayici.spoken_duration(3599) == "1 saat"  # 59.98 dk "60 dakika" değil
    assert zamanlayici._lik("10 dakika") == "10 dakikalık"
    assert zamanlayici._lik("1 saat") == "1 saatlik"
    assert zamanlayici._lik("40 saniye") == "40 saniyelik"


def test_resolve_at_rolls_to_tomorrow_and_rejects_bad_input():
    now = datetime(2026, 11, 4, 16, 0)
    assert zamanlayici.resolve_seconds(at="16:30", now=now) == 30 * 60
    assert zamanlayici.resolve_seconds(at="15:00", now=now) == 23 * 3600  # geçti → yarın
    assert zamanlayici.resolve_seconds(at="9.05", now=now) == (17 * 60 + 5) * 60
    for bad in ("25:00", "yarın", "15"):
        with pytest.raises(ValueError):
            zamanlayici.resolve_seconds(at=bad, now=now)
    with pytest.raises(ValueError):
        zamanlayici.resolve_seconds()
    with pytest.raises(ValueError):
        zamanlayici.resolve_seconds(minutes=25 * 60)
    assert zamanlayici.resolve_seconds(minutes=1, seconds=30) == 90


def test_set_list_and_fire_once():
    result = zamanlayici.set_timer("set", minutes=10, label="çay")
    assert result["success"] and "çay" in result["message"] and "10 dakika" in result["message"]
    listed = zamanlayici.set_timer("list")
    assert listed["success"] and "çay" in listed["message"] and "kaldı" in listed["message"]

    assert zamanlayici.pop_due(time.time()) == []  # henüz dolmadı
    due = zamanlayici._timers[0]["due"]
    messages = zamanlayici.pop_due(due + 1)
    assert len(messages) == 1 and "'çay'" in messages[0] and "gecikme" not in messages[0]
    assert zamanlayici.pop_due(due + 2) == []  # bir kez söylenir
    assert not zamanlayici.has_timers()


def test_late_fire_mentions_delay_and_unnamed_timer():
    zamanlayici.set_timer("set", minutes=25)
    due = zamanlayici._timers[0]["due"]
    (message,) = zamanlayici.pop_due(due + 120)
    assert "25 dakikalık zamanlayıcı" in message and "gecikme" in message


def test_cancel_by_name_ambiguity_and_all():
    zamanlayici.set_timer("set", minutes=5, label="çay")
    zamanlayici.set_timer("set", minutes=30, label="toplantı")
    ambiguous = zamanlayici.set_timer("cancel")
    assert not ambiguous["success"] and "Hangisini" in ambiguous["message"]
    assert len(zamanlayici._timers) == 2  # belirsizken hiçbirini silmez

    assert zamanlayici.set_timer("cancel", label="Çay")["success"]
    assert [t["label"] for t in zamanlayici._timers] == ["toplantı"]
    assert not zamanlayici.set_timer("cancel", label="yemek")["success"]

    zamanlayici.set_timer("set", minutes=2)
    assert zamanlayici.set_timer("cancel", label="hepsi")["data"]["cancelled"] == 2
    assert zamanlayici.set_timer("list")["message"] == "Kurulu zamanlayıcı yok."


def test_bad_input_returns_failure_not_exception():
    assert not zamanlayici.set_timer("set")["success"]
    assert not zamanlayici.set_timer("set", at="yarın")["success"]
    assert not zamanlayici.set_timer("snooze")["success"]
    assert zamanlayici._timers == []


def test_declared_and_registered():
    from core.tool_registry import bind_args, get_tool
    from tool_defs import TOOL_DECLARATIONS

    func = get_tool("set_timer")
    assert func is zamanlayici.set_timer
    assert bind_args(func, {"action": "set", "minutes": "10"})["minutes"] == 10.0  # model metin yollasa da

    decl = next(d for d in TOOL_DECLARATIONS if d["name"] == "set_timer")
    assert set(decl["parameters"]["properties"]) == {"action", "minutes", "seconds", "at", "label"}
    prompt = (PROJECT_ROOT / "core" / "prompt.txt").read_text(encoding="utf-8")
    assert "set_timer" in prompt
