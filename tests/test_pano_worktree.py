from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.api import pano as pano_api
from backend.core import pano_git
from backend.core.pano import Pano, PanoError
from backend.core.pano_git import GitError


class FakeJobs:
    """Pano durumlarını süreç başlatmadan elle değiştirebilen küçük iş kuyruğu."""

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
        self.submissions.append(
            {"id": job_id, "task": task, "resume_of": resume_of, "origin": origin, "cwd": cwd}
        )
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
        self.cancelled.append(job_id)
        return job_id in self.jobs

    def set(self, job_id: str, **values: object) -> None:
        self.jobs[job_id].update(values)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", check=True
    )
    return result.stdout.strip()


def _repo(tmp_path: Path, name: str = "repo") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "dosya.txt").write_text("ilk satır\n", encoding="utf-8")
    _git(repo, "add", "dosya.txt")
    _git(repo, "commit", "-m", "ilk")
    return repo


def _pano(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Pano, FakeJobs]:
    monkeypatch.setattr(pano_git, "WORKTREE_ROOT", tmp_path / "wt")
    jobs = FakeJobs()
    return Pano(store_path=tmp_path / "pano.json", jobs=jobs, background=False), jobs


def _passing_test() -> str:
    return f'"{sys.executable}" -c "print(\'ok\')"'


def _failing_test() -> str:
    return f'"{sys.executable}" -c "import sys; print(\'kirmizi\'); sys.exit(1)"'


def _finish(board: Pano, jobs: FakeJobs, card: dict, *, change: str | None = "kart satırı\n") -> dict:
    worktree = Path(card["worktree"])
    if change is not None:
        (worktree / "dosya.txt").write_text(change, encoding="utf-8")
    jobs.set(card["job_id"], status="done", session_id="s1")
    board.snapshot()
    result = board.get(card["id"])
    assert result is not None
    return result


def test_create_resolves_repo_root_and_rejects_invalid_paths(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    board, _ = _pano(tmp_path, monkeypatch)
    nested = repo / "alt" / "klasor"
    nested.mkdir(parents=True)

    card = board.create("Proje", repo=str(nested))

    assert card["repo"] == str(repo.resolve())
    not_repo = tmp_path / "git-degil"
    not_repo.mkdir()
    with pytest.raises(PanoError):
        board.create("Git değil", repo=str(not_repo))
    with pytest.raises(PanoError):
        board.create("Yok", repo=str(tmp_path / "yok"))


def test_start_creates_worktree_and_gives_claude_its_path(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    board, jobs = _pano(tmp_path, monkeypatch)
    card = board.create("Değiştir", repo=str(repo), test_cmd=_passing_test())

    started = board.start(card["id"])

    worktree = tmp_path / "wt" / "repo-K-001"
    assert Path(started["worktree"]) == worktree
    assert worktree.is_dir()
    assert started["branch"] == "pano/K-001"
    assert started["base_branch"] == "main"
    assert started["base_sha"] == head
    assert jobs.submissions[-1]["cwd"] == str(worktree)
    assert "worktree" in jobs.submissions[-1]["task"]
    assert _passing_test() in jobs.submissions[-1]["task"]


def test_changed_worktree_is_committed_tested_and_waits_for_merge(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    board, jobs = _pano(tmp_path, monkeypatch)
    card = board.start(board.create("Değiştir", repo=str(repo), test_cmd=_passing_test())["id"])

    verified = _finish(board, jobs, card)

    worktree = Path(card["worktree"])
    assert verified["status"] == "birlestir"
    assert verified["test"]["ok"] is True
    assert "1 file changed" in verified["diff"]
    assert _git(worktree, "log", "-1", "--format=%s").startswith("Pano K-001:")
    assert (repo / "dosya.txt").read_text(encoding="utf-8") == "ilk satır\n"


def test_approved_merge_updates_main_and_cleans_worktree_and_branch(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    board, jobs = _pano(tmp_path, monkeypatch)
    card = board.start(board.create("Değiştir", repo=str(repo), test_cmd=_passing_test())["id"])
    verified = _finish(board, jobs, card)
    worktree = Path(verified["worktree"])

    merged = board.merge(card["id"], approved=True)

    assert merged["status"] == "bitti"
    assert merged["merged"]
    assert (repo / "dosya.txt").read_text(encoding="utf-8") == "kart satırı\n"
    assert len(_git(repo, "rev-list", "--parents", "-n", "1", "HEAD").split()) == 3
    assert not worktree.exists()
    assert _git(repo, "branch", "--list", "pano/K-001") == ""


def test_failed_test_keeps_worktree_and_retry_resumes_session(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    board, jobs = _pano(tmp_path, monkeypatch)
    card = board.start(board.create("Kırık", repo=str(repo), test_cmd=_failing_test())["id"])
    worktree = card["worktree"]

    failed = _finish(board, jobs, card)
    retried = board.start(card["id"])

    assert failed["status"] == "hata"
    assert "Test kaldı" in failed["error"]
    assert "kirmizi" in failed["error"]
    assert Path(retried["worktree"]) == Path(worktree)
    assert jobs.submissions[-1]["resume_of"] == "job-1"
    assert jobs.submissions[-1]["task"].startswith("Önceki deneme")


def test_no_changes_finishes_without_merge_and_removes_worktree_and_branch(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    board, jobs = _pano(tmp_path, monkeypatch)
    card = board.start(board.create("Bak", repo=str(repo), test_cmd=_passing_test())["id"])
    worktree = Path(card["worktree"])

    finished = _finish(board, jobs, card, change=None)

    assert finished["status"] == "bitti"
    assert finished["merged"] is None
    assert not worktree.exists()
    assert _git(repo, "branch", "--list", "pano/K-001") == ""


def test_rejected_merge_removes_worktree_but_preserves_branch(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    board, jobs = _pano(tmp_path, monkeypatch)
    card = board.start(board.create("Reddet", repo=str(repo), test_cmd=_passing_test())["id"])
    verified = _finish(board, jobs, card)

    rejected = board.merge(card["id"], approved=False)

    assert rejected["status"] == "iptal"
    assert not Path(verified["worktree"]).exists()
    assert _git(repo, "branch", "--list", "pano/K-001") == "pano/K-001"


def test_merge_rejects_tracked_dirty_main_but_allows_untracked_file(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    board, jobs = _pano(tmp_path, monkeypatch)
    card = board.start(board.create("Kirli", repo=str(repo), test_cmd=_passing_test())["id"])
    verified = _finish(board, jobs, card)
    (repo / "dosya.txt").write_text("ana kirli\n", encoding="utf-8")

    with pytest.raises(PanoError, match="commit'lenmemiş"):
        board.merge(card["id"], approved=True)
    assert board.get(card["id"])["status"] == "birlestir"
    assert (repo / "dosya.txt").read_text(encoding="utf-8") == "ana kirli\n"

    _git(repo, "checkout", "--", "dosya.txt")
    (repo / "yalniz-izlenmeyen.txt").write_text("serbest\n", encoding="utf-8")
    merged = board.merge(card["id"], approved=True)
    assert merged["status"] == "bitti"


def test_merge_conflict_returns_card_to_error_and_aborts_main_merge(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    board, jobs = _pano(tmp_path, monkeypatch)
    card = board.start(board.create("Çakış", repo=str(repo), test_cmd=_passing_test())["id"])
    verified = _finish(board, jobs, card, change="worktree satırı\n")
    (repo / "dosya.txt").write_text("ana satırı\n", encoding="utf-8")
    _git(repo, "add", "dosya.txt")
    _git(repo, "commit", "-m", "ana değişiklik")

    result = board.merge(card["id"], approved=True)

    assert result["status"] == "hata"
    assert result["error"].startswith("Birleştirmede çakışma")
    assert "git merge main" in result["error"]
    assert _git(repo, "status", "--porcelain") == ""
    assert not (repo / ".git" / "MERGE_HEAD").exists()
    assert Path(verified["worktree"]).exists()


def test_merge_rejects_when_main_checkout_is_on_another_branch(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    board, jobs = _pano(tmp_path, monkeypatch)
    card = board.start(board.create("Dal", repo=str(repo), test_cmd=_passing_test())["id"])
    _finish(board, jobs, card)
    _git(repo, "checkout", "-b", "diger")

    with pytest.raises(PanoError, match="başka dalda"):
        board.merge(card["id"], approved=True)
    assert board.get(card["id"])["status"] == "birlestir"


def test_delete_finished_or_cancelled_card_drops_worktree_but_keeps_branch(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    board, jobs = _pano(tmp_path, monkeypatch)
    card = board.start(board.create("Sil", repo=str(repo), test_cmd=_passing_test())["id"])
    failed = _finish(board, jobs, card, change="kart\n")
    assert failed["status"] == "birlestir"
    board.merge(card["id"], approved=False)
    board.delete(card["id"])

    finished = board.start(board.create("Boş", repo=str(repo))["id"])
    assert _finish(board, jobs, finished, change=None)["status"] == "bitti"
    board.delete(finished["id"])

    assert board.get(card["id"]) is None
    assert board.get(finished["id"]) is None
    assert _git(repo, "branch", "--list", "pano/K-001") == "pano/K-001"


def test_delete_rejects_card_while_verifying(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    board, jobs = _pano(tmp_path, monkeypatch)
    card = board.start(board.create("Doğrula", repo=str(repo), test_cmd=_passing_test())["id"])
    jobs.set(card["job_id"], status="done", session_id="s1")
    monkeypatch.setattr(board, "_kick_verifications", lambda: None)

    assert board.snapshot()["cards"][0]["status"] == "dogrulaniyor"
    with pytest.raises(PanoError):
        board.delete(card["id"])


def test_changed_project_without_test_command_goes_straight_to_merge(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    board, jobs = _pano(tmp_path, monkeypatch)
    card = board.start(board.create("Testsiz", repo=str(repo))["id"])

    verified = _finish(board, jobs, card)

    assert verified["status"] == "birlestir"
    assert verified["test"] is None


def test_run_test_timeout_returns_with_timeout_tail(tmp_path):
    repo = _repo(tmp_path)
    command = f'"{sys.executable}" -c "import time; time.sleep(5)"'
    started = time.monotonic()

    result = pano_git.run_test(repo, command, timeout=1)

    assert time.monotonic() - started < 2
    assert result.ok is False
    assert result.code is None
    assert "sınırı doldu" in result.tail


def test_safe_card_id_accepts_only_safe_branch_component(tmp_path):
    _repo(tmp_path)
    assert pano_git.safe_card_id("K-001") == "K-001"
    for unsafe in ("../x", "K-1;rm"):
        with pytest.raises(GitError):
            pano_git.safe_card_id(unsafe)


def test_api_merge_wrong_state_is_409_and_repos_lists_project(tmp_path, monkeypatch):
    project = _repo(tmp_path, "gorunen-proje")
    board, _ = _pano(tmp_path, monkeypatch)
    monkeypatch.setattr(pano_api, "pano", board)
    monkeypatch.setattr(pano_git, "PROJECTS_DIR", tmp_path)
    app = FastAPI()
    app.include_router(pano_api.router)

    with TestClient(app) as client:
        board.create("Bekleyen", repo=str(project))
        wrong_state = client.post("/api/pano/K-001/merge", json={"approved": True})
        repos = client.get("/api/pano/repos")

    assert wrong_state.status_code == 409
    assert repos.status_code == 200
    assert repos.json()["data"]["repos"] == [
        {"name": "gorunen-proje", "path": str(project), "test_cmd": ""}
    ]


# ── Canlı deneme (2026-10-26): testin bıraktığı izlenmeyen dosyalar ──────────────


def _artifact_test() -> str:
    # pytest'in __pycache__'i gibi: test koşarken izlenmeyen dosya ve klasör bırakır.
    script = "import os; os.makedirs('artik', exist_ok=True); open('artik/x.pyc','w').write('x'); print('ok')"
    return f'"{sys.executable}" -c "{script}"'


def test_test_artifacts_do_not_block_cleanup_or_leak_into_next_commit(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    board, jobs = _pano(tmp_path, monkeypatch)
    card = board.start(board.create("Artık bırakan test", repo=str(repo), test_cmd=_artifact_test())["id"])
    worktree = Path(card["worktree"])

    card = _finish(board, jobs, card)

    assert card["status"] == "birlestir"
    assert not (worktree / "artik").exists()
    assert "artik" not in _git(worktree, "show", "--name-only", "--format=", "HEAD")

    card = board.merge(card["id"], True)

    assert card["status"] == "bitti" and card["worktree"] is None
    assert not worktree.exists()
    assert _git(repo, "branch", "--list", "pano/*") == ""


# ── Terra incelemesi (2026-10-26, adım 3) ──────────────────────────────────────


def _api(board: Pano, monkeypatch: pytest.MonkeyPatch, *, remote: bool) -> TestClient:
    monkeypatch.setattr(pano_api, "pano", board)
    monkeypatch.setattr(pano_api.remote_auth, "is_remote_scope", lambda scope: remote)
    app = FastAPI()
    app.include_router(pano_api.router)
    return TestClient(app)


def test_remote_request_cannot_set_custom_test_command(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    board, _ = _pano(tmp_path, monkeypatch)
    body = {"title": "Kart", "repo": str(repo), "test_cmd": "echo sahiden-komut"}

    with _api(board, monkeypatch, remote=True) as client:
        refused = client.post("/api/pano", json=body)
        plain = client.post("/api/pano", json={**body, "test_cmd": ""})

    assert refused.status_code == 403 and refused.json()["success"] is False
    assert plain.status_code == 200
    assert [c["test_cmd"] for c in board.snapshot()["cards"]] == [""]

    with _api(board, monkeypatch, remote=False) as client:
        local = client.post("/api/pano", json=body)
    assert local.status_code == 200 and local.json()["data"]["card"]["test_cmd"] == "echo sahiden-komut"


def test_card_cannot_be_stopped_while_its_test_runs(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    board, jobs = _pano(tmp_path, monkeypatch)
    card = board.start(board.create("Kart", repo=str(repo))["id"])
    # Claude bitti, doğrulama arkada koşuyor (thread'i taklit: yeniden başlatılmasın).
    board._verifying.add(card["id"])
    jobs.set(card["job_id"], status="done", session_id="s1")

    with pytest.raises(PanoError, match="Test sürüyor"):
        board.stop(card["id"])
    with pytest.raises(PanoError):
        board.delete(card["id"])


def test_deleting_card_keeps_unfinished_work_on_branch(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    board, jobs = _pano(tmp_path, monkeypatch)
    card = board.start(board.create("Yarım iş", repo=str(repo))["id"])
    worktree = Path(card["worktree"])
    (worktree / "yarim.txt").write_text("Claude buraya kadar yazdı\n", encoding="utf-8")
    jobs.set(card["job_id"], status="cancelled")
    board.stop(card["id"])

    board.delete(card["id"])

    assert not worktree.exists()
    assert _git(repo, "show", "pano/K-001:yarim.txt") == "Claude buraya kadar yazdı"


def test_test_side_effects_on_tracked_files_never_reach_a_commit(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    board, jobs = _pano(tmp_path, monkeypatch)
    # Test izlenen dosyayı bozuyor ve kalıyor.
    script = "open('dosya.txt','a').write('TESTIN IZI\n'); import sys; sys.exit(1)"
    card = board.start(board.create("Kart", repo=str(repo), test_cmd=f'"{sys.executable}" -c "{script}"')["id"])
    worktree = Path(card["worktree"])

    card = _finish(board, jobs, card, change="claude satırı\n")
    assert card["status"] == "hata"
    assert (worktree / "dosya.txt").read_text(encoding="utf-8") == "claude satırı\n"

    # Yeniden dene: Claude başka bir dosyaya dokunur; testin izi hiçbir commit'e girmemeli.
    card = board.start(card["id"])
    (worktree / "ikinci.txt").write_text("düzeltme\n", encoding="utf-8")
    _finish(board, jobs, card, change=None)
    log = _git(worktree, "log", "-p", "main..HEAD")
    assert "TESTIN IZI" not in log
