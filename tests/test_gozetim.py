from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core import gozetim
from backend.core.ofis import OfficeState, tool_category

SID = "sess-g"


def ev(event: str, ts: float, **extra) -> dict:
    return {"event": event, "ts": ts, "session_id": SID, "cwd": r"C:\Projects\Chiron", **extra}


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def assistant(ts: float, mid: str, model: str = "claude-opus-5-5", text: str | None = None, **usage) -> str:
    u = {"input_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 0}
    u.update(usage)
    content = [{"type": "text", "text": text}] if text else [{"type": "tool_use", "name": "Read"}]
    return json.dumps({"type": "assistant", "timestamp": iso(ts), "requestId": "r" + mid,
                       "message": {"id": mid, "model": model, "usage": u, "content": content}})


def user(ts: float, text: str) -> str:
    return json.dumps({"type": "user", "timestamp": iso(ts), "message": {"role": "user", "content": text}})


# ── fiyat ve model ───────────────────────────────────────────────────────────
def test_price_prefers_longest_model_prefix():
    assert gozetim.price_for("claude-opus-5-5")["in"] == 4.0
    assert gozetim.price_for("claude-opus-5")["in"] == 5.0
    assert gozetim.price_for("claude-opus-5-5[1m]")["cr"] == 0.20
    assert abs(gozetim.price_for("claude-sonnet-4-6")["cr"] - 0.3) < 1e-9
    assert gozetim.price_for("gpt-5") is None
    assert gozetim.short_model("claude-opus-5-5") == "opus 5.5"
    assert gozetim.short_model("claude-sonnet-5") == "sonnet 5"
    assert gozetim.window_for("claude-haiku-4-5") == 200_000


def test_usage_cost_counts_1h_cache_writes_double():
    p = gozetim.price_for("claude-opus-5-5")
    cost = gozetim.usage_cost({
        "input_tokens": 1_000_000, "output_tokens": 1_000_000,
        "cache_read_input_tokens": 1_000_000, "cache_creation_input_tokens": 1_000_000,
        "cache_creation": {"ephemeral_1h_input_tokens": 1_000_000, "ephemeral_5m_input_tokens": 0},
    }, p)
    assert round(cost, 2) == round(4 + 20 + 0.20 + 8, 2)


# ── kayıt sayacı ─────────────────────────────────────────────────────────────
def test_meter_dedupes_split_records_and_reads_incrementally(tmp_path):
    path = tmp_path / "s.jsonl"
    now = time.time()
    # Aynı yanıt iki içerik bloğuna bölünmüş: usage bir kez sayılmalı.
    line = assistant(now, "m1", input_tokens=10, cache_read_input_tokens=1000, output_tokens=50)
    path.write_text(line + "\n" + line + "\n", encoding="utf-8")
    meters = gozetim.TranscriptMeters()
    m = meters.read(str(path))
    assert m.tokens["output"] == 50
    assert m.ctx_used == 1010
    first_cost = m.cost
    with open(path, "a", encoding="utf-8") as f:
        f.write(assistant(now + 1, "m2", input_tokens=5, cache_read_input_tokens=2000, output_tokens=10) + "\n")
        f.write('{"type": "assistant", "yarım')  # yarım satır sonraki okumayı beklemeli
    m = meters.read(str(path))
    assert m.tokens["output"] == 60
    assert m.ctx_used == 2005
    assert m.cost > first_cost
    assert m.model == "claude-opus-5-5"


def test_meter_marks_unknown_model_cost():
    meters = gozetim.TranscriptMeters()
    m = gozetim.Meter()
    meters._ingest(m, assistant(time.time(), "x", model="claude-yeni-9", output_tokens=5).encode())
    assert m.cost_known is False
    assert m.tokens["output"] == 5


def test_last_reply_joins_text_after_last_user_message(tmp_path):
    path = tmp_path / "s.jsonl"
    now = time.time()
    tool_result = json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}})
    path.write_text("\n".join([
        user(now, "ilk soru"),
        assistant(now + 1, "a", text="eski cevap"),
        user(now + 2, "ikinci soru"),
        assistant(now + 3, "b", text="Birinci parça"),
        tool_result,
        assistant(now + 4, "c", text="İkinci parça"),
    ]) + "\n", encoding="utf-8")
    assert gozetim.last_reply(str(path)) == "Birinci parça\n\nİkinci parça"


# ── görünüm ──────────────────────────────────────────────────────────────────
def test_view_builds_sessions_research_heat_and_costs(tmp_path):
    now = time.time()
    tpath = tmp_path / "t.jsonl"
    tpath.write_text(assistant(now - 10, "m1", input_tokens=100, cache_read_input_tokens=900,
                               output_tokens=40) + "\n", encoding="utf-8")
    st = OfficeState()
    st.apply(ev("SessionStart", now - 60, transcript_path=str(tpath)))
    st.apply(ev("UserPromptSubmit", now - 50, prompt="gözetim ekle", transcript_path=str(tpath)))
    st.apply(ev("PreToolUse", now - 40, tool_name="Read", tool_use_id="t1", file_path=r"C:\a\ofis.py"))
    st.apply(ev("PreToolUse", now - 30, tool_name="Edit", tool_use_id="t2", file_path=r"C:\a\ofis.py"))
    st.apply(ev("PreToolUse", now - 20, tool_name="WebSearch", tool_use_id="t3", target="statusline rate_limits"))
    # İkinci oturum aynı dosyaya yazıyor → çakışma
    st.apply({"event": "PreToolUse", "ts": now - 15, "session_id": "other", "cwd": r"C:\Projects\Dilcep",
              "tool_name": "Write", "tool_use_id": "t4", "file_path": r"C:\a\ofis.py"})
    st.apply(ev("PermissionRequest", now - 5, tool_name="Bash", command="npm run build"))

    v = gozetim.view(st)
    s = next(x for x in v["sessions"] if x["session_id"] == SID)
    assert s["project"] == "Chiron"
    assert s["status"] == "onay_bekliyor"
    assert s["model_short"] == "opus 5.5"
    assert s["ctx"]["used"] == 1000 and s["ctx"]["window"] == 1_000_000
    assert s["approvals"] and s["approvals"][0]["tool"] == "Bash"
    assert [c for _, c in s["marks"]] == ["okuma", "duzenle", "web", "onay"]
    assert "transcript_path" not in s
    assert v["tool_mix"] == {"okuma": 1, "duzenle": 2, "web": 1}
    assert v["research"][0]["kind"] == "ara" and v["research"][0]["project"] == "Chiron"
    heat = v["files"][0]
    assert heat["writes"] == 2 and heat["collision"] is True
    assert set(heat["writers"]) == {"Chiron", "Dilcep"}
    assert v["totals"]["sessions_live"] == 2
    assert v["totals"]["cost_today"] > 0
    assert v["totals"]["cache_hit"] == 0.9
    assert v["approvals"][0]["project"] == "Chiron"


def test_subagent_belongs_to_its_session_in_view():
    now = time.time()
    st = OfficeState()
    st.apply(ev("UserPromptSubmit", now - 30, prompt="ara"))
    st.apply(ev("PreToolUse", now - 20, tool_name="Agent", tool_use_id="ag1",
                description="ofis taraması", subagent_type="Explore", prompt="tara"))
    v = gozetim.view(st)
    s = v["sessions"][0]
    assert s["subagents"][0]["name"] == "Explore"
    assert v["totals"]["subagents_running"] == 1


def test_tool_category():
    assert tool_category("Grep") == "okuma"
    assert tool_category("MultiEdit") == "duzenle"
    assert tool_category("PowerShell") == "shell"
    assert tool_category("mcp__chiron__search_memory") == "mcp"
    assert tool_category("Skill") == "diger"


# ── kaçak süreç ──────────────────────────────────────────────────────────────
def test_runaway_end_refuses_unlisted_or_reused_pid():
    w = gozetim.RunawayWatch()
    ok, why = w.end(999999, 1.0)
    assert ok is False and "listede" in why
    import os
    import psutil
    me = psutil.Process(os.getpid())
    w._items = [{"pid": me.pid, "create_time": me.create_time() + 50, "name": "python.exe"}]
    ok, why = w.end(me.pid, me.create_time() + 50)
    assert ok is False and "başka bir süreç" in why


def test_phone_view_trims_and_keeps_queue():
    full = {
        "now": 100.0,
        "totals": {"sessions_live": 1, "cost_today": 3.5, "cost_known": True},
        "sessions": [{
            "id": "claude:a", "project": "Dilcep", "title": "t" * 200, "status": "calisiyor",
            "current": "Edit", "last_ts": 99.0, "cost": 1.2, "ctx": {"used": 250, "window": 1000},
            "subagents": [{"status": "calisiyor"}, {"status": "bitti"}], "approvals": [{"id": "x"}],
            "transcript_path": "C:/gizli.jsonl", "files_written": ["a.py"],
        }],
        "log": [{"text": "x"}], "files": [], "research": [], "runaways": [{"pid": 1}],
    }
    decisions = [{"id": "r1", "project": "Dilcep", "tool": "Bash", "summary": "npm test", "detail": "d" * 900,
                  "can_always": True, "ts": 98.0, "deadline": 160.0, "cwd": "C:/x", "session_id": "s"}]
    limits = {"status": "allowed", "five_hour": {"used": 0.8, "resets_at": 200.0}, "seven_day": {"used": "?"}}
    out = gozetim.phone_view(full, decisions, limits)
    assert out["live"] == 1 and out["cost_today"] == 3.5 and out["runaways"] == 1
    s = out["sessions"][0]
    assert s["ctx_pct"] == 25 and s["subagents"] == 1 and s["waiting"] is True
    assert len(s["title"]) == 80 and "transcript_path" not in s and "files_written" not in s
    q = out["queue"][0]
    assert q["id"] == "r1" and len(q["detail"]) == 600 and "cwd" not in q
    assert out["limits"] == {"five_hour": {"used": 0.8, "resets_at": 200.0}}
    assert "log" not in out


def test_phone_view_empty():
    out = gozetim.phone_view({}, [], {})
    assert out["live"] == 0 and out["sessions"] == [] and out["queue"] == [] and out["limits"] == {}
