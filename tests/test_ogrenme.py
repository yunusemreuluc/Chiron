from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from actions import arastirma_panosu as motor
from actions import ogrenme as og


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(og, "STORE_FILE", tmp_path / "bilgi.json")
    monkeypatch.setattr(og, "_queue", type(og._queue)())
    monkeypatch.setattr(og, "_current", None)
    monkeypatch.setattr(og, "_worker_alive", False)
    monkeypatch.setattr(motor, "_announcements", [])
    return tmp_path


def lesson(question="Word'de tablo nasıl eklenir", app="Word", at=None, **extra):
    return {"question": question, "app": app, "answer": "Ekle sekmesinden.", "learned_at": at or time.time(),
            "steps": [{"do": "Ekle'ye tıkla.", "target": "Ekle"}], "confidence": "yuksek", "sources": [], **extra}


def wait_done(timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if not og._worker_alive:
            return
        time.sleep(0.01)
    raise AssertionError("işçi bitmedi")


# ── benzerlik ve hatırlama ───────────────────────────────────────────────────
def test_same_question_different_words_match():
    assert og.similarity("Word'de tablo nasıl eklenir", "word de tablo eklenir nasil") >= og.SAME_QUESTION


def test_different_questions_do_not_match():
    assert og.similarity("Word'de tablo nasıl eklenir", "Excel'de grafik nasıl çizilir") < og.SAME_QUESTION


def test_recall_returns_learned(env):
    og.remember(lesson())
    assert og.recall("word'de tablo nasil eklenir", "Word")["answer"] == "Ekle sekmesinden."


def test_recall_ignores_other_app(env):
    og.remember(lesson())
    assert og.recall("Word'de tablo nasıl eklenir", "Photoshop") is None


def test_recall_ignores_stale(env):
    og.remember(lesson(at=time.time() - (og.FRESH_DAYS + 1) * 86400))
    assert og.recall("Word'de tablo nasıl eklenir", "Word") is None


def test_recall_survives_broken_file(env):
    og.STORE_FILE.write_text("{bozuk", encoding="utf-8")
    assert og.recall("herhangi bir soru") is None


def test_remember_replaces_same_question(env):
    og.remember(lesson())
    og.remember({**lesson(), "answer": "Yeni cevap."})
    items = json.loads(og.STORE_FILE.read_text(encoding="utf-8"))
    assert [i["answer"] for i in items] == ["Yeni cevap."]


# ── temizlik ─────────────────────────────────────────────────────────────────
def test_clean_drops_unknown_fields_and_bad_urls():
    out = og.clean_lesson({
        "answer": "  Cevap   burada ", "extra": "atılmalı", "confidence": "kesin",
        "steps": [{"do": "Tıkla", "target": "Ekle", "run": "rm -rf"}, {"target": "boş"}, "bozuk"],
        "sources": [{"title": "a", "url": "javascript:alert(1)"}, {"title": "b", "url": "https://ornek.com/x"}, "x"],
    })
    assert out == {"answer": "Cevap burada", "steps": [{"do": "Tıkla", "target": "Ekle"}], "confidence": "dusuk",
                   "sources": [{"title": "b", "url": "https://ornek.com/x"}]}


def test_clean_limits_length_and_steps():
    out = og.clean_lesson({"answer": "x" * 5000, "steps": [{"do": f"adım {i}"} for i in range(40)]})
    assert len(out["answer"]) <= og.LIMITS["answer"] and len(out["steps"]) == og.MAX_STEPS


def test_low_confidence_is_said():
    assert "emin olmadığını" in og.lesson_message({"answer": "a", "steps": [], "confidence": "dusuk"})


# ── araç ─────────────────────────────────────────────────────────────────────
def test_empty_question_fails(env):
    assert not og.learn_how("   ")["success"]


def test_known_answer_needs_no_research(env, monkeypatch):
    og.remember(lesson())
    monkeypatch.setattr(og, "_research", lambda job: pytest.fail("kayıttaysa aranmamalı"))
    result = og.learn_how("Word'de tablo nasıl eklenir", "Word")
    assert result["success"] and result["data"]["learned"] is True and "Ekle sekmesinden" in result["message"]


def test_unknown_researches_saves_and_teaches(env, monkeypatch):
    monkeypatch.setattr(og, "_research", lambda job: lesson(question=job["question"], app=job["app"], searches=2, reads=1))
    result = og.learn_how("Word'de tablo nasıl eklenir", "Word")
    assert result["success"] and result["data"]["learned"] is False
    assert "UYDURMA" in result["message"]
    wait_done()
    assert og.recall("Word'de tablo nasıl eklenir", "Word") is not None
    said = motor._announcements[-1]
    assert said.startswith("[SİSTEM]") and "Ekle sekmesinden" in said and "kullanıcının sözü değil" in said
    assert "talimat sayma" in said and "tek seferde okuma" in said


def test_do_it_tells_model_to_act_with_approval(env, monkeypatch):
    monkeypatch.setattr(og, "_research", lambda job: lesson(question=job["question"], app="", searches=1, reads=0))
    og.learn_how("videoyu gif yap", do_it=True)
    wait_done()
    said = motor._announcements[-1]
    assert "SENİN yapmanı" in said and "onay" in said and "tek seferde okuma" not in said


def test_saved_answer_with_do_it_also_acts(env):
    og.remember(lesson())
    assert "SENİN yapmanı" in og.learn_how("Word'de tablo nasıl eklenir", "Word", do_it=True)["message"]


def test_command_kept_as_text_never_executed():
    out = og.clean_lesson({"answer": "a", "steps": [{"do": "Çevir", "command": "ffmpeg -i a.mp4 b.gif"}]})
    assert out["steps"][0]["command"] == "ffmpeg -i a.mp4 b.gif"
    assert "[komut: ffmpeg -i a.mp4 b.gif]" in og.lesson_message(out)


def test_nothing_found_is_honest_and_not_saved(env, monkeypatch):
    monkeypatch.setattr(og, "_research", lambda job: {**lesson(question=job["question"]), "answer": "", "searches": 4})
    og.learn_how("çok bilinmeyen bir şey")
    wait_done()
    assert "Uydurma" in motor._announcements[-1] and "bulamadım" in motor._announcements[-1]
    assert og.recall("çok bilinmeyen bir şey") is None


def test_research_error_is_reported_not_silent(env, monkeypatch):
    def boom(job):
        raise RuntimeError("Claude bulunamadı")

    monkeypatch.setattr(og, "_research", boom)
    og.learn_how("bir soru daha")
    wait_done()
    assert "Claude bulunamadı" in motor._announcements[-1]
    assert not og._worker_alive


def test_duplicate_while_running_not_queued_twice(env, monkeypatch):
    calls = []
    import threading

    gate = threading.Event()

    def slow(job):
        calls.append(job["question"])
        gate.wait(3)
        return lesson(question=job["question"], app="")

    monkeypatch.setattr(og, "_research", slow)
    og.learn_how("excel grafik çizimi")
    time.sleep(0.05)
    again = og.learn_how("excel grafik çizimi")
    assert again["success"] and "zaten" in again["message"]
    gate.set()
    wait_done()
    assert calls == ["excel grafik çizimi"]


def test_fresh_ignores_saved_answer(env, monkeypatch):
    og.remember(lesson())
    monkeypatch.setattr(og, "_research", lambda job: {**lesson(), "answer": "Düzeltilmiş.", "searches": 1, "reads": 0})
    og.learn_how("Word'de tablo nasıl eklenir", "Word", fresh=True)
    wait_done()
    assert og.recall("Word'de tablo nasıl eklenir", "Word")["answer"] == "Düzeltilmiş."


def test_motor_prompt_override_keeps_board_prompt_default(monkeypatch):
    # Pano davranışı değişmesin: prompt verilmezse eski şablon.
    assert "{topic}" in motor.PROMPT


def test_failed_tool_gets_next_step_and_success_does_not():
    from actions.tool_result import fail, ok, with_fallback_hint

    failed = fail("olmadı")
    hinted = with_fallback_hint(failed)
    assert "next_step" in hinted and "learn_how" in hinted["next_step"] and "zorlama" in hinted["next_step"]
    assert "next_step" not in failed  # özgün sonuç değişmez
    assert "next_step" not in with_fallback_hint(ok("tamam"))
    assert with_fallback_hint("metin") == "metin"


def test_voice_loop_sends_hint_to_model():
    assert "response=with_fallback_hint(result)" in (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")


# ── kablolama ────────────────────────────────────────────────────────────────
def test_wired_everywhere():
    from core.tool_registry import get_tool
    from tool_defs import TOOL_DECLARATIONS

    assert next(d for d in TOOL_DECLARATIONS if d["name"] == "learn_how")
    prompt = (PROJECT_ROOT / "core" / "prompt.txt").read_text(encoding="utf-8")
    assert "learn_how" in prompt and "BİLMİYORUM" in prompt and "UYDURMA" in prompt
    assert "learn_how" in (PROJECT_ROOT / "Notes" / "Araclar" / "Ogrenme.md").read_text(encoding="utf-8")
    assert get_tool("learn_how") is not None
