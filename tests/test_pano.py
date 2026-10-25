from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import pano as pano_api
from backend.core import claude_jobs
from backend.core.pano import Pano, PanoError


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


class FakeJobs:
    """Pano durumlarını süreç başlatmadan elle değiştirebilen küçük iş kuyruğu."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.submissions: list[dict] = []
        self.cancelled: list[str] = []
        self.submit_errors: list[ValueError] = []
        self._next = 1

    def submit(
        self, task: str, resume_of: str | None = None, origin: str = "telefon", cwd: str | None = None
    ) -> SimpleNamespace:
        if self.submit_errors:
            raise self.submit_errors.pop(0)
        job_id = f"job-{self._next}"
        self._next += 1
        self.submissions.append({"id": job_id, "task": task, "resume_of": resume_of, "origin": origin})
        self.jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "summary": "",
            "session_id": None,
            "approval": "",
            "error": "",
            "steps": 0,
            "last_step": "",
            "cost_usd": 0.0,
        }
        return SimpleNamespace(id=job_id)

    def get(self, job_id: str) -> dict | None:
        job = self.jobs.get(job_id)
        return dict(job) if job is not None else None

    def cancel(self, job_id: str) -> bool:
        if job_id not in self.jobs or self.jobs[job_id]["status"] not in claude_jobs.ACTIVE:
            return False
        self.cancelled.append(job_id)
        return True

    def set(self, job_id: str, **values: object) -> None:
        self.jobs[job_id].update(values)


def _pano(tmp_path: Path) -> tuple[Pano, FakeJobs]:
    jobs = FakeJobs()
    return Pano(store_path=tmp_path / "pano.json", jobs=jobs), jobs


def test_create_assigns_ids_and_rejects_blank_title(tmp_path):
    board, _ = _pano(tmp_path)

    first = board.create("İlk kart")
    second = board.create("İkinci kart")

    assert (first["id"], first["status"]) == ("K-001", "bekliyor")
    assert second["id"] == "K-002"
    with pytest.raises(PanoError):
        board.create("   ")


def test_start_submits_full_card_task_with_pano_origin(tmp_path):
    board, jobs = _pano(tmp_path)
    card = board.create("Testleri çalıştır", "Ayrıntılı görev")

    started = board.start(card["id"])

    assert started["status"] == "calisiyor"
    assert jobs.submissions == [{
        "id": "job-1",
        "task": "Kart K-001: Testleri çalıştır\n\nAyrıntılı görev",
        "resume_of": None,
        "origin": "pano",
    }]


def test_done_job_updates_summary_cost_and_clears_active_job(tmp_path):
    board, jobs = _pano(tmp_path)
    card = board.start(board.create("Bitir")["id"])
    jobs.set(
        card["job_id"], status="done", summary="Tamamlandı", session_id="s1",
        steps=3, last_step="Bash: pytest", cost_usd=0.01,
    )

    result = board.snapshot()["cards"][0]

    assert result["status"] == "bitti"
    assert result["summary"] == "Tamamlandı"
    assert result["job_id"] is None
    assert result["cost_usd"] == 0.01
    assert result["steps"] == 3
    assert result["last_step"] == "Bash: pytest"


@pytest.mark.parametrize(
    ("approved", "prefix"),
    [(True, "Onaylandı:"), (False, "Onaylanmadı:")],
)
def test_answer_resumes_approval_job(tmp_path, approved, prefix):
    board, jobs = _pano(tmp_path)
    card = board.start(board.create("Onaylı iş")["id"])
    jobs.set(card["job_id"], status="needs_approval", session_id="s1", approval="silinsin mi?")

    awaiting = board.get(card["id"])
    answered = board.answer(card["id"], approved)

    assert awaiting is not None
    assert awaiting["status"] == "onay"
    assert awaiting["approval"] == "silinsin mi?"
    assert answered["status"] == "calisiyor"
    assert jobs.submissions[-1]["resume_of"] == "job-1"
    assert jobs.submissions[-1]["task"].startswith(prefix)
    assert jobs.submissions[-1]["origin"] == "pano"


def test_pause_cancels_then_resumes_after_cancelled(tmp_path):
    board, jobs = _pano(tmp_path)
    card = board.start(board.create("Duraklat")["id"])
    jobs.set(card["job_id"], status="running", session_id="s1")

    stopping = board.pause(card["id"])
    jobs.set(card["job_id"], status="cancelled", session_id="s1")
    paused = board.get(card["id"])
    resumed = board.start(card["id"])

    assert stopping["status"] == "calisiyor"
    assert stopping["stopping"] is True
    assert jobs.cancelled == ["job-1"]
    assert paused is not None
    assert paused["status"] == "duraklatildi"
    assert resumed["status"] == "calisiyor"
    assert jobs.submissions[-1]["resume_of"] == "job-1"
    assert jobs.submissions[-1]["task"].startswith("Durdurulmuştun.")


def test_stop_cancels_running_or_ends_waiting_and_rejects_final_card(tmp_path):
    board, jobs = _pano(tmp_path)
    running = board.start(board.create("Çalışan")["id"])
    jobs.set(running["job_id"], status="running")

    stopping = board.stop(running["id"])
    jobs.set(running["job_id"], status="cancelled")
    stopped = board.get(running["id"])
    waiting = board.create("Bekleyen")
    ended = board.stop(waiting["id"])

    assert stopping["stopping"] is True
    assert stopped is not None
    assert stopped["status"] == "iptal"
    assert ended["status"] == "iptal"
    with pytest.raises(PanoError):
        board.stop(ended["id"])


def test_failed_job_can_resume_with_previous_error_note(tmp_path):
    board, jobs = _pano(tmp_path)
    card = board.start(board.create("Hatalı iş")["id"])
    jobs.set(card["job_id"], status="failed", error="pytest kırıldı", session_id="s1")

    failed = board.get(card["id"])
    restarted = board.start(card["id"])

    assert failed is not None
    assert failed["status"] == "hata"
    assert failed["error"] == "pytest kırıldı"
    assert restarted["status"] == "calisiyor"
    assert jobs.submissions[-1]["resume_of"] == "job-1"
    assert jobs.submissions[-1]["task"].startswith("Önceki deneme")


def test_missing_resume_session_retries_with_full_task_but_full_queue_error_preserves_card(tmp_path):
    board, jobs = _pano(tmp_path)
    card = board.start(board.create("Yeniden dene", "Detay")["id"])
    jobs.set(card["job_id"], status="failed", error="hata", session_id="s1")
    assert board.get(card["id"])["status"] == "hata"
    jobs.submit_errors.append(ValueError("Sürdürülecek iş bulunamadı ya da oturumu yok."))

    retried = board.start(card["id"])

    assert retried["status"] == "calisiyor"
    assert jobs.submissions[-1]["resume_of"] is None
    assert jobs.submissions[-1]["task"].startswith("Kart K-001: Yeniden dene")

    jobs.set(retried["job_id"], status="failed", error="yine hata", session_id="s2")
    assert board.get(card["id"])["status"] == "hata"
    jobs.submit_errors.append(ValueError("Kuyruk dolu; önceki işler bitsin."))

    with pytest.raises(PanoError, match="Kuyruk dolu"):
        board.start(card["id"])
    assert board.get(card["id"])["status"] == "hata"


def test_missing_job_record_marks_working_card_failed(tmp_path):
    board, jobs = _pano(tmp_path)
    card = board.start(board.create("Kayıp iş")["id"])
    del jobs.jobs[card["job_id"]]

    result = board.get(card["id"])

    assert result is not None
    assert result["status"] == "hata"
    assert result["error"] == "İş kaydı bulunamadı."


def test_edit_only_waiting_and_delete_only_non_working_cards(tmp_path):
    board, _ = _pano(tmp_path)
    waiting = board.create("Düzenle")
    edited = board.edit(waiting["id"], title="Yeni başlık", detail="Yeni ayrıntı")
    running = board.start(board.create("Çalışıyor")["id"])

    assert edited["title"] == "Yeni başlık"
    with pytest.raises(PanoError):
        board.edit(running["id"], title="Olmaz")
    with pytest.raises(PanoError):
        board.delete(running["id"])
    done = board.create("Bitmiş")
    board.stop(done["id"])
    board.delete(done["id"])
    assert board.get(done["id"]) is None


def test_cards_and_next_number_persist(tmp_path):
    path = tmp_path / "pano.json"
    board = Pano(store_path=path, jobs=FakeJobs())
    first = board.create("Kalıcı kart")

    reloaded = Pano(store_path=path, jobs=FakeJobs())
    second = reloaded.create("İkinci kalıcı kart")

    assert reloaded.get(first["id"])["title"] == "Kalıcı kart"
    assert second["id"] == "K-002"


def test_start_rejects_done_card(tmp_path):
    board, jobs = _pano(tmp_path)
    card = board.start(board.create("Biten")["id"])
    jobs.set(card["job_id"], status="done")
    assert board.get(card["id"])["status"] == "bitti"

    with pytest.raises(PanoError):
        board.start(card["id"])


def _wait_for_card(board: Pano, card_id: str, expected: str, *, timeout: float = 10) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = board.get(card_id)
        if last is not None and last["status"] == expected:
            return last
        time.sleep(0.02)
    pytest.fail(f"Kart beklenen duruma gelmedi; beklenen={expected}, son={last}")


def test_real_claude_job_finishes_pano_card_without_phone_update(tmp_path, processes, job_managers):
    manager = _manager(
        tmp_path / "jobs", _stream_script(_success_events()), processes, job_managers
    )
    board = Pano(store_path=tmp_path / "pano.json", jobs=manager)

    started = board.start(board.create("Gerçek süreç")["id"])
    finished = _wait_for_card(board, started["id"], "bitti")
    job = manager.get(started["job_id"])

    assert finished["summary"] == "İş tamamlandı."
    assert job is not None
    assert job["origin"] == "pano"
    assert job["notified"] is True
    assert manager.updates() == []


def test_phone_jobs_appear_in_updates_but_pano_jobs_do_not(tmp_path, processes, job_managers):
    manager = _manager(
        tmp_path / "jobs", _stream_script(_success_events()), processes, job_managers
    )
    board = Pano(store_path=tmp_path / "pano.json", jobs=manager)
    pano_card = board.start(board.create("Pano işi")["id"])
    _wait_for_card(board, pano_card["id"], "bitti")
    phone_job = manager.submit("Telefon işi")
    _wait_for(manager, phone_job.id, "done")

    assert [job["id"] for job in manager.updates()] == [phone_job.id]


def test_pano_api_create_list_start_and_errors(tmp_path, monkeypatch):
    board, jobs = _pano(tmp_path)
    monkeypatch.setattr(pano_api, "pano", board)
    app = FastAPI()
    app.include_router(pano_api.router)

    with TestClient(app) as client:
        created = client.post("/api/pano", json={"title": "API kartı", "detail": "ayrıntı"})
        listed = client.get("/api/pano")
        started = client.post("/api/pano/K-001/start")
        jobs.set(started.json()["data"]["card"]["job_id"], status="done")
        bad_pause = client.post("/api/pano/K-001/pause")
        missing = client.delete("/api/pano/bilinmeyen")

    assert created.status_code == 200
    assert created.json()["success"] is True
    assert [card["id"] for card in listed.json()["data"]["cards"]] == ["K-001"]
    assert started.status_code == 200
    assert started.json()["success"] is True
    assert bad_pause.status_code == 409
    assert bad_pause.json()["success"] is False
    assert missing.status_code == 409
    assert missing.json()["success"] is False


# ── Terra incelemesi (2026-10-26): kalıcılık bulguları ─────────────────────────


@pytest.mark.parametrize("content", ["[]", "{\"cards\": 5}", "{bozuk"])
def test_unreadable_store_opens_empty_and_is_moved_aside(tmp_path, content):
    store = tmp_path / "pano.json"
    store.write_text(content, encoding="utf-8")

    board = Pano(store_path=store, jobs=FakeJobs())

    assert board.snapshot()["cards"] == []
    aside = list(tmp_path.glob("pano.bozuk-*.json"))
    assert len(aside) == 1 and aside[0].read_text(encoding="utf-8") == content
    board.create("Yeni kart")
    assert aside[0].read_text(encoding="utf-8") == content


def test_create_is_rolled_back_when_store_cannot_be_written(tmp_path, monkeypatch):
    board, _ = _pano(tmp_path)
    monkeypatch.setattr(board, "_save", lambda: False)

    with pytest.raises(PanoError):
        board.create("Yazılamayan kart")

    monkeypatch.undo()
    assert board.snapshot()["cards"] == []
    assert board.create("Sonraki")["id"] == "K-001"


def test_user_action_reports_save_failure(tmp_path, monkeypatch):
    board, jobs = _pano(tmp_path)
    card = board.create("Kart")
    monkeypatch.setattr(board, "_save", lambda: False)

    with pytest.raises(PanoError, match="diske yazılamadı"):
        board.start(card["id"])
    # İş yine de verildi; kart bellekte doğru durumda.
    assert jobs.submissions and board.get(card["id"])["status"] == "calisiyor"
