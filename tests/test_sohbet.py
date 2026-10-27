"""Sohbet (Komuta ekranı): aynı oturumu süren konuşma, onay, Gemini bağlamı, terminali devralma."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.api import sohbet as sohbet_api  # noqa: E402
from backend.core import claude_jobs  # noqa: E402
from backend.core.sohbet import APPROVE_TEXT, Sohbet, SohbetError  # noqa: E402


class Jobs:
    """Elle sürülen iş kuyruğu: submit'e gelenleri kaydeder."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.calls: list[dict] = []
        self.cancelled: list[str] = []

    def submit(self, task, resume_of=None, origin="telefon", cwd=None, engine="claude", mode="auto", session_id=None):
        job_id = f"j{len(self.jobs) + 1}"
        self.calls.append({"task": task, "origin": origin, "cwd": cwd, "engine": engine, "session_id": session_id})
        self.jobs[job_id] = {"id": job_id, "status": "queued", "summary": "", "session_id": session_id,
                             "approval": "", "error": "", "trail": [], "last_step": "", "cost_usd": None, "bekci": []}
        return SimpleNamespace(id=job_id)

    def get(self, job_id):
        job = self.jobs.get(job_id)
        return dict(job) if job else None

    def cancel(self, job_id):
        self.cancelled.append(job_id)
        self.jobs[job_id]["status"] = "cancelled"
        return True

    def run(self, job_id, *steps):
        self.jobs[job_id].update(status="running", trail=list(steps), last_step=steps[-1] if steps else "")

    def finish(self, job_id, **values):
        self.jobs[job_id].update({"status": "done", "summary": "Tamam.", "finished_at": time.time()} | values)


def _setup(tmp_path: Path, active=None) -> tuple[Sohbet, Jobs]:
    jobs = Jobs()
    store = Sohbet(tmp_path / "sohbet.json", jobs=jobs, projects_dir=tmp_path / "projects",
                   session_active=active or (lambda sid: False))
    return store, jobs


def test_claude_chat_resumes_same_session(tmp_path):
    store, jobs = _setup(tmp_path)
    chat = store.create("claude")
    chat = store.send(chat["id"], "Dilcep'te balonu büyüt")
    assert chat["title"] == "Dilcep'te balonu büyüt" and chat["busy"] and chat["status"] == "sirada"
    assert jobs.calls[0] == {"task": "Dilcep'te balonu büyüt", "origin": "sohbet", "cwd": None,
                             "engine": "claude", "session_id": None}

    jobs.run("j1", "Read: LessonPath.tsx", "Edit: LessonPath.tsx")
    live = store.get(chat["id"])
    assert live["status"] == "calisiyor" and live["messages"][-1]["steps"] == ["Read: LessonPath.tsx", "Edit: LessonPath.tsx"]
    with pytest.raises(SohbetError):
        store.send(chat["id"], "araya giriyorum")  # ajan çalışırken ikinci mesaj yok

    jobs.finish("j1", summary="Balon 72px oldu.", session_id="abcd-1234-ef")
    done = store.get(chat["id"])
    assert not done["busy"] and done["messages"][-1]["text"] == "Balon 72px oldu."

    store.send(chat["id"], "commit at")
    assert jobs.calls[1]["session_id"] == "abcd-1234-ef"  # aynı oturum sürer


def test_new_session_id_after_resume_is_followed(tmp_path):
    """`-p --resume` yeni kimlik dönerse sonraki mesaj yenisini sürdürür."""
    store, jobs = _setup(tmp_path)
    chat = store.create("claude")
    store.send(chat["id"], "bir")
    jobs.finish("j1", session_id="aaaa-1111")
    store.send(chat["id"], "iki")
    jobs.finish("j2", session_id="bbbb-2222")
    store.send(chat["id"], "üç")
    assert [c["session_id"] for c in jobs.calls] == [None, "aaaa-1111", "bbbb-2222"]


def test_approval_answer_continues_session(tmp_path):
    store, jobs = _setup(tmp_path)
    chat = store.create("claude")
    store.send(chat["id"], "dalı gönder")
    jobs.finish("j1", status="needs_approval", summary="Hazır.\nONAY_GEREKLI: git push",
                approval="git push", session_id="cafe-0001")
    waiting = store.get(chat["id"])
    assert waiting["status"] == "onay" and waiting["approval"] == "git push"

    store.answer(chat["id"], approved=True)
    assert jobs.calls[1] == {"task": APPROVE_TEXT, "origin": "sohbet", "cwd": None,
                             "engine": "claude", "session_id": "cafe-0001"}
    with pytest.raises(SohbetError):
        store.answer(chat["id"], approved=False)  # artık bekleyen onay yok


def test_gemini_chat_carries_context_not_session(tmp_path):
    store, jobs = _setup(tmp_path)
    chat = store.create("gemini")
    store.send(chat["id"], "Expo 54 notlarını oku")
    jobs.finish("j1", summary="İki değişiklik var.", session_id="g-sess")
    store.send(chat["id"], "ikincisini aç")
    call = jobs.calls[1]
    assert call["engine"] == "gemini" and call["session_id"] is None
    assert "Yunus: Expo 54 notlarını oku" in call["task"] and "Sen: İki değişiklik var." in call["task"]
    assert call["task"].endswith("ikincisini aç")


def test_stop_delete_and_persistence(tmp_path):
    store, jobs = _setup(tmp_path)
    chat = store.create("claude", title="Deneme")
    store.send(chat["id"], "uzun iş")
    with pytest.raises(SohbetError):
        store.delete(chat["id"])  # çalışırken silinmez
    stopped = store.stop(chat["id"])
    assert jobs.cancelled == ["j1"] and stopped["messages"][-1]["status"] == "durdu"

    again = Sohbet(tmp_path / "sohbet.json", jobs=jobs, projects_dir=tmp_path / "projects")
    assert again.get(chat["id"])["title"] == "Deneme"
    again.delete(chat["id"])
    assert again.list() == []


def test_lost_job_marks_message_failed(tmp_path):
    store, jobs = _setup(tmp_path)
    chat = store.create("claude")
    store.send(chat["id"], "iş")
    jobs.jobs.clear()  # Chiron yeniden başladı, iş kaydı yok
    assert store.get(chat["id"])["messages"][-1]["status"] == "hata"


def _session_file(projects: Path, sid: str, cwd: Path, entrypoint="cli", title="Bekçi ve döngü", age=3600) -> Path:
    folder = projects / "C--x"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{sid}.jsonl"
    lines = [
        {"type": "attachment", "entrypoint": entrypoint, "cwd": str(cwd), "sessionId": sid},
        {"type": "user", "message": {"role": "user", "content": "selam"}, "entrypoint": entrypoint},
        {"type": "last-prompt", "lastPrompt": "devam et", "sessionId": sid},
        {"type": "ai-title", "aiTitle": title, "sessionId": sid},
    ]
    path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n", encoding="utf-8")
    stamp = time.time() - age
    os.utime(path, (stamp, stamp))
    return path


def test_terminal_sessions_lists_only_interactive(tmp_path):
    store, _ = _setup(tmp_path, active=lambda sid: sid == "2222-aaaa")
    projects = tmp_path / "projects"
    _session_file(projects, "1111-aaaa", tmp_path)
    _session_file(projects, "2222-aaaa", tmp_path, title="Açık olan")
    _session_file(projects, "3333-aaaa", tmp_path, entrypoint="sdk-cli")  # Chiron'un kendi işi
    _session_file(projects, "4444-aaaa", tmp_path, title="Yeni yazılmış", age=10)
    sessions = {s["session_id"]: s for s in store.terminal_sessions()}
    assert set(sessions) == {"1111-aaaa", "2222-aaaa", "4444-aaaa"}
    assert sessions["1111-aaaa"]["title"] == "Bekçi ve döngü" and sessions["1111-aaaa"]["last_prompt"] == "devam et"
    assert not sessions["1111-aaaa"]["open"]
    assert sessions["2222-aaaa"]["open"]  # ofis SessionEnd görmedi
    assert sessions["4444-aaaa"]["open"]  # kaydı az önce değişti


def test_takeover_refuses_open_session_and_resumes(tmp_path):
    store, jobs = _setup(tmp_path, active=lambda sid: sid == "2222-aaaa")
    projects = tmp_path / "projects"
    _session_file(projects, "1111-aaaa", tmp_path)
    _session_file(projects, "2222-aaaa", tmp_path)
    with pytest.raises(SohbetError, match="açık"):
        store.takeover("2222-aaaa")
    forced = store.takeover("2222-aaaa", force=True)
    assert forced["source"] == "terminal"

    chat = store.takeover("1111-aaaa")
    assert chat["title"] == "Bekçi ve döngü" and chat["cwd"] == str(tmp_path)
    assert chat["messages"][0]["role"] == "sistem"
    assert store.takeover("1111-aaaa")["id"] == chat["id"]  # ikinci kez: aynı sohbet
    store.send(chat["id"], "kaldığımız yerden devam")
    assert jobs.calls[0]["session_id"] == "1111-aaaa" and jobs.calls[0]["cwd"] == str(tmp_path)
    taken = {s["session_id"]: s["taken"] for s in store.terminal_sessions()}
    assert taken["1111-aaaa"] is True
    with pytest.raises(SohbetError):
        store.takeover("../../etc")


def test_api_flow(tmp_path, monkeypatch):
    store, jobs = _setup(tmp_path)
    monkeypatch.setattr(sohbet_api, "sohbet", store)
    app = FastAPI()
    app.include_router(sohbet_api.router)
    with TestClient(app) as client:
        created = client.post("/api/sohbet", json={"agent": "claude"}).json()["data"]["chat"]
        sent = client.post(f"/api/sohbet/{created['id']}/mesaj", json={"text": "merhaba"})
        busy = client.post(f"/api/sohbet/{created['id']}/mesaj", json={"text": "tekrar"})
        listed = client.get("/api/sohbet").json()["data"]["chats"]
        bad = client.post("/api/sohbet", json={"agent": "codex"})
        terminal = client.get("/api/sohbet/terminal").json()["data"]["sessions"]
    assert sent.status_code == 200 and sent.json()["data"]["chat"]["busy"]
    assert busy.status_code == 409
    assert listed[0]["id"] == created["id"]
    assert bad.status_code == 409 and terminal == []


# ── claude_jobs: oturumu kimliğiyle sürdürme + araç adımları ─────────────────

def test_claude_jobs_session_id_and_trail(tmp_path):
    script = "\n".join([
        "import json",
        "print(json.dumps({'type':'assistant','message':{'content':[{'type':'tool_use','name':'Read','input':{'file_path':'a.py'}}]}}), flush=True)",
        "print(json.dumps({'type':'assistant','message':{'content':[{'type':'tool_use','name':'Bash','input':{'command':'pytest'}}]}}), flush=True)",
        "print(json.dumps({'type':'result','subtype':'success','result':'Bitti.','session_id':'ffff-0002'}), flush=True)",
    ])
    seen: list[tuple[str | None, str]] = []
    procs: list[subprocess.Popen] = []

    def launch(job, log_path):
        seen.append((job.session_id, job.origin))
        proc = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, stdin=subprocess.PIPE)
        procs.append(proc)
        return proc

    manager = claude_jobs.ClaudeJobs(jobs_dir=tmp_path / "jobs", launcher=launch, time_limit=20)
    try:
        job = manager.submit("devam", origin="sohbet", session_id="eeee-0001")
        deadline = time.monotonic() + 15
        while manager.get(job.id)["status"] in claude_jobs.ACTIVE and time.monotonic() < deadline:
            time.sleep(0.02)
        data = manager.get(job.id)
        assert seen == [("eeee-0001", "sohbet")]
        assert data["status"] == "done" and data["session_id"] == "ffff-0002"
        assert data["trail"] == ["Read: a.py", "Bash: pytest"] and data["notified"] is True
        with pytest.raises(ValueError):
            manager.submit("x", session_id="eeee-0001", engine="gemini")
        with pytest.raises(ValueError):
            manager.submit("x", session_id="; rm -rf")
    finally:
        manager.shutdown()
        for proc in procs:
            if proc.poll() is None:
                proc.kill()


def test_claude_args_resume_with_chat_note(tmp_path, monkeypatch):
    captured: dict = {}

    class FakePopen:
        def __init__(self, args, **kwargs):
            captured["args"], captured["cwd"] = args, kwargs.get("cwd")

    monkeypatch.setattr(claude_jobs, "find_claude_exe", lambda: "claude.exe")
    monkeypatch.setattr(claude_jobs.subprocess, "Popen", FakePopen)
    manager = claude_jobs.ClaudeJobs(jobs_dir=tmp_path / "jobs", launcher=lambda *a: None)
    job = claude_jobs.Job(id="abcd0001", task="t", origin="sohbet", session_id="sess-0001", cwd=str(tmp_path))
    manager._launch_engine(job, tmp_path / "x.jsonl")
    args = captured["args"]
    assert args[args.index("--resume") + 1] == "sess-0001"
    assert args[args.index("--append-system-prompt") + 1] == claude_jobs.CHAT_NOTE
    assert captured["cwd"] == str(tmp_path)
