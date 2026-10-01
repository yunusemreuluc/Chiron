from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import office as office_api
from backend.core import ofis
from backend.core.ofis import OfficeState, OfficeWatcher, classify_lane

SID = "sess-1"
T0 = 1_790_000_000.0


def ev(event: str, ts: float, **extra) -> dict:
    return {"event": event, "ts": ts, "session_id": SID, "cwd": r"C:\proje", **extra}


def started_turn(state: OfficeState, prompt: str = "Airon'a ofis ekle") -> None:
    state.apply(ev("SessionStart", T0, source="startup"))
    state.apply(ev("UserPromptSubmit", T0 + 1, prompt=prompt))


# ── lane tanıma ──────────────────────────────────────────────────────────────
def test_classify_lane_recognises_each_model():
    sol = classify_lane(
        'codex exec --skip-git-repo-check -m gpt-5.6-sol -c model_reasoning_effort=high '
        '--sandbox workspace-write -C "C:/Users/yunus/Proje" "tests/test_x.py dosyasını yaz, desene uy" < /dev/null 2>&1'
    )
    assert sol["desk"] == "sol"
    assert sol["sandbox"] == "workspace-write"
    assert sol["target_dir"] == "C:/Users/yunus/Proje"
    assert sol["brief"] == "tests/test_x.py dosyasını yaz, desene uy"

    astra = classify_lane('"" | codex exec -m gpt-6-astra --sandbox read-only -C . "diff\'i incele, bulguları listele"')
    assert astra["desk"] == "astra" and astra["sandbox"] == "read-only"

    assert classify_lane('python ~/.claude/tools/bunny.py -e medium -p "logu özetle lütfen bu" big.log')["desk"] == "bunny"
    assert classify_lane('cd x && OPENCODE_DISABLE_CLAUDE_CODE=1 opencode run -m openrouter/x "küçük bir iş yap"')["desk"] == "opencode"
    assert classify_lane('cd d && gemini --skip-trust -m gemini-3.8-flash -p "iki kütüphaneyi karşılaştır" < /dev/null')["desk"] == "gemini"


def test_classify_lane_ignores_mentions():
    assert classify_lane('grep -n "codex exec" CLAUDE.md') is None
    assert classify_lane("cat bunny.py") is None
    assert classify_lane("ls -la") is None
    assert classify_lane(None) is None


# ── şef döngüsü ──────────────────────────────────────────────────────────────
def test_chief_turn_creates_task_and_closes_on_stop():
    s = OfficeState()
    started_turn(s)
    s.apply(ev("PreToolUse", T0 + 2, tool_name="Read", tool_use_id="t1", file_path=r"C:\proje\a.py"))
    s.apply(ev("PostToolUse", T0 + 3, tool_name="Read", tool_use_id="t1", result_chars=10))
    s.apply(ev("PreToolUse", T0 + 4, tool_name="Edit", tool_use_id="t2", file_path=r"C:\proje\a.py"))

    chief = s.workers[f"claude:{SID}"]
    assert chief.status == ofis.WORKING
    assert chief.current == "Düzenliyor: a.py"
    task = s.tasks[chief.task_id]
    assert task.title == "Airon'a ofis ekle"
    assert task.files_changed == [r"C:\proje\a.py"]

    s.apply(ev("Stop", T0 + 5, last_message="Tamam, ekledim."))
    assert chief.status == ofis.IDLE
    assert task.column == ofis.COL_DONE
    assert task.result == "Tamam, ekledim."

    desk = next(d for d in s.snapshot()["desks"] if d["id"] == "claude")
    assert desk["status"] == ofis.IDLE
    assert desk["stats"]["jobs"] == 1 and desk["stats"]["done"] == 1


def test_session_end_marks_chief_left_and_stops_open_task():
    s = OfficeState()
    started_turn(s)
    s.apply(ev("SessionEnd", T0 + 9, source="exit"))
    chief = s.workers[f"claude:{SID}"]
    assert chief.status == ofis.LEFT
    assert s.tasks[chief.task_id].column == ofis.COL_STOPPED
    assert f"claude:{SID}" not in s.snapshot()["desks"][0]["workers"]


# ── alt ajan ─────────────────────────────────────────────────────────────────
def test_subagent_is_bound_tracked_and_finished():
    s = OfficeState()
    started_turn(s)
    s.apply(ev("PreToolUse", T0 + 2, tool_name="Agent", tool_use_id="ag1",
               description="Repo'yu tara", subagent_type="Explore", prompt="frontend'i tara"))
    sub = s.workers["sub:ag1"]
    assert sub.status == ofis.WORKING and sub.given_by == f"claude:{SID}"

    s.apply(ev("SubagentStart", T0 + 3, agent_id="A1", agent_type="Explore"))
    s.apply(ev("PreToolUse", T0 + 4, agent_id="A1", agent_type="Explore",
               tool_name="Grep", tool_use_id="g1", pattern="useOffice"))
    assert sub.current == "Arıyor: useOffice"
    assert s.workers[f"claude:{SID}"].current.startswith("Alt ajana iş verdi")

    s.apply(ev("SubagentStop", T0 + 8, agent_id="A1", agent_type="Explore", last_message="3 dosya buldum"))
    assert sub.status == ofis.DONE and sub.result == "3 dosya buldum"
    root = s.tasks[s.workers[f"claude:{SID}"].task_id]
    assert root.children == ["sub:ag1"]
    assert s.tasks["sub:ag1"].column == ofis.COL_DONE
    proof = root.to_dict(s)["proof"]
    assert proof["delegations"] == 1 and proof["children_done"] == 1


def test_subagent_event_without_start_opens_worker_in_place():
    s = OfficeState()
    started_turn(s)
    s.apply(ev("PreToolUse", T0 + 2, agent_id="Z9", agent_type="Plan", tool_name="Read",
               tool_use_id="r", file_path="x.md"))
    assert s.workers["sub:Z9"].desk == "subagents"


# ── lane'ler ─────────────────────────────────────────────────────────────────
def test_foreground_lane_finishes_on_post_tool_use():
    s = OfficeState()
    started_turn(s)
    cmd = 'python ~/.claude/tools/bunny.py -e medium -p "bu logda hata ne?" app.log'
    s.apply(ev("PreToolUse", T0 + 2, tool_name="Bash", tool_use_id="b1", command=cmd, description="Logu Bunny'ye oku"))
    lane = s.workers["lane:b1"]
    assert lane.desk == "bunny" and lane.title == "Logu Bunny'ye oku"
    s.apply(ev("PostToolUse", T0 + 9, tool_name="Bash", tool_use_id="b1", command=cmd, result_tail="Hata: port dolu"))
    assert lane.status == ofis.DONE and lane.result == "Hata: port dolu"
    assert s.desk_stats["bunny"]["done"] == 1


def test_background_codex_lane_links_to_rollout_and_finishes_there():
    s = OfficeState()
    started_turn(s)
    cmd = 'codex exec -m gpt-5.6-sol --sandbox workspace-write -C "C:/proje" "test dosyasını yaz lütfen"'
    s.apply(ev("PreToolUse", T0 + 2, tool_name="Bash", tool_use_id="c1", command=cmd, background=True))
    s.apply(ev("PostToolUse", T0 + 3, tool_name="Bash", tool_use_id="c1", command=cmd, backgroundTaskId="bt1"))
    lane = s.workers["lane:c1"]
    assert lane.status == ofis.WORKING and lane.tracking == "tam"

    s.codex_turn("R1", T0 + 4, "C:/proje", "gpt-5.6-sol", "workspace-write")
    s.codex_event("R1", T0 + 5, "command", {"cmd": "pytest -q"})
    s.codex_event("R1", T0 + 6, "tokens", {"total": 1200, "input": 1000, "output": 200})
    s.codex_event("R1", T0 + 6, "quota", {"primary": {"used_percent": 31.0}})
    assert lane.codex_rollout == "R1" and lane.current == "pytest -q"
    s.codex_event("R1", T0 + 7, "done", {"message": "Yazdım, 4 test geçti"})
    assert lane.status == ofis.DONE and lane.result == "Yazdım, 4 test geçti"
    assert s.desk_stats["sol"]["tokens"] == 1200
    assert s.snapshot()["quota"]["codex"]["primary"]["used_percent"] == 31.0


def test_codex_rollout_moves_lane_to_real_model_desk():
    s = OfficeState()
    started_turn(s)
    s.apply(ev("PreToolUse", T0 + 2, tool_name="Bash", tool_use_id="c2",
               command='codex exec --sandbox read-only "şu diff\'i incele lütfen"', background=True))
    assert s.workers["lane:c2"].desk == "sol"  # -m yok → varsayılan
    s.codex_turn("R2", T0 + 3, None, "gpt-6-astra", "read-only")
    lane = s.workers["lane:c2"]
    assert lane.desk == "astra" and lane.name == "Codex Astra"
    assert s.desk_stats["sol"]["jobs"] == 0 and s.desk_stats["astra"]["jobs"] == 1


def test_astra_read_only_lane_goes_to_review_column():
    s = OfficeState()
    started_turn(s)
    s.apply(ev("PreToolUse", T0 + 2, tool_name="Bash", tool_use_id="c3",
               command='codex exec -m gpt-6-astra --sandbox read-only -C . "değişikliği incele lütfen"'))
    assert s.tasks["lane:c3"].column == ofis.COL_REVIEW
    root = s.tasks[s.workers[f"claude:{SID}"].task_id]
    assert root.to_dict(s)["proof"]["reviews"] == 1


def test_background_non_codex_lane_is_marked_limited_and_stops_with_session():
    s = OfficeState()
    started_turn(s)
    s.apply(ev("PreToolUse", T0 + 2, tool_name="Bash", tool_use_id="o1", background=True,
               command='OPENCODE_DISABLE_CLAUDE_CODE=1 opencode run -m x "bir yardımcı fonksiyon yaz"'))
    lane = s.workers["lane:o1"]
    assert lane.tracking == "sinirli"
    s.apply(ev("SessionEnd", T0 + 50))
    assert lane.status == ofis.LEFT
    assert s.tasks["lane:o1"].column == ofis.COL_STOPPED


# ── onay ve test kanıtı ──────────────────────────────────────────────────────
def test_permission_request_waits_then_clears():
    s = OfficeState()
    started_turn(s)
    s.apply(ev("PreToolUse", T0 + 2, tool_name="Bash", tool_use_id="p1", command="git push"))
    s.apply(ev("PermissionRequest", T0 + 3, tool_name="Bash", command="git push"))
    chief = s.workers[f"claude:{SID}"]
    assert chief.status == ofis.WAITING
    assert s.tasks[chief.task_id].column == ofis.COL_APPROVAL
    assert [a["what"] for a in s.snapshot()["approvals"]] == ["git push"]
    assert s.snapshot()["desks"][0]["status"] == ofis.WAITING

    s.apply(ev("PostToolUse", T0 + 9, tool_name="Bash", tool_use_id="p1", command="git push"))
    assert chief.status == ofis.WORKING
    assert s.snapshot()["approvals"] == []
    assert s.tasks[chief.task_id].column == ofis.COL_RUN


def test_test_runs_become_proof_on_root_task():
    s = OfficeState()
    started_turn(s)
    s.apply(ev("PreToolUse", T0 + 2, tool_name="Bash", tool_use_id="x1", command="venv/Scripts/python -m pytest -q"))
    s.apply(ev("PostToolUse", T0 + 3, tool_name="Bash", tool_use_id="x1",
               command="venv/Scripts/python -m pytest -q", result_tail="18 passed in 1.2s"))
    s.apply(ev("PostToolUseFailure", T0 + 4, tool_name="Bash", tool_use_id="x2",
               command="npm run build", error="Exit code 1"))
    tests = s.tasks[s.workers[f"claude:{SID}"].task_id].tests
    assert [t["verdict"] for t in tests] == ["yesil", "kirmizi"]


def test_unknown_events_are_ignored():
    s = OfficeState()
    s.apply({"event": "SomethingNew", "ts": T0})
    s.apply({"event": "PreToolUse", "ts": T0, "tool_name": "Read"})  # session yok
    assert s.workers == {} and s.events_seen == 2


# ── dosya izleyici ───────────────────────────────────────────────────────────
def _write_lines(path: Path, records: list[dict], partial: str = "") -> None:
    with open(path, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.write(partial)


def test_watcher_tails_events_and_codex_rollouts(tmp_path):
    events = tmp_path / "events.jsonl"
    now = time.time()
    _write_lines(events, [ev("UserPromptSubmit", now, prompt="Ofisi kur")],
                 partial='{"event": "PreToolUse", "ts": ')  # yazılırken kesilmiş satır
    day = datetime.now()
    codex_day = tmp_path / "codex" / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}"
    codex_day.mkdir(parents=True)

    sent: list[dict] = []
    s = OfficeState()
    w = OfficeWatcher(s, on_change=sent.append, events_path=events, codex_dir=tmp_path / "codex")
    w.poll()
    assert s.events_seen == 1 and len(sent) == 1

    # Kesik satır tamamlanır + Codex lane'i başlar.
    cmd = 'codex exec -m gpt-5.6-sol -C "C:/proje" "bir şey yaz lütfen tamam"'
    with open(events, "a", encoding="utf-8") as f:
        f.write(f'{now + 1}, "session_id": "{SID}", "tool_name": "Bash", "tool_use_id": "L", '
                f'"command": {json.dumps(cmd)}, "background": true}}\n')
    iso = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")  # noqa: E731
    _write_lines(codex_day / "rollout-x.jsonl", [
        {"timestamp": iso(now + 2), "type": "session_meta", "payload": {"id": "RX", "cwd": "C:/proje", "originator": "codex_exec"}},
        {"timestamp": iso(now + 2), "type": "turn_context", "payload": {"cwd": "C:/proje", "model": "gpt-5.6-sol", "sandbox_policy": {"type": "workspace-write"}}},
        {"timestamp": iso(now + 3), "type": "response_item", "payload": {"type": "custom_tool_call", "input": 'tools.exec_command({cmd:"pytest -q",max_output_tokens:3000})'}},
        {"timestamp": iso(now + 4), "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"total_tokens": 5000}}, "rate_limits": {"primary": {"used_percent": 12.0}, "plan_type": "plus"}}},
    ])
    w._last_scan = 0
    w.poll()
    lane = s.workers["lane:L"]
    assert lane.codex_rollout == "RX"
    assert lane.tokens["total"] == 5000
    assert any(a["text"] == "pytest -q" for a in lane.activity)
    assert sent[-1]["quota"]["codex"]["primary"]["used_percent"] == 12.0

    _write_lines(codex_day / "rollout-x.jsonl", [
        {"timestamp": iso(now + 5), "type": "event_msg", "payload": {"type": "task_complete", "last_agent_message": "bitti"}},
    ])
    w.poll()
    assert lane.status == ofis.DONE

    # Değişiklik yoksa yeniden yayın yok.
    count = len(sent)
    w.poll()
    assert len(sent) == count


def test_watcher_handles_rotation_and_history_window(tmp_path):
    events = tmp_path / "events.jsonl"
    _write_lines(events, [ev("SessionStart", T0 + i) for i in range(50)])
    s = OfficeState()
    w = OfficeWatcher(s, events_path=events, codex_dir=tmp_path / "yok", history_bytes=400)
    w.poll()
    assert 0 < s.events_seen < 50  # yalnız son pencere, ilk (yarım) satır atlandı

    events.write_text("", encoding="utf-8")  # döndürüldü
    _write_lines(events, [ev("UserPromptSubmit", T0 + 99, prompt="yeni dosya")])
    seen = s.events_seen
    w.poll()
    assert s.events_seen == seen + 1


# ── API ──────────────────────────────────────────────────────────────────────
def test_office_api(monkeypatch):
    s = OfficeState()
    started_turn(s)
    monkeypatch.setattr(office_api, "office", s)
    app = FastAPI()
    app.include_router(office_api.router)
    client = TestClient(app)

    body = client.get("/api/office/state").json()
    assert body["success"] and [d["id"] for d in body["data"]["desks"]][0] == "claude"

    detail = client.get(f"/api/office/workers/claude:{SID}").json()
    assert detail["success"] and detail["data"]["task"]["title"] == "Airon'a ofis ekle"
    assert detail["data"]["activity"]

    assert client.get("/api/office/workers/yok").json()["success"] is False
    assert client.get("/api/office/desks/astra").json()["data"]["name"] == "Codex Astra"
    assert client.get("/api/office/desks/yok").json()["success"] is False


# ── Astra çapraz incelemesi (2026-10-02) — regresyon testleri ────────────────
def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")


def _codex_day(tmp_path: Path) -> Path:
    day = datetime.now()
    folder = tmp_path / "codex" / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}"
    folder.mkdir(parents=True)
    return folder


def test_lane_regex_ignores_quoted_separators_and_accepts_quoted_exe():
    assert classify_lane('echo "örnek; codex exec -m gpt-6-astra yap"') is None
    ps = classify_lane(
        '"" | & "C:/Program Files/Codex/codex.exe" exec -m gpt-6-astra --sandbox read-only "farkı incele lütfen tamam"'
    )
    assert ps is not None and ps["desk"] == "astra"
    cd = classify_lane('cd "C:/Users/yunus/Proje" && codex exec -m gpt-5.6-sol -C . "testleri yaz lütfen tamam"')
    assert cd["target_dir"] == "C:/Users/yunus/Proje"


def test_codex_commands_and_messages_are_masked():
    s = OfficeState()
    started_turn(s)
    s.apply(ev("PreToolUse", T0 + 2, tool_name="Bash", tool_use_id="m1", command='codex exec "bir şey yap lütfen tamam"'))
    s.codex_turn("RM", T0 + 3, None, "gpt-5.6-sol", "read-only")
    s.codex_event("RM", T0 + 4, "command", {"cmd": "curl -H 'Authorization: Bearer abcdefghijklmnop1234'"})
    s.codex_event("RM", T0 + 5, "done", {"message": "anahtar OPENAI_API_KEY=sk-abcdefghijklmnopqrstuv"})
    text = json.dumps(s.workers["lane:m1"].detail(), ensure_ascii=False)
    assert "abcdefghijklmnop1234" not in text and "sk-abcdefghij" not in text


def test_failed_agent_call_leaves_queue():
    s = OfficeState()
    started_turn(s)
    s.apply(ev("PreToolUse", T0 + 2, tool_name="Agent", tool_use_id="A", subagent_type="Explore", description="a"))
    s.apply(ev("PostToolUseFailure", T0 + 3, tool_name="Agent", tool_use_id="A", error="iptal"))
    s.apply(ev("PreToolUse", T0 + 4, tool_name="Agent", tool_use_id="B", subagent_type="Explore", description="b"))
    s.apply(ev("SubagentStart", T0 + 5, agent_id="X", agent_type="Explore"))
    assert s.workers["sub:A"].status == ofis.FAILED
    assert s.workers["sub:B"].agent_id == "X"


def test_subagent_start_before_pretooluse_is_one_job():
    s = OfficeState()
    started_turn(s)
    s.apply(ev("SubagentStart", T0 + 2.0, agent_id="Q", agent_type="Plan"))
    s.apply(ev("PreToolUse", T0 + 2.1, tool_name="Agent", tool_use_id="P", subagent_type="Plan",
               description="Plan yaz", prompt="..."))
    subs = [w for w in s.workers.values() if w.kind == "subagent"]
    assert len(subs) == 1 and subs[0].title == "Plan yaz"
    assert s.desk_stats["subagents"]["jobs"] == 1
    s.apply(ev("PostToolUse", T0 + 9, tool_name="Agent", tool_use_id="P", result_tail="tamam"))
    s.apply(ev("SubagentStop", T0 + 9, agent_id="Q", agent_type="Plan"))
    assert subs[0].status == ofis.DONE and s.desk_stats["subagents"]["done"] == 1


def test_codex_link_respects_dir_and_model():
    s = OfficeState()
    started_turn(s)
    s.apply(ev("PreToolUse", T0 + 2, tool_name="Bash", tool_use_id="L1", background=True,
               command='codex exec -m gpt-5.6-sol -C "C:/a" "işi yap lütfen tamam mı"'))
    assert s.codex_turn("other-dir", T0 + 3, "C:/b", "gpt-5.6-sol", "read-only") is False
    assert s.codex_turn("other-model", T0 + 3, "C:/a", "gpt-6-astra", "read-only") is False
    assert s.codex_turn("right", T0 + 3, "C:/a", "gpt-5.6-sol", "workspace-write") is True
    assert s.workers["lane:L1"].codex_rollout == "right"


def test_moving_finished_lane_moves_all_stats():
    s = OfficeState()
    started_turn(s)
    cmd = 'codex exec --sandbox read-only "şunu incele lütfen tamam"'
    s.apply(ev("PreToolUse", T0 + 2, tool_name="Bash", tool_use_id="F", command=cmd))
    s.apply(ev("PostToolUse", T0 + 12, tool_name="Bash", tool_use_id="F", command=cmd, result_tail="bitti"))
    s.codex_turn("RF", T0 + 3, None, "gpt-6-astra", "read-only")
    assert s.desk_stats["sol"] == {"jobs": 0, "done": 0, "failed": 0, "busy_seconds": 0.0, "tokens": 0}
    assert s.desk_stats["astra"]["jobs"] == 1 and s.desk_stats["astra"]["done"] == 1
    assert s.desk_stats["astra"]["busy_seconds"] == 10.0


def test_approvals_cleared_on_stop_and_subagent_stop():
    s = OfficeState()
    started_turn(s)
    s.apply(ev("PermissionRequest", T0 + 2, tool_name="Bash", command="rm -rf build"))
    s.apply(ev("Stop", T0 + 3))
    assert s.approvals == {}
    s.apply(ev("UserPromptSubmit", T0 + 4, prompt="yeni"))
    s.apply(ev("PreToolUse", T0 + 5, tool_name="Agent", tool_use_id="S", subagent_type="Explore"))
    s.apply(ev("SubagentStart", T0 + 6, agent_id="E", agent_type="Explore"))
    s.apply(ev("PermissionRequest", T0 + 7, agent_id="E", tool_name="Bash", command="git push"))
    assert len(s.approvals) == 1
    s.apply(ev("SubagentStop", T0 + 8, agent_id="E"))
    assert s.approvals == {}


def test_index_tables_are_pruned_with_workers(monkeypatch):
    monkeypatch.setattr(ofis, "MAX_WORKERS", 20)
    s = OfficeState()
    started_turn(s)
    for i in range(60):
        s.apply(ev("PreToolUse", T0 + 2 + i, tool_name="Agent", tool_use_id=f"t{i}", subagent_type="Explore"))
        s.apply(ev("SubagentStart", T0 + 2 + i, agent_id=f"a{i}", agent_type="Explore"))
        s.apply(ev("SubagentStop", T0 + 2.5 + i, agent_id=f"a{i}"))
    assert len(s.workers) <= 21
    assert len(s._agent_to_worker) <= 21 and len(s._tool_to_worker) <= 21


def test_watcher_links_rollout_read_before_lane_and_replays_done(tmp_path):
    events = tmp_path / "events.jsonl"
    events.write_text("", encoding="utf-8")
    codex_day = _codex_day(tmp_path)
    now = time.time()
    # Codex kaydı (ve bitişi) hook olayından ÖNCE okunuyor.
    _write_lines(codex_day / "rollout-y.jsonl", [
        {"timestamp": _iso(now + 1), "type": "session_meta", "payload": {"id": "RY", "cwd": "C:/p", "originator": "codex_exec"}},
        {"timestamp": _iso(now + 1), "type": "turn_context",
         "payload": {"cwd": "C:/p", "model": "gpt-5.6-sol", "sandbox_policy": {"type": "read-only"}}},
        {"timestamp": _iso(now + 2), "type": "event_msg", "payload": {"type": "task_complete", "last_agent_message": "tamam"}},
    ])
    s = OfficeState()
    w = OfficeWatcher(s, events_path=events, codex_dir=tmp_path / "codex")
    w.poll()
    _write_lines(events, [
        ev("UserPromptSubmit", now, prompt="x"),
        ev("PreToolUse", now + 0.5, tool_name="Bash", tool_use_id="LY", background=True,
           command='codex exec -m gpt-5.6-sol "bir iş yap lütfen tamam mı"'),
    ])
    w.poll()
    assert s.workers["lane:LY"].status == ofis.DONE
    assert s.workers["lane:LY"].result == "tamam"


def test_watcher_ignores_interactive_codex_sessions(tmp_path):
    events = tmp_path / "events.jsonl"
    now = time.time()
    _write_lines(events, [
        ev("UserPromptSubmit", now, prompt="x"),
        ev("PreToolUse", now + 0.5, tool_name="Bash", tool_use_id="LZ", background=True,
           command='codex exec "bir iş yap lütfen tamam mı"'),
    ])
    codex_day = _codex_day(tmp_path)
    _write_lines(codex_day / "rollout-z.jsonl", [
        {"timestamp": _iso(now + 1), "type": "session_meta", "payload": {"id": "RZ", "originator": "codex_cli_rs"}},
        {"timestamp": _iso(now + 1), "type": "turn_context", "payload": {"model": "gpt-5.6-sol"}},
    ])
    s = OfficeState()
    OfficeWatcher(s, events_path=events, codex_dir=tmp_path / "codex").poll()
    assert s.workers["lane:LZ"].codex_rollout is None


# ── Canlı veride bulunanlar (2026-10-02) ─────────────────────────────────────
def _notification(tool_use_id: str, status: str = "completed", code: int = 0) -> str:
    return (
        "<task-notification>\n<task-id>b1</task-id>\n"
        f"<tool-use-id>{tool_use_id}</tool-use-id>\n<status>{status}</status>\n"
        f'<summary>Background command "x" completed (exit code {code})</summary>\n</task-notification>'
    )


def test_task_notification_finishes_background_lane_without_new_task():
    s = OfficeState()
    started_turn(s)
    s.apply(ev("PreToolUse", T0 + 2, tool_name="Bash", tool_use_id="bg", background=True,
               command='python ~/.claude/tools/bunny.py -p "bu dosyayı oku ve özetle" big.log'))
    s.apply(ev("Stop", T0 + 3))
    tasks_before = len(s.tasks)
    s.apply(ev("UserPromptSubmit", T0 + 60, prompt=_notification("bg")))
    lane = s.workers["lane:bg"]
    assert lane.status == ofis.DONE and lane.tracking == "tam"
    assert len(s.tasks) == tasks_before  # bildirim yeni görev açmaz
    chief = s.workers[f"claude:{SID}"]
    assert chief.status == ofis.WORKING
    s.apply(ev("Stop", T0 + 61))
    assert s.desk_stats["claude"]["done"] == 1  # yeniden açılan görev iki kez sayılmaz


def test_task_notification_with_nonzero_exit_marks_failure():
    s = OfficeState()
    started_turn(s)
    s.apply(ev("PreToolUse", T0 + 2, tool_name="Bash", tool_use_id="bg2", background=True,
               command='OPENCODE_DISABLE_CLAUDE_CODE=1 opencode run "küçük bir iş yap lütfen"'))
    s.apply(ev("UserPromptSubmit", T0 + 30, prompt=_notification("bg2", code=1)))
    assert s.workers["lane:bg2"].status == ofis.FAILED


def test_git_bash_paths_match_windows_paths():
    assert ofis._same_dir("/c/Users/yunus/Proje", r"C:\Users\yunus\Proje")
    assert ofis._same_dir('"/c/Users/yunus/Ders Notları/Aıron"', r"C:\Users\yunus\Ders Notları\Aıron")
    assert not ofis._same_dir("/c/Users/a", r"C:\Users\b")


def test_tail_detects_same_size_replacement(tmp_path):
    import os

    path = tmp_path / "e.jsonl"
    path.write_text('{"a": 1}\n', encoding="utf-8")
    tail = ofis._Tail(path)
    assert tail.read() == [{"a": 1}]
    replacement = tmp_path / "yeni.jsonl"
    replacement.write_text('{"b": 2}\n', encoding="utf-8")  # aynı boy
    os.replace(replacement, path)
    assert tail.read() == [{"b": 2}]
