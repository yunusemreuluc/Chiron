"""Claude kotası (Ajan İstasyonu adım 6): rate_limit_event okunur, %90'da yeni Claude işi başlamaz."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core import claude_jobs  # noqa: E402
from backend.core.pano import Pano, PanoError  # noqa: E402


def _rate_event(five: float, week: float, *, status: str = "allowed", resets: float | None = None) -> dict:
    resets = resets or time.time() + 3600
    return {
        "type": "rate_limit_event",
        "rate_limit_info": {
            "status": status,
            "resetsAt": int(resets),
            "unifiedWindows": {
                "five_hour": {"utilization": five, "resetsAt": int(resets)},
                "seven_day": {"utilization": week, "resetsAt": int(resets + 86400)},
            },
        },
    }


class LimitJobs:
    """Sahte kuyruk: limits() elle ayarlanır, submit kaydedilir."""

    def __init__(self) -> None:
        self.state: dict = {}
        self.submitted: list[str] = []

    def limits(self) -> dict:
        return dict(self.state)

    def set(self, five: float, week: float = 0.1, *, resets: float | None = None, blocked: float | None = None) -> None:
        resets = resets if resets is not None else time.time() + 3600
        self.state = {
            "status": "rejected" if blocked else "allowed",
            "ts": time.time(),
            "five_hour": {"used": five, "resets_at": resets},
            "seven_day": {"used": week, "resets_at": resets + 86400},
        }
        if blocked:
            self.state["blocked_until"] = blocked

    def submit(self, task, resume_of=None, origin="telefon", cwd=None, engine="claude", mode="auto"):
        self.submitted.append(engine)
        return SimpleNamespace(id=f"j{len(self.submitted)}")

    def get(self, job_id):
        return {"id": job_id, "status": "running", "steps": 0, "last_step": ""}

    def cancel(self, job_id):
        return True


def _board(tmp_path: Path) -> tuple[Pano, LimitJobs]:
    jobs = LimitJobs()
    return Pano(store_path=tmp_path / "pano.json", jobs=jobs), jobs


def test_stop_level_blocks_new_claude_work_but_not_other_agents(tmp_path):
    board, jobs = _board(tmp_path)
    jobs.set(0.93)
    claude_card = board.create("Claude işi")
    gemini_card = board.create("Okuma", agent="gemini")

    with pytest.raises(PanoError, match="%93"):
        board.start(claude_card["id"])
    with pytest.raises(PanoError, match="kotası"):
        board.plan(claude_card["id"])
    board.start(gemini_card["id"])

    assert jobs.submitted == ["gemini"]
    quota = board.snapshot()["agents"]["claude"]
    assert quota["level"] == "stop" and "5 saatlik" in quota["reason"]


@pytest.mark.parametrize(
    ("five", "week", "level"),
    [(0.1, 0.2, "ok"), (0.55, 0.2, "info"), (0.2, 0.8, "warn"), (0.89, 0.1, "warn"), (0.2, 0.95, "stop")],
)
def test_levels_follow_the_fullest_window(tmp_path, five, week, level):
    board, jobs = _board(tmp_path)
    jobs.set(five, week)
    assert board.snapshot()["agents"]["claude"]["level"] == level


def test_warn_level_still_starts_work(tmp_path):
    board, jobs = _board(tmp_path)
    jobs.set(0.8)
    board.start(board.create("Kart")["id"])
    assert jobs.submitted == ["claude"]


def test_window_that_already_reset_counts_as_empty(tmp_path):
    board, jobs = _board(tmp_path)
    jobs.set(0.97, 0.97, resets=time.time() - 60 - 86400)
    assert board.snapshot()["agents"]["claude"]["level"] == "ok"
    board.start(board.create("Kart")["id"])


def test_rejected_status_blocks_until_reset(tmp_path):
    board, jobs = _board(tmp_path)
    jobs.set(0.2, blocked=time.time() + 600)
    with pytest.raises(PanoError, match="doldu"):
        board.start(board.create("Kart")["id"])


def test_no_quota_seen_yet_is_ok(tmp_path):
    board, _ = _board(tmp_path)
    quota = board.snapshot()["agents"]["claude"]
    assert quota["level"] == "ok" and quota["seen"] is None


# ── Gerçek ClaudeJobs: olay okunur, saklanır, iş kaydı sanılmaz ────────────────


def _manager(tmp_path: Path, events: list[dict], procs: list) -> claude_jobs.ClaudeJobs:
    script = "\n".join(f"print({json.dumps(e)!r}, flush=True)" for e in events)

    def launch(job, log_path):
        proc = subprocess.Popen(
            [sys.executable, "-c", script], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE
        )
        procs.append(proc)
        return proc

    return claude_jobs.ClaudeJobs(jobs_dir=tmp_path / "jobs", launcher=launch, time_limit=10)


def test_rate_limit_event_is_stored_and_survives_restart(tmp_path):
    procs: list = []
    result = {"type": "result", "subtype": "success", "is_error": False, "result": "tamam", "session_id": "s"}
    manager = _manager(tmp_path, [{"type": "system", "session_id": "s"}, _rate_event(0.53, 0.25), result], procs)
    try:
        job = manager.submit("iş")
        deadline = time.monotonic() + 10
        while manager.get(job.id)["status"] in claude_jobs.ACTIVE and time.monotonic() < deadline:
            time.sleep(0.02)
        limits = manager.limits()
        assert limits["five_hour"]["used"] == pytest.approx(0.53)
        assert limits["seven_day"]["used"] == pytest.approx(0.25)
        assert manager.get(job.id)["status"] == "done"
    finally:
        manager.shutdown()
        for proc in procs:
            proc.wait(timeout=5)

    reloaded = claude_jobs.ClaudeJobs(jobs_dir=tmp_path / "jobs", launcher=lambda *a: None)
    assert reloaded.limits()["five_hour"]["used"] == pytest.approx(0.53)
    # limits.json iş kaydı sanılmadı ve budamada silinmedi
    assert all(j["id"] != "limits" for j in reloaded.list())
    assert (tmp_path / "jobs" / claude_jobs.LIMITS_FILE).exists()
