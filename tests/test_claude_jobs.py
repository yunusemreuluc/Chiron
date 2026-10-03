from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import remote
from backend.core import claude_jobs


TERMINAL_STATUSES = {
    "done",
    "failed",
    "needs_approval",
    "timeout",
    "cancelled",
    "interrupted",
}


def _stream_script(events: list[dict] | None = None, *, sleep: float = 0) -> str:
    lines = [json.dumps(event) for event in events or []]
    return "\n".join(
        [
            "import time",
            *(f"print({line!r}, flush=True)" for line in lines),
            *([f"time.sleep({sleep!r})"] if sleep else []),
        ]
    )


def _success_events(result: str = "İş tamamlandı.") -> list[dict]:
    return [
        {"type": "system", "subtype": "init", "session_id": "s1"},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "pytest"},
                    }
                ]
            },
        },
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": result,
            "session_id": "s1",
            "total_cost_usd": 0.01,
        },
    ]


def _launcher(
    script: str,
    processes: list[subprocess.Popen],
    calls: list[tuple[str, str | None, str | None]] | None = None,
) -> Callable:
    def launch(job: claude_jobs.Job, log_path: Path) -> subprocess.Popen:
        if calls is not None:
            calls.append((job.id, job.session_id, job.resume_of))
        proc = subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
        )
        processes.append(proc)
        return proc

    return launch


@pytest.fixture
def processes():
    started: list[subprocess.Popen] = []
    yield started
    for proc in started:
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


@pytest.fixture
def job_managers():
    managers: list[claude_jobs.ClaudeJobs] = []
    yield managers
    for manager in managers:
        manager.shutdown()


def _manager(
    jobs_dir: Path,
    script: str,
    processes: list[subprocess.Popen],
    job_managers: list[claude_jobs.ClaudeJobs],
    *,
    time_limit: float = 10,
    calls: list[tuple[str, str | None, str | None]] | None = None,
) -> claude_jobs.ClaudeJobs:
    manager = claude_jobs.ClaudeJobs(
        jobs_dir=jobs_dir,
        launcher=_launcher(script, processes, calls),
        time_limit=time_limit,
    )
    job_managers.append(manager)
    return manager


def _wait_for(
    manager: claude_jobs.ClaudeJobs,
    job_id: str,
    expected: str | set[str] | None = None,
    *,
    timeout: float = 10,
) -> dict:
    wanted = TERMINAL_STATUSES if expected is None else {expected} if isinstance(expected, str) else expected
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = manager.get(job_id)
        if last is not None and last["status"] in wanted:
            return last
        time.sleep(0.02)
    pytest.fail(f"İş beklenen duruma gelmedi; beklenen={wanted}, son={last}")


def _wait_for_process(
    manager: claude_jobs.ClaudeJobs,
    processes: list[subprocess.Popen],
    *,
    timeout: float = 10,
) -> subprocess.Popen:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if processes and manager._proc is processes[-1]:
            return processes[-1]
        time.sleep(0.02)
    pytest.fail("Alt süreç ClaudeJobs yöneticisine bağlanmadı.")


def test_successful_job_records_result_steps_and_jsonl(tmp_path, processes, job_managers):
    manager = _manager(
        tmp_path,
        _stream_script(_success_events()),
        processes,
        job_managers,
    )

    job = manager.submit("testleri çalıştır")
    result = _wait_for(manager, job.id, "done")

    assert result["summary"] == "İş tamamlandı."
    assert result["session_id"] == "s1"
    assert result["steps"] >= 1
    assert result["last_step"] == "Bash: pytest"
    log_path = tmp_path / f"{job.id}.jsonl"
    assert log_path.exists()
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert events == _success_events()


def test_approval_marker_changes_job_status(tmp_path, processes, job_managers):
    summary = "Hazırlık tamamlandı.\nONAY_GEREKLI: dosyaları sil"
    manager = _manager(
        tmp_path,
        _stream_script(_success_events(summary)),
        processes,
        job_managers,
    )

    result = _wait_for(manager, manager.submit("temizle").id, "needs_approval")

    assert result["summary"] == summary
    assert result["approval"] == "dosyaları sil"


def test_process_exit_without_result_fails(tmp_path, processes, job_managers):
    events = [{"type": "system", "subtype": "init", "session_id": "s1"}]
    manager = _manager(tmp_path, _stream_script(events), processes, job_managers)

    result = _wait_for(manager, manager.submit("sonuçsuz iş").id, "failed")

    assert "sonuç vermeden" in result["error"]


def test_error_max_turns_result_fails(tmp_path, processes, job_managers):
    events = [
        {"type": "system", "subtype": "init", "session_id": "s1"},
        {
            "type": "result",
            "subtype": "error_max_turns",
            "is_error": True,
            "result": "Sınır doldu.",
            "session_id": "s1",
        },
    ]
    manager = _manager(tmp_path, _stream_script(events), processes, job_managers)

    result = _wait_for(manager, manager.submit("uzun iş").id, "failed")

    assert result["error"] == "error_max_turns"


def test_time_limit_kills_process_and_marks_timeout(tmp_path, processes, job_managers):
    manager = _manager(
        tmp_path,
        _stream_script(sleep=30),
        processes,
        job_managers,
        time_limit=1,
    )

    result = _wait_for(manager, manager.submit("takılan iş").id, "timeout")

    assert result["status"] == "timeout"
    assert processes[0].poll() is not None


def test_cancel_running_and_queued_jobs(tmp_path, processes, job_managers):
    manager = _manager(
        tmp_path,
        _stream_script(sleep=30),
        processes,
        job_managers,
    )
    running = manager.submit("çalışan")
    _wait_for(manager, running.id, "running")
    _wait_for_process(manager, processes)
    queued = manager.submit("kuyruktaki")

    assert manager.cancel(queued.id) is True
    assert _wait_for(manager, queued.id, "cancelled")["status"] == "cancelled"
    assert manager.cancel(running.id) is True
    assert _wait_for(manager, running.id, "cancelled")["status"] == "cancelled"


def test_only_one_job_runs_and_second_has_queue_position_one(tmp_path, processes, job_managers):
    manager = _manager(
        tmp_path,
        _stream_script(sleep=30),
        processes,
        job_managers,
    )
    first = manager.submit("birinci")
    _wait_for(manager, first.id, "running")
    _wait_for_process(manager, processes)

    second = manager.submit("ikinci")
    second_data = manager.get(second.id)

    assert second_data is not None
    assert second_data["status"] == "queued"
    assert second_data["queue_position"] == 1
    manager.cancel(second.id)
    manager.cancel(first.id)
    _wait_for(manager, first.id, "cancelled")


def test_queue_and_task_limits_are_enforced(tmp_path, processes, job_managers):
    manager = _manager(
        tmp_path,
        _stream_script(sleep=30),
        processes,
        job_managers,
    )

    with pytest.raises(ValueError, match="boş"):
        manager.submit("   ")
    with pytest.raises(ValueError, match="en fazla"):
        manager.submit("x" * (claude_jobs.MAX_TASK_CHARS + 1))

    running = manager.submit("çalışan")
    _wait_for(manager, running.id, "running")
    _wait_for_process(manager, processes)
    queued = [manager.submit(f"kuyruk {index}") for index in range(claude_jobs.MAX_QUEUE)]
    with pytest.raises(ValueError, match="Kuyruk dolu"):
        manager.submit("fazla")

    for job in queued:
        manager.cancel(job.id)
    manager.cancel(running.id)
    _wait_for(manager, running.id, "cancelled")


def test_resume_requires_known_job_and_reuses_parent_session(tmp_path, processes, job_managers):
    calls: list[tuple[str, str | None, str | None]] = []
    manager = _manager(
        tmp_path,
        _stream_script(_success_events()),
        processes,
        job_managers,
        calls=calls,
    )

    with pytest.raises(ValueError, match="bulunamadı"):
        manager.submit("devam", resume_of="bilinmeyen")

    parent = manager.submit("ilk iş")
    _wait_for(manager, parent.id, "done")
    resumed = manager.submit("devam et", resume_of=parent.id)
    _wait_for(manager, resumed.id, "done")

    resumed_call = next(call for call in calls if call[0] == resumed.id)
    assert resumed.resume_of == parent.id
    assert resumed_call[1] == "s1"
    assert resumed_call[2] == parent.id


def test_running_job_on_disk_is_reloaded_as_interrupted(tmp_path, processes, job_managers):
    stored = claude_jobs.Job(id="deadbeef", task="yarım iş", status="running")
    (tmp_path / "deadbeef.json").write_text(
        json.dumps(asdict(stored), ensure_ascii=False),
        encoding="utf-8",
    )

    manager = _manager(tmp_path, _stream_script(), processes, job_managers)

    result = manager.get("deadbeef")
    assert result is not None
    assert result["status"] == "interrupted"
    assert result["finished_at"] is not None
    persisted = json.loads((tmp_path / "deadbeef.json").read_text(encoding="utf-8"))
    assert persisted["status"] == "interrupted"


@pytest.mark.parametrize(
    ("text", "approval"),
    [
        ("Bitti.\nONAY_GEREKLI: dosyaları sil", "dosyaları sil"),
        ("Bitti.\n**ONAY_GEREKLI:** dosyaları sil", "dosyaları sil"),
        ("Bitti.", ""),
    ],
)
def test_split_approval(text, approval):
    summary, extracted = claude_jobs.split_approval(text)

    assert summary == text
    assert extracted == approval


def test_find_claude_exe_rejects_cmd_without_exe_and_returns_neighbor_exe(
    tmp_path, monkeypatch
):
    cmd = tmp_path / "claude.CMD"
    cmd.write_text("", encoding="utf-8")
    monkeypatch.setattr(claude_jobs.shutil, "which", lambda name: str(cmd))

    assert claude_jobs.find_claude_exe() is None

    exe = (
        tmp_path
        / "node_modules"
        / "@anthropic-ai"
        / "claude-code"
        / "bin"
        / "claude.exe"
    )
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    assert claude_jobs.find_claude_exe() == str(exe)


def test_remote_claude_endpoints(tmp_path, monkeypatch, processes, job_managers):
    manager = _manager(
        tmp_path,
        _stream_script(sleep=30),
        processes,
        job_managers,
    )
    monkeypatch.setattr(remote.claude_jobs, "jobs", manager)
    app = FastAPI()
    app.include_router(remote.router)

    with TestClient(app) as client:
        created = client.post("/api/remote/claude", json={"task": "test et"})
        empty = client.post("/api/remote/claude", json={"task": "   "})
        missing = client.get("/api/remote/claude/bilinmeyen")
        listed = client.get("/api/remote/claude")
        job_id = created.json()["data"]["id"]
        _wait_for_process(manager, processes)
        cancelled = client.post(f"/api/remote/claude/{job_id}/cancel")

    assert created.status_code == 200
    assert job_id
    assert empty.status_code == 409
    assert missing.status_code == 404
    assert listed.status_code == 200
    assert any(job["id"] == job_id for job in listed.json()["data"]["jobs"])
    assert cancelled.status_code == 200
    assert cancelled.json()["success"] is True
    assert _wait_for(manager, job_id, "cancelled")["status"] == "cancelled"


# ── Astra incelemesinin regresyonları (2026-10-03) ───────────────────────────


def _pid_alive(pid: int) -> bool:
    import psutil

    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def test_orphan_grandchild_holding_stdout_is_killed(tmp_path, processes, job_managers):
    """Ebeveyn çıkar, torun stdout'u açık tutar: eskiden kuyruk sonsuza kilitleniyordu."""
    pid_file = tmp_path / "grandchild.pid"
    script = "\n".join(
        [
            "import subprocess, sys",
            "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],"
            " stdout=sys.stdout, stderr=sys.stderr)",
            f"open({str(pid_file)!r}, 'w').write(str(p.pid))",
            "print('{\"type\":\"result\",\"subtype\":\"success\",\"is_error\":false,"
            "\"result\":\"tamam\",\"session_id\":\"s1\"}', flush=True)",
        ]
    )
    manager = _manager(tmp_path / "jobs", script, processes, job_managers)
    job = manager.submit("görev")
    status = _wait_for(manager, job.id, "done", timeout=20)
    assert status["summary"] == "tamam"
    grandchild = int(pid_file.read_text())
    deadline = time.time() + 5
    while _pid_alive(grandchild) and time.time() < deadline:
        time.sleep(0.1)
    assert not _pid_alive(grandchild)


def test_time_limit_kills_whole_tree(tmp_path, processes, job_managers):
    pid_file = tmp_path / "grandchild.pid"
    script = "\n".join(
        [
            "import subprocess, sys, time",
            "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])",
            f"open({str(pid_file)!r}, 'w').write(str(p.pid))",
            "time.sleep(60)",
        ]
    )
    manager = _manager(tmp_path / "jobs", script, processes, job_managers, time_limit=1.5)
    job = manager.submit("görev")
    assert _wait_for(manager, job.id, "timeout", timeout=20)["status"] == "timeout"
    deadline = time.time() + 5
    grandchild = int(pid_file.read_text())
    while _pid_alive(grandchild) and time.time() < deadline:
        time.sleep(0.1)
    assert not _pid_alive(grandchild)


def test_cancel_before_process_registered_kills_it(tmp_path, processes, job_managers):
    """İş 'running' olup süreç kaydedilmeden gelen iptal kaybolmamalı."""
    holder: dict[str, claude_jobs.ClaudeJobs] = {}
    base = _launcher(_stream_script(_success_events(), sleep=30), processes)

    def launch(job, log_path):
        proc = base(job, log_path)
        assert holder["m"].cancel(job.id) is True  # tam kayıttan önce
        return proc

    manager = claude_jobs.ClaudeJobs(jobs_dir=tmp_path / "jobs", launcher=launch, time_limit=30)
    holder["m"] = manager
    job_managers.append(manager)
    started = time.time()
    job = manager.submit("görev")
    assert _wait_for(manager, job.id, "cancelled", timeout=15)["status"] == "cancelled"
    assert time.time() - started < 10
    assert processes[-1].poll() is not None


def test_save_failure_does_not_kill_worker(tmp_path, processes, job_managers, monkeypatch):
    manager = _manager(tmp_path / "jobs", _stream_script(_success_events()), processes, job_managers)

    def broken_replace(*args, **kwargs):
        raise OSError("disk dolu")

    monkeypatch.setattr(claude_jobs.os, "replace", broken_replace)
    first = manager.submit("bir")
    second = manager.submit("iki")
    assert _wait_for(manager, first.id, "done")["status"] == "done"
    assert _wait_for(manager, second.id, "running")["status"] == "running"  # kuyruk kilitlenmedi


def test_old_job_files_are_pruned_from_disk(tmp_path, processes, job_managers, monkeypatch):
    monkeypatch.setattr(claude_jobs, "KEEP_JOBS", 2)
    jobs_dir = tmp_path / "jobs"
    manager = _manager(jobs_dir, _stream_script(_success_events()), processes, job_managers)
    ids = []
    for index in range(4):
        job = manager.submit(f"görev {index}")
        _wait_for(manager, job.id, "done")
        ids.append(job.id)
    manager.submit("son")  # _trim tetiklenir
    on_disk = {p.name.split(".", 1)[0] for p in jobs_dir.glob("*.json*")}
    assert ids[0] not in on_disk
    assert ids[-1] in on_disk


def test_shutdown_rejects_new_jobs_and_cancels_queue(tmp_path, processes, job_managers):
    manager = _manager(
        tmp_path / "jobs", _stream_script(_success_events(), sleep=30), processes, job_managers
    )
    running = manager.submit("bir")
    queued = manager.submit("iki")
    _wait_for(manager, running.id, "running")
    manager.shutdown()
    assert manager.get(queued.id)["status"] == "cancelled"
    assert _wait_for(manager, running.id, "cancelled", timeout=15)["status"] == "cancelled"
    with pytest.raises(ValueError):
        manager.submit("üç")


def test_job_object_failure_fails_job_and_kills_process(tmp_path, processes, job_managers, monkeypatch):
    """Astra 2. tur: güvence kurulamazsa süreç çalıştırılmaz, kuyruk kilitlenmez."""
    if claude_jobs.os.name != "nt":
        pytest.skip("Job Object yalnız Windows'ta")

    def broken_job() -> int:
        raise OSError("job yok")

    monkeypatch.setattr(claude_jobs, "_create_kill_on_close_job", broken_job)
    manager = _manager(
        tmp_path / "jobs", _stream_script(_success_events(), sleep=30), processes, job_managers
    )
    first = manager.submit("bir")
    status = _wait_for(manager, first.id, "failed", timeout=10)
    assert "Job Object" in status["error"]
    processes[-1].wait(timeout=5)
    monkeypatch.undo()
    second = manager.submit("iki")
    assert _wait_for(manager, second.id, "running")["status"] == "running"  # kuyruk kilitlenmedi


def test_log_quota_is_never_exceeded(tmp_path, processes, job_managers, monkeypatch):
    monkeypatch.setattr(claude_jobs, "MAX_LOG_BYTES", 200)
    big = {"type": "assistant", "message": {"content": [{"type": "text", "text": "x" * 1000}]}}
    manager = _manager(
        tmp_path / "jobs", _stream_script([big, *_success_events()]), processes, job_managers
    )
    job = manager.submit("görev")
    assert _wait_for(manager, job.id, "done")["status"] == "done"
    assert (tmp_path / "jobs" / f"{job.id}.jsonl").stat().st_size <= 200


def test_prune_only_touches_job_files(tmp_path, processes, job_managers):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    keep = ["deadbeef.json.backup", "notlar.txt", "DEADBEEF.json"]
    for name in keep + ["deadbeef.json", "deadbeef.jsonl", "cafebabe.json.tmp"]:
        (jobs_dir / name).write_text("{}" if name == "deadbeef.json" else "x", encoding="utf-8")
    manager = _manager(jobs_dir, _stream_script(_success_events()), processes, job_managers)
    manager._jobs.clear()
    manager._prune_disk()
    assert sorted(p.name for p in jobs_dir.iterdir()) == sorted(keep)


def test_updates_and_acknowledge(tmp_path, processes, job_managers, monkeypatch):
    manager = _manager(tmp_path / "jobs", _stream_script(_success_events()), processes, job_managers)
    job = manager.submit("görev")
    _wait_for(manager, job.id, "done")
    assert [u["id"] for u in manager.updates()] == [job.id]
    assert manager.acknowledge([job.id, "yok"]) == 1
    assert manager.updates() == []
    # Kalıcı: yeniden açılınca tekrar bildirilmez.
    reloaded = claude_jobs.ClaudeJobs(jobs_dir=tmp_path / "jobs", launcher=lambda *a: None)
    assert reloaded.updates() == []

    monkeypatch.setattr(remote.claude_jobs, "jobs", manager)
    app = FastAPI()
    app.include_router(remote.router)
    client = TestClient(app)
    second = manager.submit("iki")
    _wait_for(manager, second.id, "done")
    listed = client.get("/api/remote/claude/updates").json()["data"]["jobs"]
    assert [j["id"] for j in listed] == [second.id]
    assert client.post("/api/remote/claude/ack", json={"ids": [second.id]}).json()["data"]["updated"] == 1
    assert client.get("/api/remote/claude/updates").json()["data"]["jobs"] == []
    assert client.get("/api/remote/claude/updates").json()["data"]["active"] == 0
