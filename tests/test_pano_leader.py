from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.api import pano as pano_api
from backend.core import claude_jobs
from backend.core.pano import Pano, PanoError, parse_plan


class FakeJobs:
    """Pano durumlarını süreç başlatmadan elle değiştiren küçük iş kuyruğu."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.submissions: list[dict] = []
        self.engines: list[tuple[str, str]] = []
        self.cancelled: list[str] = []
        self._next = 1

    def submit(
        self,
        task: str,
        resume_of: str | None = None,
        origin: str = "telefon",
        cwd: str | None = None,
        engine: str = "claude",
        mode: str = "auto",
    ) -> SimpleNamespace:
        self.engines.append((engine, mode))
        job_id = f"job-{self._next}"
        self._next += 1
        self.submissions.append({
            "id": job_id,
            "task": task,
            "resume_of": resume_of,
            "origin": origin,
            "cwd": cwd,
        })
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


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    return repo


def _plan_text() -> str:
    return """```json
{"ozet": "Üç aşamalı plan", "gorevler": [
 {"baslik": "İncele", "ayrinti": "Kaynakları incele.", "ajan": "claude", "sonra": []},
 {"baslik": "Uygula", "ayrinti": "Değişikliği uygula.", "ajan": "codex", "sonra": [1]},
 {"baslik": "Araştır", "ayrinti": "Sonucu araştır.", "ajan": "gemini", "sonra": [1, 2]}
]}
```"""


def _by_id(snapshot: dict, card_id: str) -> dict:
    return next(card for card in snapshot["cards"] if card["id"] == card_id)


def _split(board: Pano, jobs: FakeJobs, *, repo: Path | None = None) -> tuple[dict, list[dict]]:
    top = board.create("Liderlik görevi", "Ayrıntılı görev", str(repo) if repo else None, "pytest -q")
    planning = board.plan(top["id"])
    jobs.set(planning["job_id"], status="done", summary=_plan_text())
    snapshot = board.snapshot()
    top = _by_id(snapshot, top["id"])
    return top, [_by_id(snapshot, child_id) for child_id in top["children"]]


def test_plan_submits_jarvis_and_applies_children_with_dependencies(tmp_path):
    board, jobs = _pano(tmp_path)
    repo = _init_repo(tmp_path)
    top = board.create("Liderlik görevi", "Ayrıntılı görev", str(repo), "pytest -q")

    planning = board.plan(top["id"])

    assert planning["status"] == "planlaniyor"
    assert jobs.engines == [("claude", "plan")]
    assert jobs.submissions[0]["origin"] == "pano"
    assert jobs.submissions[0]["cwd"] == str(repo)
    assert "Chiron" in jobs.submissions[0]["task"]
    assert top["title"] in jobs.submissions[0]["task"]

    jobs.set(planning["job_id"], status="done", summary=_plan_text())
    snapshot = board.snapshot()
    split = _by_id(snapshot, top["id"])
    children = [_by_id(snapshot, card_id) for card_id in split["children"]]

    assert split["status"] == "bolundu"
    assert split["children"] == ["K-002", "K-003", "K-004"]
    assert split["plan_summary"] == "Üç aşamalı plan"
    assert [child["status"] for child in children] == ["bekliyor"] * 3
    assert [child["parent"] for child in children] == [top["id"]] * 3
    assert [child["agent"] for child in children] == ["claude", "codex", "gemini"]
    assert [child["after"] for child in children] == [[], ["K-002"], ["K-002", "K-003"]]
    assert top["id"] in children[0]["detail"]
    assert split["plan_summary"] in children[0]["detail"]
    assert all(child["repo"] == str(repo) and child["test_cmd"] == "pytest -q" for child in children)


def test_child_dependencies_and_agent_submission(tmp_path):
    board, jobs = _pano(tmp_path)
    _, children = _split(board, jobs)
    first, second, _ = children

    with pytest.raises(PanoError, match="Önce K-002 bitmeli"):
        board.start(second["id"])

    started_first = board.start(first["id"])
    jobs.set(started_first["job_id"], status="done", summary="Tamam")
    assert board.get(first["id"])["status"] == "bitti"

    started_second = board.start(second["id"])
    assert started_second["status"] == "calisiyor"
    assert jobs.engines[-1] == ("codex", "auto")


@pytest.mark.parametrize(
    ("final_statuses", "expected"),
    [(["bitti", "iptal", "iptal"], "bitti"), (["iptal", "iptal", "iptal"], "iptal")],
)
def test_split_parent_rolls_up_when_all_children_close(tmp_path, final_statuses, expected):
    board, jobs = _pano(tmp_path)
    top, children = _split(board, jobs)

    for child, status in zip(children, final_statuses):
        if status == "iptal":
            assert board.stop(child["id"])["status"] == "iptal"
        else:
            running = board.start(child["id"])
            jobs.set(running["job_id"], status="done", summary="Tamam")
            board.get(child["id"])

    assert _by_id(board.snapshot(), top["id"])["status"] == expected


def test_split_parent_stays_open_while_a_child_is_open(tmp_path):
    board, jobs = _pano(tmp_path)
    top, children = _split(board, jobs)

    board.stop(children[0]["id"])
    board.stop(children[1]["id"])

    assert _by_id(board.snapshot(), top["id"])["status"] == "bolundu"


@pytest.mark.parametrize(
    "summary",
    [
        "plan yok",
        "```json\n{\"ozet\": \"boş\", \"gorevler\": []}\n```",
        "```json\n{" + '"gorevler": [' + ",".join('{"baslik":"x"}' for _ in range(9)) + "]}\n```",
        "```json\n{\"gorevler\": [{\"baslik\": \"ilk\", \"sonra\": [2]}]}\n```",
        "```json\n{\"gorevler\": [{\"ayrinti\": \"başlık yok\"}]}\n```",
    ],
)
def test_invalid_plan_marks_top_failed_without_children_and_retries(tmp_path, summary):
    board, jobs = _pano(tmp_path)
    top = board.create("Bozuk plan")
    planning = board.plan(top["id"])
    jobs.set(planning["job_id"], status="done", summary=summary)

    failed = board.get(top["id"])

    assert failed["status"] == "hata"
    assert failed["error"].startswith("Chiron'un planı okunamadı")
    assert failed["children"] == []
    retried = board.start(top["id"])
    assert retried["status"] == "planlaniyor"
    assert jobs.engines[-1] == ("claude", "plan")


def test_parse_plan_normalizes_agents_and_finds_the_right_json():
    unknown = parse_plan('{"gorevler": [{"baslik": "a", "ajan": "bilinmiyor"}]}')
    capitalized = parse_plan('{"gorevler": [{"baslik": "a", "ajan": "Codex"}]}')
    prose = parse_plan('Önce not. {"gorevler": [{"baslik": "a"}]} Sonra not.')
    last_block = parse_plan(
        '```json\n{"gorevler": [{"baslik": "ilk"}]}\n```\n'
        '```json\n{"gorevler": [{"baslik": "son"}]}\n```'
    )

    assert unknown["gorevler"][0]["ajan"] == "claude"
    assert capitalized["gorevler"][0]["ajan"] == "codex"
    assert prose["gorevler"][0]["baslik"] == "a"
    assert last_block["gorevler"][0]["baslik"] == "son"


def test_leader_card_rules_and_deletion_after_children_close(tmp_path):
    board, jobs = _pano(tmp_path)
    top, children = _split(board, jobs)

    with pytest.raises(PanoError):
        board.plan(children[0]["id"])
    active = board.start(board.create("Çalışan") ["id"])
    with pytest.raises(PanoError):
        board.plan(active["id"])
    planning = board.plan(board.create("Planlanacak")["id"])
    with pytest.raises(PanoError):
        board.pause(planning["id"])
    stopping = board.stop(planning["id"])
    assert jobs.cancelled[-1] == planning["job_id"]
    jobs.set(stopping["job_id"], status="cancelled")
    assert board.get(planning["id"])["status"] == "iptal"
    with pytest.raises(PanoError):
        board.stop(top["id"])
    with pytest.raises(PanoError):
        board.delete(top["id"])

    for child in children:
        board.stop(child["id"])
    board.snapshot()
    board.delete(top["id"])
    assert board.get(top["id"]) is None


def test_gemini_project_card_does_not_open_worktree_and_unknown_agent_is_rejected(tmp_path):
    board, jobs = _pano(tmp_path)
    repo = _init_repo(tmp_path)
    card = board.create("Araştır", repo=str(repo), agent="gemini")

    started = board.start(card["id"])

    assert started["worktree"] is None
    assert jobs.submissions[-1]["cwd"] == str(repo)
    assert jobs.engines[-1] == ("gemini", "auto")
    with pytest.raises(PanoError):
        board.create("Bilinmeyen", agent="x")


TERMINAL_STATUSES = {"done", "failed", "needs_approval", "timeout", "cancelled", "interrupted"}


def _stream_script(events: list[dict] | None = None, *, lines: list[str] | None = None) -> str:
    output = [json.dumps(event) for event in events or []] + list(lines or [])
    return "\n".join(["import sys", *(f"print({line!r}, flush=True)" for line in output)])


def _launcher(
    script: str, processes: list[subprocess.Popen], engines: list[str]
) -> Callable:
    def launch(job: claude_jobs.Job, log_path: Path) -> subprocess.Popen:
        engines.append(job.engine)
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
    engines: list[str],
) -> claude_jobs.ClaudeJobs:
    manager = claude_jobs.ClaudeJobs(
        jobs_dir=jobs_dir, launcher=_launcher(script, processes, engines), time_limit=10
    )
    job_managers.append(manager)
    return manager


def _wait_for(manager: claude_jobs.ClaudeJobs, job_id: str, expected: str | None = None) -> dict:
    wanted = TERMINAL_STATUSES if expected is None else {expected}
    deadline = time.monotonic() + 10
    last = None
    while time.monotonic() < deadline:
        last = manager.get(job_id)
        if last is not None and last["status"] in wanted:
            return last
        time.sleep(0.02)
    pytest.fail(f"İş beklenen duruma gelmedi; beklenen={wanted}, son={last}")


def test_codex_events_finish_job_and_record_session_and_step(tmp_path, processes, job_managers):
    engines: list[str] = []
    events = [
        {"type": "thread.started", "thread_id": "t1"},
        {"type": "item.completed", "item": {"type": "command_execution", "command": "pytest"}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "Bitti."}},
        {"type": "turn.completed", "usage": {}},
    ]
    manager = _manager(tmp_path / "jobs", _stream_script(events), processes, job_managers, engines)

    result = _wait_for(manager, manager.submit("test", engine="codex").id, "done")

    assert engines == ["codex"]
    assert result["summary"] == "Bitti."
    assert result["session_id"] == "t1"
    assert result["steps"] >= 1
    # Son adım Codex'in son mesajı (kartta "en son ne oldu" görünür); komut adımı sayıldı.
    assert result["last_step"] == "Bitti."


def test_codex_failed_turn_fails_job(tmp_path, processes, job_managers):
    engines: list[str] = []
    manager = _manager(
        tmp_path / "jobs",
        _stream_script([{"type": "turn.failed", "error": {"message": "kota doldu"}}]),
        processes,
        job_managers,
        engines,
    )

    assert _wait_for(manager, manager.submit("test", engine="codex").id, "failed")["status"] == "failed"


@pytest.mark.parametrize("exit_code", [0, 1])
def test_gemini_plain_text_filters_noise_and_nonzero_exit_fails(tmp_path, processes, job_managers, exit_code):
    engines: list[str] = []
    script = _stream_script(lines=[
        "Warning: True color (24-bit) support not detected.",
        "Ripgrep is not available. Falling back to GrepTool.",
        "Cevap: 5",
    ]) + f"\nsys.exit({exit_code})"
    manager = _manager(tmp_path / "jobs", script, processes, job_managers, engines)

    result = _wait_for(manager, manager.submit("araştır", engine="gemini").id)

    assert engines == ["gemini"]
    if exit_code == 0:
        assert result["status"] == "done"
        assert result["summary"] == "Cevap: 5"
    else:
        assert result["status"] == "failed"


def test_submit_rejects_codex_resume_unknown_engine_and_unknown_mode(tmp_path, processes, job_managers):
    engines: list[str] = []
    manager = _manager(tmp_path / "jobs", _stream_script(), processes, job_managers, engines)
    existing = manager.submit("ilk")

    with pytest.raises(ValueError):
        manager.submit("devam", engine="codex", resume_of=existing.id)
    with pytest.raises(ValueError):
        manager.submit("bilinmeyen", engine="x")
    with pytest.raises(ValueError):
        manager.submit("bilinmeyen", mode="x")


def test_pano_api_accepts_agent_rejects_unknown_and_starts_plan(tmp_path, monkeypatch):
    board, _ = _pano(tmp_path)
    monkeypatch.setattr(pano_api, "pano", board)
    app = FastAPI()
    app.include_router(pano_api.router)

    with TestClient(app) as client:
        created = client.post("/api/pano", json={"title": "t", "agent": "codex"})
        bad = client.post("/api/pano", json={"title": "t", "agent": "x"})
        planned = client.post("/api/pano/K-001/plan")

    assert created.status_code == 200
    assert created.json()["data"]["card"]["agent"] == "codex"
    assert bad.status_code == 409
    assert planned.status_code == 200
    assert planned.json()["data"]["card"]["status"] == "planlaniyor"


# ── Terra'nın kotası (canlı, 2026-10-26: "usage limit ... try again at Nov 24th") ─────

LIMIT = (
    "ERROR: You've hit your usage limit. Upgrade to Plus to continue using Codex "
    "(https://chatgpt.com/explore/plus), or try again at Nov 24th, 2026 10:02 PM."
)


def _codex_fails_with_limit(board: Pano, jobs: FakeJobs) -> dict:
    card = board.start(board.create("Mekanik iş", agent="codex")["id"])
    jobs.set(card["job_id"], status="failed", error=LIMIT)
    return _by_id(board.snapshot(), card["id"])


def test_codex_limit_blocks_terra_until_reported_time_and_persists(tmp_path):
    board, jobs = _pano(tmp_path)

    card = _codex_fails_with_limit(board, jobs)

    assert card["status"] == "hata" and "24.11.2026 22:02" in card["error"]
    agents = board.snapshot()["agents"]["codex"]
    assert agents["available"] is False
    with pytest.raises(PanoError, match="kotası"):
        board.start(card["id"])
    # Yeniden açılan pano da hatırlar.
    reloaded = Pano(store_path=tmp_path / "pano.json", jobs=jobs)
    assert reloaded.snapshot()["agents"]["codex"]["available"] is False


def test_switching_blocked_card_to_claude_restarts_fresh(tmp_path):
    board, jobs = _pano(tmp_path)
    card = _codex_fails_with_limit(board, jobs)

    board.edit(card["id"], agent="claude")
    restarted = board.start(card["id"])

    assert restarted["status"] == "calisiyor"
    assert jobs.engines[-1] == ("claude", "auto")
    assert jobs.submissions[-1]["resume_of"] is None
    with pytest.raises(PanoError):
        board.edit(card["id"], agent="codex")  # çalışırken ajan değişmez
    with pytest.raises(PanoError):
        board.edit(card["id"], agent="x")


def test_jarvis_is_told_and_codex_tasks_fall_back_to_claude_while_blocked(tmp_path):
    board, jobs = _pano(tmp_path)
    _codex_fails_with_limit(board, jobs)

    top, children = _split(board, jobs)

    assert "codex ŞU AN KULLANILAMAZ" in jobs.submissions[-1]["task"]
    assert [c["agent"] for c in children] == ["claude", "claude", "gemini"]


def test_other_codex_errors_do_not_block(tmp_path):
    board, jobs = _pano(tmp_path)
    card = board.start(board.create("Mekanik iş", agent="codex")["id"])
    jobs.set(card["job_id"], status="failed", error="bağlantı koptu")

    assert board.snapshot()["agents"]["codex"]["available"] is True
