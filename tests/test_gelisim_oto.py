"""Onaysız kendini geliştirme (2026-11-06): gerçek depo + uzak depo ile birleştir, gönder, kilitlenme."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core import claude_jobs, dongu as dongu_mod, pano_git  # noqa: E402
from backend.core.dongu import Dongu  # noqa: E402
from backend.core.pano import Pano, auto_block_reason  # noqa: E402


class Jobs:
    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.submissions: list[dict] = []

    def submit(self, task, resume_of=None, origin="telefon", cwd=None, engine="claude", mode="auto"):
        job_id = f"j{len(self.jobs) + 1}"
        self.submissions.append({"id": job_id, "task": task, "origin": origin, "cwd": cwd, "resume_of": resume_of})
        self.jobs[job_id] = {"id": job_id, "status": "queued", "summary": "", "session_id": None, "approval": "",
                             "error": "", "steps": 0, "last_step": "", "cost_usd": 0.1}
        return SimpleNamespace(id=job_id)

    def get(self, job_id):
        job = self.jobs.get(job_id)
        return dict(job) if job else None

    def cancel(self, job_id):
        return True

    def limits(self):
        return {}

    def finish(self, job_id: str, **values) -> None:
        self.jobs[job_id].update({"status": "done", "summary": "Şunu yaptım."} | values)


class Clock:
    def __init__(self) -> None:
        self.ts = datetime(2026, 11, 6, 10, 0).timestamp()

    def __call__(self) -> float:
        return self.ts


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip()


def _commit(repo: Path, name: str, text: str, message: str = "ekle") -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", message)


TEST_OK = f'"{sys.executable}" -c "print(1)"'
TEST_NEEDS_MAIN = f'"{sys.executable}" -c "import pathlib,sys; sys.exit(0 if not pathlib.Path(\'bozuk.txt\').exists() else 1)"'


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(pano_git, "WORKTREE_ROOT", tmp_path / "wt")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@t"), ("config", "user.name", "t"),
                 ("config", "core.autocrlf", "false"), ("remote", "add", "origin", str(remote))):
        _git(repo, *args)
    _commit(repo, "a.txt", "bir\n", "ilk")
    _git(repo, "push", "-q", "origin", "main")
    jobs = Jobs()
    board = Pano(store_path=tmp_path / "pano.json", jobs=jobs, background=False)
    clock = Clock()
    loop = Dongu(board, tmp_path / "dongu.json", tmp_path / "rapor", clock=clock)
    loop.set_gelisim(True)
    loop.state["gelisim_son"] = clock.ts  # döngü kendi kartını açmasın, kartı test açıyor
    return SimpleNamespace(repo=repo, remote=remote, jobs=jobs, board=board, loop=loop, clock=clock)


def _run_card(s, name="b.txt", text="kart\n", test=TEST_OK) -> tuple[str, Path]:
    """Kartı açar, başlatır; kopyada dosya yazar, işi bitirir. Dönüş: kart + kopya (henüz doğrulanmadı)."""
    card = s.board.create("Gelişim: deneme", "görev", str(s.repo), test)["id"]
    s.loop.tick()
    data = s.board.get(card)
    assert data["status"] == "calisiyor"
    worktree = Path(data["worktree"])
    target = worktree / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    s.jobs.finish(s.jobs.submissions[-1]["id"])
    return card, worktree


def _ticks(s, count=3):
    for _ in range(count):
        s.loop.tick()


def test_passing_card_merges_and_pushes_without_asking(setup):
    s = setup
    card, worktree = _run_card(s)
    _ticks(s)
    data = s.board.get(card)
    assert data["status"] == "bitti" and data["merged"]
    assert (s.repo / "b.txt").exists() and not worktree.exists()
    assert _git(s.repo, "rev-parse", "main") == _git(s.remote, "rev-parse", "main")  # gönderildi
    assert s.loop.state["gelisim_push"] is None
    assert [n["durum"] for n in s.loop.take_news()] == ["bitti"]
    assert s.jobs.submissions[0]["origin"] == claude_jobs.GELISIM_ORIGIN


def test_moved_base_is_taken_into_copy_and_retested(setup):
    s = setup
    card, _ = _run_card(s)
    s.board.get(card)  # doğrulama: kart birlestir
    _commit(s.repo, "c.txt", "ana dal ilerledi\n")
    _ticks(s)
    assert s.board.get(card)["status"] == "bitti"
    assert (s.repo / "b.txt").exists() and (s.repo / "c.txt").exists()
    assert _git(s.repo, "rev-parse", "main") == _git(s.remote, "rev-parse", "main")


def test_test_failure_on_merged_state_blocks_merge(setup):
    """Kart tek başına geçiyor, ana dalla birleşince kalıyor: ana dala girmez."""
    s = setup
    card, _ = _run_card(s, test=TEST_NEEDS_MAIN)
    s.board.get(card)
    head_before = _git(s.repo, "rev-parse", "HEAD")
    _commit(s.repo, "bozuk.txt", "x\n")
    head_before = _git(s.repo, "rev-parse", "HEAD")
    s.loop.state["gelisim_deneme"][card] = dongu_mod.OTO_DENEME  # yeniden deneme hakkı bitmiş
    _ticks(s)
    assert s.board.get(card)["status"] == "iptal"
    assert _git(s.repo, "rev-parse", "HEAD") == head_before and not (s.repo / "b.txt").exists()


def test_dirty_main_unrelated_file_is_kept_and_merge_goes_through(setup):
    s = setup
    card, _ = _run_card(s)
    (s.repo / "a.txt").write_text("yarım iş\n", encoding="utf-8")
    _ticks(s)
    assert s.board.get(card)["status"] == "bitti"
    assert (s.repo / "a.txt").read_text(encoding="utf-8") == "yarım iş\n"


def test_dirty_main_same_file_waits_without_touching_then_merges(setup):
    s = setup
    card, _ = _run_card(s, name="a.txt", text="kartın hali\n")
    (s.repo / "a.txt").write_text("yarım iş\n", encoding="utf-8")
    _ticks(s)
    assert s.board.get(card)["status"] == "birlestir"
    assert (s.repo / "a.txt").read_text(encoding="utf-8") == "yarım iş\n"  # yarım işe dokunulmadı
    assert s.loop.take_news() == []  # Yunus'a soru yok
    _git(s.repo, "checkout", "--", "a.txt")
    _ticks(s)
    assert s.board.get(card)["status"] == "birlestir"  # bekleme süresi dolmadı
    s.clock.ts += dongu_mod.OTO_BEKLE + 1
    _ticks(s)
    assert s.board.get(card)["status"] == "bitti"
    assert (s.repo / "a.txt").read_text(encoding="utf-8") == "kartın hali\n"


def test_sensitive_file_waits_for_yunus(setup):
    s = setup
    card, _ = _run_card(s, name="backend/core/dongu.py", text="# fren kalktı\n")
    head = _git(s.repo, "rev-parse", "HEAD")
    _ticks(s)
    data = s.board.get(card)
    assert data["status"] == "birlestir" and "backend/core/dongu.py" in data["oto_engel"]
    assert _git(s.repo, "rev-parse", "HEAD") == head
    news = s.loop.take_news()
    assert [n["durum"] for n in news] == ["birlestir"] and "dongu.py" in news[0]["metin"]
    _ticks(s)
    assert s.loop.take_news() == []  # bir kez söylenir


def test_real_conflict_goes_back_to_agent(setup):
    s = setup
    card, _ = _run_card(s, name="a.txt", text="kartın hali\n")
    s.board.get(card)
    _commit(s.repo, "a.txt", "ana dalın hali\n")
    _ticks(s, 2)
    data = s.board.get(card)
    assert data["status"] == "calisiyor"  # hataya düştü, aynı işi çözmesi için yeniden başladı
    assert "çakıştı" in s.jobs.submissions[-1]["task"] and "git merge" in s.jobs.submissions[-1]["task"]
    assert (s.repo / "a.txt").read_text(encoding="utf-8") == "ana dalın hali\n"


def test_push_failure_keeps_work_and_retries(setup):
    s = setup
    good = str(s.remote)
    _git(s.repo, "remote", "set-url", "origin", str(s.remote) + "-yok")
    card, _ = _run_card(s)
    _ticks(s)
    assert s.board.get(card)["status"] == "bitti"  # birleşme gönderimi beklemez
    assert s.loop.state["gelisim_push"]["dal"] == "main"
    assert any("Gönderilemedi" in e["metin"] for e in s.loop.public()["olaylar"])
    _git(s.repo, "remote", "set-url", "origin", good)
    _ticks(s)
    assert s.loop.state["gelisim_push"] is not None  # bekleme süresi dolmadı
    s.clock.ts += dongu_mod.OTO_PUSH_BEKLE + 1
    _ticks(s)
    assert s.loop.state["gelisim_push"] is None
    assert _git(s.repo, "rev-parse", "main") == _git(s.remote, "rev-parse", "main")


def test_approval_request_is_rejected_without_asking(setup):
    s = setup
    card = s.board.create("Gelişim: onaylı", "görev", str(s.repo), TEST_OK)["id"]
    s.loop.tick()
    s.jobs.jobs["j1"].update(status="needs_approval", approval="git push", session_id="s1")
    _ticks(s, 1)
    assert s.board.get(card)["status"] == "calisiyor"
    assert "Onaylanmadı" in s.jobs.submissions[-1]["task"]


def test_normal_cards_still_wait_for_yunus(setup):
    """Yalnız kendini geliştirme kartları onaysız: normal proje kartı eski kuralda kalır."""
    s = setup
    card = s.board.create("Normal iş", "görev", str(s.repo), TEST_OK)["id"]
    s.loop.tick()
    data = s.board.get(card)
    (Path(data["worktree"]) / "n.txt").write_text("x\n", encoding="utf-8")
    s.jobs.finish("j1")
    _ticks(s)
    assert s.board.get(card)["status"] == "birlestir" and not (s.repo / "n.txt").exists()
    assert s.jobs.submissions[0]["origin"] == "pano"


def test_closed_gelisim_does_not_merge(setup):
    s = setup
    card, _ = _run_card(s)
    s.loop.set_gelisim(False)
    _ticks(s)
    assert s.board.get(card)["status"] == "birlestir"


def test_block_reasons():
    ok = {"ok": True}
    assert auto_block_reason(ok, [], [("M", "actions/x.py"), ("A", "tests/test_x.py")]) == ""
    assert "test" in auto_block_reason({}, [], []).lower()
    assert "Bekçi" in auto_block_reason(ok, [{"seviye": "yuksek", "ad": "Gizli"}], [])
    assert auto_block_reason(ok, [{"seviye": "orta", "ad": "x"}], []) == ""
    assert "silmiş" in auto_block_reason(ok, [], [("D", "tests/test_x.py")])
    for path in ("backend/core/dongu.py", "backend/core/bekci.py", "config/api_keys.json", ".claude/settings.json",
                 ".gitignore", ".github/workflows/x.yml", "requirements.txt", "frontend/package.json"):
        assert auto_block_reason(ok, [], [("M", path)]), path


def test_lean_job_keeps_guard_and_note():
    assert "--settings" not in claude_jobs.GELISIM_ARGS  # bekçi ortak listede, buradan ezilmez
    assert "--strict-mcp-config" in claude_jobs.GELISIM_ARGS and "--max-budget-usd" in claude_jobs.GELISIM_ARGS
    assert "onay isteme" in claude_jobs.note_for(claude_jobs.GELISIM_ORIGIN)
    assert claude_jobs.note_for("pano") == claude_jobs.PANO_NOTE


def test_task_is_short_and_lists_open_wishes(tmp_path):
    notes = tmp_path / "Notes"
    notes.mkdir()
    (notes / "Istek-Listesi.md").write_text(
        "# Liste\n\n### İ-001 · Bitti\n**Durum:** yapıldı\n- 2026 · \"eski\" · x\n\n"
        "### İ-002 · Açık\n**Durum:** yeni · **Sayı:** 1\n- 2026 · \"bunu yap\" · x\n",
        encoding="utf-8",
    )
    (notes / "Gelisim-Gunlugu.md").write_text("# G\n\n## 2026-11-04 — Parlaklık\n- x\n", encoding="utf-8")
    wishes = dongu_mod.acik_istekler(tmp_path)
    assert "İ-002" in wishes and "bunu yap" in wishes and "İ-001" not in wishes
    assert "Parlaklık" in dongu_mod.gunluk_basliklari(tmp_path)
    assert dongu_mod.acik_istekler(tmp_path / "yok") == "- (okunamadı)"
    text = dongu_mod.GELISIM_TASK.format(test="t", istekler="i" * 500, gunluk="g" * 750, recent="r" * 350)
    assert len(text) < 3500  # MAX_DETAIL'e sığmalı, yoksa sonu kesilir
    assert "Bilinen-Tuzaklar" in text and "baştan sona okuma" in text
