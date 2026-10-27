"""Pano kartının çalışma kopyası: git worktree, commit, test, birleştirme (Ajan İstasyonu adım 3, 2026-10-26).

Kullanıcı kararı (2026-10-25): her iş ayrı kopyada yapılır, test geçmezse "bitti" sayılmaz,
ana dala birleştirmeyi Yunus onaylar. Otomatik birleştirme YOK.

Akış (bir kart için):
    create_worktree  → <WORKTREE_ROOT>/<repo>-<kart>, dal `pano/<kart>`, ana dalın o anki ucundan
    (Claude worktree'de çalışır; commit atmaz)
    commit_all       → Claude'un bıraktığı her değişiklik tek commit (Chiron atar, Claude değil)
    run_test         → kartın test komutu worktree'de, Chiron koşar — Claude'un "test geçti" demesine güvenilmez
    merge            → Yunus onaylayınca ana klasörde `git merge --no-ff`; çakışmada geri alınır
    remove_worktree  → birleştikten / kart silinince

Neden worktree OneDrive dışında: senkron istemcisi git'in kilit dosyalarını tutup
`index.lock` hatası verdiriyor (CLAUDE.md § Sıralama ve çakışma).

Komutlar argüman listesiyle çalışır (kabuk yok); yalnızca TEST komutu kabukta çalışır,
çünkü onu kullanıcı yazıyor (`venv\\Scripts\\python -m pytest ...`). Test komutunu yazabilen
biri zaten Claude'a auto izinle iş verebiliyor; ek bir yetki açılmıyor.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

PROJECTS_DIR = Path.home() / "Projects"
WORKTREE_ROOT = PROJECTS_DIR / ".pano-worktrees"
# %TEMP%\pytest-of-yunus'un izinleri bozuk (2026-10-26) — önerilen test komutu kendi geçici klasörünü kullanır.
PYTEST_TMP = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "chiron" / "pano-pytest"

GIT_TIMEOUT = 120
TEST_TIMEOUT = 15 * 60
TAIL_CHARS = 1500
DIFF_SCAN_CHARS = 2_000_000
BRANCH_PREFIX = "pano/"

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class GitError(RuntimeError):
    """Kullanıcıya gösterilecek git/test hatası."""


@dataclass
class TestResult:
    ok: bool
    code: int | None
    tail: str
    cmd: str


def _tail(text: str, limit: int = TAIL_CHARS) -> str:
    text = text.strip()
    return text if len(text) <= limit else "…" + text[-limit:]


def git(args: list[str], cwd: Path, timeout: float = GIT_TIMEOUT) -> str:
    exe = shutil.which("git")
    if not exe:
        raise GitError("git bulunamadı.")
    try:
        proc = subprocess.run(
            [exe, *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as error:
        raise GitError(f"git {args[0]} {timeout:.0f} sn'de bitmedi.") from error
    if proc.returncode != 0:
        detail = _tail(proc.stderr or proc.stdout, 400) or f"çıkış kodu {proc.returncode}"
        raise GitError(f"git {args[0]}: {detail}")
    return proc.stdout.strip()


def repo_root(path: str | Path) -> Path:
    """Klasörün git kökü; git deposu değilse GitError."""
    path = Path(path).expanduser()
    if not path.is_dir():
        raise GitError(f"Klasör yok: {path}")
    try:
        return Path(git(["rev-parse", "--show-toplevel"], path)).resolve()
    except GitError as error:
        raise GitError(f"Git deposu değil: {path}") from error


def current_branch(repo: Path) -> str:
    name = git(["rev-parse", "--abbrev-ref", "HEAD"], repo)
    if name == "HEAD":
        raise GitError("Ana klasör bir dalda değil (detached HEAD).")
    return name


def create_worktree(repo: Path, card_id: str) -> dict[str, str]:
    """Kart için worktree + dal açar. Dönen sözlük karta yazılır."""
    base = current_branch(repo)
    base_sha = git(["rev-parse", "HEAD"], repo)
    branch = f"{BRANCH_PREFIX}{card_id}"
    path = WORKTREE_ROOT / f"{repo.name}-{card_id}"
    if path.exists():
        raise GitError(f"Çalışma kopyası zaten var: {path}")
    WORKTREE_ROOT.mkdir(parents=True, exist_ok=True)
    git(["worktree", "add", "-b", branch, str(path), base_sha], repo)
    return {"worktree": str(path), "branch": branch, "base_branch": base, "base_sha": base_sha}


def commit_all(worktree: Path, message: str) -> bool:
    """Worktree'deki her değişikliği tek commit'ler. Değişiklik yoksa False."""
    git(["add", "-A"], worktree)
    if not git(["status", "--porcelain"], worktree):
        return False
    git(["commit", "-m", message], worktree)
    return True


def diff_stat(repo_or_worktree: Path, base_sha: str) -> str:
    """`3 files changed, 40 insertions(+), 2 deletions(-)` — kartta gösterilen özet."""
    out = git(["diff", "--shortstat", f"{base_sha}..HEAD"], repo_or_worktree)
    return out.strip()


def diff_text(repo_or_worktree: Path, base_sha: str, limit: int = DIFF_SCAN_CHARS) -> str:
    """Bekçinin taradığı tam diff (bağlamsız); çok büyükse baştan kesilir."""
    return git(["diff", "--unified=0", "--no-color", f"{base_sha}..HEAD"], repo_or_worktree)[:limit]


def has_commits(worktree: Path, base_sha: str) -> bool:
    return bool(git(["rev-list", f"{base_sha}..HEAD"], worktree))


def run_test(worktree: Path, cmd: str, timeout: float = TEST_TIMEOUT) -> TestResult:
    """Kabuk altındaki bütün ağaç Claude işleri gibi Job Object'e bağlı (Terra incelemesi):
    psutil'le "çocukları bul öldür" yetim torunu kaçırıyor, Chiron kapanınca da test yaşıyordu.
    Askıda başlar, job'a atanınca uyanır — atamadan önce çocuk doğurup kaçamasın."""
    from backend.core.claude_jobs import CREATE_SUSPENDED, ProcessTree

    proc = subprocess.Popen(
        cmd,
        shell=True,
        cwd=str(worktree),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=_NO_WINDOW | (CREATE_SUSPENDED if os.name == "nt" else 0),
    )
    try:
        tree = ProcessTree(proc)
    except RuntimeError as error:
        return TestResult(False, None, str(error), cmd)
    timed_out = False
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        tree.kill()
        try:
            out, _ = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            out = b""
    finally:
        tree.close()
    text = (out or b"").decode("utf-8", "replace")
    if timed_out:
        return TestResult(False, None, _tail(f"{text}\n{timeout / 60:.0f} dk sınırı doldu, test durduruldu."), cmd)
    return TestResult(proc.returncode == 0, proc.returncode, _tail(text), cmd)


def reset_after_test(worktree: Path) -> None:
    """Kopyayı testten hemen önceki commit'e döndürür: testin bıraktığı izlenmeyen dosyalar
    (`__pycache__`, rapor) ve değiştirdiği izlenen dosyalar gider.

    Yalnızca `commit_all`'dan SONRA çağrılır: o anda HEAD'den farklı her şey testin ürünüdür,
    Claude'un işi zaten commit'te. Yoksa (canlı deneme 2026-10-26) `worktree remove`
    reddediyor, dal silinemiyor; "Yeniden dene"de de testin yan etkisi bir sonraki commit'e
    Claude'un işiymiş gibi karışıyordu (Terra). `-x` yok: .gitignore'daki dosyalara dokunulmaz.
    """
    git(["reset", "--hard", "-q", "HEAD"], worktree)
    git(["clean", "-fdq"], worktree)


def merge(repo: Path, branch: str, base_branch: str, message: str) -> str:
    """Ana klasörde birleştirir, birleşme commit'inin kısa sha'sını döner.

    Ana klasör kartın açıldığı dalda olmalı ve izlenen dosyalarda commit'lenmemiş değişiklik
    olmamalı — Yunus'un yarım işinin üstüne birleştirme yapılmaz. Çakışmada birleştirme geri alınır.
    """
    if current_branch(repo) != base_branch:
        raise GitError(f"Ana klasör şu an başka dalda; kart '{base_branch}' dalından açılmıştı.")
    dirty = [line for line in git(["status", "--porcelain"], repo).splitlines() if not line.startswith("??")]
    if dirty:
        raise GitError(f"Ana klasörde commit'lenmemiş {len(dirty)} değişiklik var; önce onları commit'le ya da kenara al.")
    try:
        git(["merge", "--no-ff", "-m", message, branch], repo)
    except GitError as error:
        try:
            git(["merge", "--abort"], repo)
        except GitError:
            pass
        raise GitError(
            f"Birleştirmede çakışma: '{base_branch}' dalı kart açıldıktan sonra değişmiş. ({error})"
        ) from error
    return git(["rev-parse", "--short", "HEAD"], repo)


def remove_worktree(repo: Path, worktree: Path, *, force: bool = False) -> None:
    args = ["worktree", "remove", str(worktree)]
    if force:
        args.insert(2, "--force")
    git(args, repo)


def delete_branch(repo: Path, branch: str) -> None:
    """Yalnızca birleşmiş dalı siler (`-d`); birleşmemişse git reddeder, dal kalır."""
    if not branch.startswith(BRANCH_PREFIX):
        raise GitError("Yalnızca pano dalları silinebilir.")
    git(["branch", "-d", branch], repo)


def list_repos() -> list[dict[str, str]]:
    """~/Projects altındaki git depoları + önerilen test komutu (karta proje seçmek için)."""
    repos: list[dict[str, str]] = []
    if not PROJECTS_DIR.is_dir():
        return repos
    for child in sorted(PROJECTS_DIR.iterdir(), key=lambda p: p.name.lower()):
        if child.name.startswith(".") or not child.is_dir() or not (child / ".git").exists():
            continue
        repos.append({"name": child.name, "path": str(child), "test_cmd": suggest_test(child)})
    return repos


def suggest_test(repo: Path) -> str:
    """Depodaki düzene bakıp test komutu önerir; bulamazsa boş (kart testsiz birleşmeye gider).

    venv worktree'ye gelmez (git dışı) — ana klasörün venv'i mutlak yolla kullanılır.
    """
    python = repo / "venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = repo / ".venv" / "Scripts" / "python.exe"
    if python.exists() and (repo / "tests").is_dir():
        return f'"{python}" -m pytest -q -p no:cacheprovider --basetemp="{PYTEST_TMP}"'
    return ""


_SAFE_ID = re.compile(r"^K-\d{3,6}$")


def safe_card_id(card_id: str) -> str:
    """Dal ve klasör adına girer; yalnız `K-001` biçimi kabul edilir."""
    if not _SAFE_ID.match(card_id):
        raise GitError("Geçersiz kart kimliği.")
    return card_id
