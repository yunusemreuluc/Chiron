"""Telefondan Claude Code'a iş — PC ucu (Faz 1, 2026-10-03).

Kullanıcı isteği (2026-09-30): "ben işteyken telefonla görev verince Chiron senin
sisteminle yapabilir mi?" Telefon `POST /api/remote/claude` ile görev bırakır;
burada `claude -p` başlatılır — normal oturumun aynısı: `~/.claude/CLAUDE.md`,
Jarvis hafızası, skill'ler, Codex lane'leri. Telefon `GET` ile durumu ve özeti alır.

Kurallar (Plan-Claude-Entegrasyonu § Faz 1):
- Tek seferde TEK iş; gerisi kuyrukta. İki tam yetkili ajan aynı dosyalara yazmasın.
- Araç kısıtı yok (kullanıcı kararı) ama izin modu `auto`: bu oturumun kendisi gibi,
  tehlikeli adımı sınıflandırıcı durdurur. Üstüne sistem notu: geri alınamayan adıma
  gelince yapma, `ONAY_GEREKLI:` satırıyla dur → iş "onay bekliyor" olur, telefondan
  gelen cevap aynı oturumu `--resume` ile sürdürür.
- Süre sınırı: takılan iş kotayı sonsuza kadar yemesin. Süre dolunca / iptalde
  SÜREÇ AĞACI öldürülür — claude Bash ile codex/python başlatmış olabilir
  (bkz. Bilinen-Tuzaklar: alt süreç bırakma).
- Her işin tam akışı `logs/claude-jobs/<id>.jsonl`, özeti `<id>.json`.

GÜVENLİK: görev metni ARGÜMAN olarak verilmez, stdin'den gider. `claude` npm
başlatıcısı bir `.CMD`; Windows'ta .cmd'ye argüman geçmek cmd.exe ayrıştırmasından
geçer (`&`, `|`, `%` ile komut enjeksiyonu — "BatBadBut"). Bu yüzden başlatıcının
çağırdığı `claude.exe` doğrudan çalıştırılır ve argümanlar sabit kalır.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from backend.core import bekci

logger = logging.getLogger("chiron.claude_jobs")

BASE_DIR = Path(__file__).resolve().parents[2]
JOBS_DIR = BASE_DIR / "logs" / "claude-jobs"
# Claude'un açıldığı klasör: kullanıcının kendi oturumları da buradan açılıyor,
# hafıza köprüsü ve global CLAUDE.md burada devrede.
WORK_DIR = Path.home()

MAX_TASK_CHARS = 4000
MAX_QUEUE = 3
TIME_LIMIT_SECONDS = 45 * 60
PERMISSION_MODE = "auto"
KEEP_JOBS = 30
MAX_LOG_BYTES = 20 * 1024 * 1024  # iş başına; aşan kısım loga yazılmaz, ayrıştırma sürer
APPROVAL_MARKER = "ONAY_GEREKLI:"

SYSTEM_NOTE = f"""\
Bu iş Yunus'un telefonundan, Chiron üzerinden geldi. Yunus PC başında değil; \
soru sorarsan cevabı ancak sonra, telefondan gelir.
- İşi uçtan uca kendin bitir; netleştirme gerekiyorsa makul varsayımla ilerle ve varsayımı özette söyle.
- Geri alınamayan bir adıma gelirsen (toplu silme, üzerine yazma, ödeme, başkasına mesaj/e-posta/yayın, \
force push, Drive/Etsy yüklemesi) O ADIMI YAPMA. Oraya kadar hazırla, sonra son mesajını \
"{APPROVAL_MARKER} <tek cümlede ne yapacağın>" satırıyla bitir ve dur.
- Son mesajın telefonda sesli okunacak: Türkçe, kısa, düz cümleler; ne yaptın, sonuç ne, \
Yunus'un yapması gereken bir şey var mı. Tablo, kod bloğu, uzun yol listesi yok.
"""

# Panodan (Chiron'un Ajan Ofisi, PC başında) başlatılan iş. Yunus ekranın başında
# olabilir ya da olmayabilir; özet sesli okunmuyor, karta yazılıyor.
PANO_NOTE = f"""\
Bu iş Chiron'un görev panosundan, bir karttan geldi. Yunus sonucu kartta okuyacak; \
soru sorarsan cevabı ancak sonra, kart üzerinden gelir.
- İşi uçtan uca kendin bitir; netleştirme gerekiyorsa makul varsayımla ilerle ve varsayımı özette söyle.
- Geri alınamayan bir adıma gelirsen (toplu silme, üzerine yazma, ödeme, başkasına mesaj/e-posta/yayın, \
force push, Drive/Etsy yüklemesi, git push) O ADIMI YAPMA. Oraya kadar hazırla, sonra son mesajını \
"{APPROVAL_MARKER} <tek cümlede ne yapacağın>" satırıyla bitir ve dur.
- Son mesajın kartın özeti olacak: Türkçe, kısa; ne yaptın, hangi dosyalar değişti, test sonucu ne, \
Yunus'un yapması gereken bir şey var mı.
"""

# Sohbet (Komuta ekranı, 2026-10-27): Yunus ajanla yazışıyor; her mesaj aynı oturumu sürdürür.
CHAT_NOTE = f"""\
Bu mesaj Chiron'un sohbet ekranından geldi; Yunus seninle yazışıyor ve aynı oturum her mesajda sürüyor.
- Normal bir sohbet gibi davran: önceki mesajları biliyorsun, gerekirse soru sor — cevabı bir sonraki mesajda gelir.
- Geri alınamayan bir adıma gelirsen (toplu silme, üzerine yazma, ödeme, başkasına mesaj/e-posta/yayın, \
force push, Drive/Etsy yüklemesi, git push) O ADIMI YAPMA. Oraya kadar hazırla, sonra son mesajını \
"{APPROVAL_MARKER} <tek cümlede ne yapacağın>" satırıyla bitir ve dur; onayı Yunus bir sonraki mesajda verir.
- Cevapların Türkçe, kısa ve doğrudan olsun.
"""

ORIGINS = ("telefon", "pano", "sohbet")
NOTES = {"telefon": SYSTEM_NOTE, "pano": PANO_NOTE, "sohbet": CHAT_NOTE}
MAX_TRAIL = 30  # iş başına saklanan araç adımı satırı (sohbette "ne yaptı" listesi)

# Motorlar (Ajan İstasyonu adım 4, 2026-10-26): pano kartı Claude'a, Codex'e ya da
# Gemini'ye gidebilir. Hepsi aynı kuyrukta, aynı Job Object ve süre sınırıyla.
# Codex ve Gemini npm'in .cmd başlatıcısıyla DEĞİL, `node <betik>` ile çalışır ve görev
# stdin'den gider — .cmd'ye argüman geçmek cmd.exe ayrıştırmasından geçiyor (BatBadBut).
ENGINES = ("claude", "codex", "gemini")
# Claude izin modu: "auto" iş yapar; "plan" salt okunur — lider ajan (Jarvis) yalnızca planlar.
MODES = ("auto", "plan")
CODEX_MODEL = "gpt-5.6-terra"  # ChatGPT planı free (2026-10-11'den beri): Sol/Astra yok
GEMINI_MODEL = "gemini-3.8-flash"
NPM_DIR = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "npm" / "node_modules"
CODEX_JS = NPM_DIR / "@openai" / "codex" / "bin" / "codex.js"
_GEMINI_NOISE = re.compile(
    r"^\s*(Warning: True color|Ripgrep is not available|Loaded cached credentials|Data collection is disabled)"
)
GEMINI_JS = NPM_DIR / "@google" / "gemini-cli" / "bundle" / "gemini.js"

# Claude aboneliğinin doluluğu (Ajan İstasyonu adım 6, 2026-10-26). Claude Code stream-json her işte
# `rate_limit_event` gönderiyor: {status, unifiedWindows: {five_hour|seven_day: {utilization 0..1,
# resetsAt epoch}}}. Tahmin değil, Anthropic'in kendi sayısı. Son görülen diske yazılır (LIMITS_FILE).
LIMITS_FILE = "limits.json"

ACTIVE = ("queued", "running")
# Telefona haber verilecek sonuçlar. `cancelled` yok: iptali kullanıcı kendisi yaptı.
NOTIFY = ("done", "needs_approval", "failed", "timeout", "interrupted")


@dataclass
class Job:
    id: str
    task: str
    status: str = "queued"  # queued|running|done|failed|needs_approval|timeout|cancelled|interrupted
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    resume_of: str | None = None  # bu iş hangi işin oturumunu sürdürüyor
    session_id: str | None = None
    last_step: str = ""
    steps: int = 0
    summary: str = ""
    approval: str = ""
    error: str = ""
    cost_usd: float | None = None
    notified: bool = False  # sonucu telefona söylendi mi (bkz. updates/acknowledge)
    origin: str = "telefon"  # telefon | pano — sistem notunu ve telefona bildirimi belirler
    cwd: str | None = None  # Claude'un açıldığı klasör; boşsa WORK_DIR (pano kartının worktree'si)
    engine: str = "claude"  # claude | codex | gemini
    mode: str = "auto"  # Claude izin modu: auto | plan (salt okunur, lider ajan)
    bekci: list[dict[str, Any]] = field(default_factory=list)  # bekçinin uyarıları (yalnız Claude işleri)
    trail: list[str] = field(default_factory=list)  # araç adımları, sırayla (en fazla MAX_TRAIL)

    def public(self) -> dict[str, Any]:
        data = asdict(self)
        end = self.finished_at or time.time()
        data["elapsed_seconds"] = int(end - self.started_at) if self.started_at else 0
        return data


def find_claude_exe() -> str | None:
    """`claude.CMD`'nin arkasındaki gerçek `claude.exe` (bkz. modül notu)."""
    found = shutil.which("claude")
    if not found:
        return None
    path = Path(found)
    if path.suffix.lower() == ".exe":
        return str(path)
    candidate = path.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    if candidate.exists():
        return str(candidate)
    # .cmd'yi argümanla çalıştırmak enjeksiyon riski; exe yoksa çalıştırmıyoruz.
    return None




# ── Süreç ağacı: Windows Job Object ──────────────────────────────────────────
# NEDEN (2026-10-03, Astra incelemesi): psutil ile "ebeveynin çocuklarını öldür"
# yetmiyor. Claude çıkıp arka planda başlattığı bir alt süreç stdout'u açık
# tutarsa ebeveyn yok, çocuklar bulunamıyor, okuma EOF'a hiç ulaşmıyor ve kuyruk
# sonsuza kadar kilitleniyordu. Job Object'e atanan sürecin TÜM torunları job'da
# kalır; TerminateJobObject hepsini tek çağrıda öldürür. KILL_ON_JOB_CLOSE:
# Chiron çökerse/kapanırsa tutamaç kapanır, Windows ağacı kendisi öldürür.
# Süreç askıda (CREATE_SUSPENDED) başlatılıp job'a atandıktan sonra uyandırılır —
# atamadan önce çocuk başlatıp job dışında kalamasın.

CREATE_SUSPENDED = 0x00000004
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JobObjectExtendedLimitInformation = 9


class ProcessTree:
    """Bir sürecin bütün ağacı. Windows dışında psutil yedeğine düşer.

    Windows'ta Job Object kurulamazsa süreç ÇALIŞTIRILMAZ (hâlâ askıda, öldürülür,
    hata yükselir): psutil yedeği yetim torunu bulamıyor ve kuyruk kilitleniyordu
    (Astra 2. tur). Güvenceyi kaybetmektense iş başarısız olsun.
    """

    def __init__(self, proc: subprocess.Popen) -> None:
        self.proc = proc
        self._job: int | None = None
        if os.name == "nt":
            try:
                self._job = _create_kill_on_close_job()
                _assign_and_resume(self._job, int(proc._handle))  # type: ignore[attr-defined]
            except Exception:
                self._close_job()
                try:
                    proc.kill()
                finally:
                    raise RuntimeError("Süreç ağacı güvenceye alınamadı (Job Object); iş başlatılmadı.")

    def kill(self) -> None:
        if self._job is not None:
            import ctypes

            ctypes.WinDLL("kernel32", use_last_error=True).TerminateJobObject(
                ctypes.c_void_p(self._job), 1
            )
            return
        kill_tree(self.proc.pid)

    def close(self) -> None:
        """Ağacı öldürür ve tutamacı bırakır (her çıkış yolunda çağrılır)."""
        try:
            self.kill()
        finally:
            self._close_job()

    def _close_job(self) -> None:
        if self._job is not None:
            import ctypes

            ctypes.WinDLL("kernel32").CloseHandle(ctypes.c_void_p(self._job))
            self._job = None


def _create_kill_on_close_job() -> int:
    import ctypes
    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class BASIC(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class EXTENDED(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BASIC),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    kernel32.SetInformationJobObject.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    ]
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    info = EXTENDED()
    info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(
        job, _JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)
    ):
        error = ctypes.WinError(ctypes.get_last_error())
        kernel32.CloseHandle(ctypes.c_void_p(job))
        raise error
    return int(job)


def _assign_and_resume(job: int, process_handle: int) -> None:
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    if not kernel32.AssignProcessToJobObject(job, process_handle):
        raise ctypes.WinError(ctypes.get_last_error())
    # Askıda değilse askı sayacı zaten 0 — zararsız.
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtResumeProcess.argtypes = [ctypes.c_void_p]
    ntdll.NtResumeProcess(process_handle)


def kill_tree(pid: int) -> None:
    """Yedek yol: Job Object yoksa psutil ile ağacı öldürür."""
    try:
        import psutil

        parent = psutil.Process(pid)
        procs = parent.children(recursive=True) + [parent]
    except Exception:
        return
    for proc in procs:
        try:
            proc.kill()
        except Exception:
            pass



def _tool_line(name: str, tool_input: dict[str, Any]) -> str:
    """Telefonda "şu an ne yapıyor" satırı."""
    for key in ("description", "command", "file_path", "pattern", "url", "prompt"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            text = " ".join(value.split())
            return f"{name}: {text[:140]}"
    return name


def split_approval(text: str) -> tuple[str, str]:
    """Son mesajdaki `ONAY_GEREKLI:` satırını ayırır → (özet, onay sorusu)."""
    match = re.search(rf"^\s*\**{re.escape(APPROVAL_MARKER)}\**\s*(.+)$", text, re.MULTILINE)
    if not match:
        return text.strip(), ""
    return text.strip(), match.group(1).strip().strip("*").strip()




class ClaudeJobs:
    """İş kuyruğu. Durum bellekte + diskte; tek çalışan thread kuyruğu boşaltır."""

    def __init__(
        self,
        jobs_dir: Path = JOBS_DIR,
        launcher: Callable[[Job, Path], subprocess.Popen] | None = None,
        time_limit: float = TIME_LIMIT_SECONDS,
    ) -> None:
        self.jobs_dir = jobs_dir
        self._launch = launcher or self._launch_engine
        self.time_limit = time_limit
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._queue: deque[str] = deque()
        self._proc: subprocess.Popen | None = None
        self._tree: ProcessTree | None = None
        self._cancel: set[str] = set()
        self._closed = False
        self._worker: threading.Thread | None = None
        self._codex_text: dict[str, str] = {}  # iş başına Codex'in son mesajı (sonuç metni)
        self._limits: dict[str, Any] = self._load_limits()
        self._load()

    # ── Kalıcılık ────────────────────────────────────────────────────────
    def _load(self) -> None:
        if not self.jobs_dir.exists():
            return
        metas = sorted(
            (p for p in self.jobs_dir.glob("*.json") if p.name != LIMITS_FILE), key=lambda p: p.stat().st_mtime
        )
        for path in metas[-KEEP_JOBS:]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                job = Job(**{k: v for k, v in data.items() if k in Job.__dataclass_fields__})
            except Exception:
                continue
            if job.status in ACTIVE:
                # Chiron kapanırken yarıda kalan iş. Süreç ağacı Job Object'le
                # Chiron'a bağlıydı (KILL_ON_JOB_CLOSE) — Chiron ölünce o da öldü.
                job.status = "interrupted"
                job.error = "Chiron kapandığı için iş yarıda kaldı."
                job.finished_at = job.finished_at or time.time()
                self._save(job)
            self._jobs[job.id] = job
        self._prune_disk()

    def _save(self, job: Job) -> None:
        """Diske yazar. Hata iş thread'ini ÖLDÜRMEZ — durum bellekte doğru kalır
        (Astra: running kaydı patlayınca worker ölüyor, kuyruk tıkanıyordu)."""
        try:
            self.jobs_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.jobs_dir / f"{job.id}.json.tmp"
            tmp.write_text(json.dumps(asdict(job), ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.jobs_dir / f"{job.id}.json")
        except Exception:
            logger.exception("Claude işi diske yazılamadı: %s", job.id)

    def _prune_disk(self) -> None:
        """Bellekte tutulmayan eski işlerin dosyalarını siler (yalnız kendi klasörü)."""
        try:
            for path in self.jobs_dir.iterdir():
                match = re.fullmatch(r"([0-9a-f]{8})\.(?:json|jsonl|json\.tmp)", path.name)  # limits.json eşleşmez
                if match and match.group(1) not in self._jobs:
                    path.unlink(missing_ok=True)
        except Exception:
            logger.exception("Eski Claude iş dosyaları silinemedi")

    # ── Dış arayüz ───────────────────────────────────────────────────────
    def submit(
        self,
        task: str,
        resume_of: str | None = None,
        origin: str = "telefon",
        cwd: str | None = None,
        engine: str = "claude",
        mode: str = "auto",
        session_id: str | None = None,
    ) -> Job:
        """`resume_of`: bir önceki işin oturumunu sürdürür. `session_id`: oturumu kimliğiyle sürdürür
        (sohbet ve terminalden devralınan oturum; `cwd` oturumun açıldığı klasör olmalı)."""
        task = task.strip()
        if not task:
            raise ValueError("Görev boş.")
        if len(task) > MAX_TASK_CHARS:
            raise ValueError(f"Görev en fazla {MAX_TASK_CHARS} karakter olabilir.")
        if origin not in ORIGINS:
            raise ValueError("Bilinmeyen iş kaynağı.")
        if cwd is not None and not Path(cwd).is_dir():
            raise ValueError(f"Çalışma klasörü yok: {cwd}")
        if engine not in ENGINES or mode not in MODES:
            raise ValueError("Bilinmeyen ajan ya da mod.")
        if (resume_of or session_id) and engine != "claude":
            raise ValueError("Bu ajan oturum sürdürmüyor; görev baştan verilir.")
        if session_id and not re.fullmatch(r"[0-9a-fA-F-]{8,64}", session_id):
            raise ValueError("Geçersiz oturum kimliği.")
        with self._lock:
            if self._closed:
                raise ValueError("Chiron kapanıyor; iş alınmıyor.")
            parent = None
            if resume_of:
                parent = self._jobs.get(resume_of)
                if not parent or not parent.session_id:
                    raise ValueError("Sürdürülecek iş bulunamadı ya da oturumu yok.")
                if parent.status in ACTIVE:
                    raise ValueError("O iş hâlâ sürüyor; bitince devam ettirilebilir.")
            if len(self._queue) >= MAX_QUEUE:
                raise ValueError("Kuyruk dolu; önceki işler bitsin.")
            # Panonun işi telefona haber verilmez: sonuç kartta okunuyor.
            job = Job(
                id=secrets.token_hex(4), task=task, resume_of=resume_of, origin=origin,
                notified=origin != "telefon", cwd=cwd, engine=engine, mode=mode,
            )
            if parent:
                job.session_id = parent.session_id
                # Claude oturumları klasöre bağlı: devam, oturumun açıldığı klasörde olmalı.
                job.cwd = parent.cwd
            elif session_id:
                job.session_id = session_id
            self._jobs[job.id] = job
            self._queue.append(job.id)
            self._save(job)
            self._trim()
            if not self._worker or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._run_queue, name="claude-jobs", daemon=True)
                self._worker.start()
        logger.info("Claude işi kuyruğa alındı: %s", job.id)
        return job

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            data = job.public()
            if job.status == "queued" and job_id in self._queue:
                data["queue_position"] = list(self._queue).index(job_id) + 1
            return data

    def list(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
            return [j.public() for j in jobs[:limit]]

    def active_count(self) -> int:
        """Kuyrukta bekleyen + çalışan iş sayısı (Çıkış onayı bununla soruluyor)."""
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.status in ACTIVE)

    def updates(self) -> list[dict[str, Any]]:
        """Telefona henüz söylenmemiş sonuçlar, eskiden yeniye."""
        with self._lock:
            pending = [j for j in self._jobs.values() if j.status in NOTIFY and not j.notified]
            return [j.public() for j in sorted(pending, key=lambda j: j.finished_at or 0)]

    def updates_snapshot(self) -> dict[str, Any]:
        """Söylenmemiş sonuçlar + süren iş sayısı, TEK kilit altında: ikisi ayrı okununca
        son iş arada bitip `jobs=[], active=0` dönebiliyor, telefon yoklamayı bırakıp
        sonucu kaçırıyordu (Astra)."""
        with self._lock:
            pending = [j for j in self._jobs.values() if j.status in NOTIFY and not j.notified]
            return {
                "jobs": [j.public() for j in sorted(pending, key=lambda j: j.finished_at or 0)],
                "active": sum(1 for j in self._jobs.values() if j.status in ACTIVE),
            }

    def acknowledge(self, job_ids: list[str]) -> int:
        """Telefon sonucu kullanıcıya söyledi: bir daha gönderme."""
        count = 0
        with self._lock:
            for job_id in job_ids:
                job = self._jobs.get(job_id)
                if job and job.status in NOTIFY and not job.notified:
                    job.notified = True
                    self._save(job)
                    count += 1
        return count

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status not in ACTIVE:
                return False
            if job.status == "queued":
                if job_id in self._queue:
                    self._queue.remove(job_id)
                self._finish(job, "cancelled", error="İptal edildi.")
                return True
            # Çalışıyor: süreç henüz kaydedilmediyse _run kayıt anında bu işareti görür.
            self._cancel.add(job_id)
            tree = self._tree
        if tree:
            tree.kill()
        return True

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            for job_id in list(self._queue):
                self._finish(self._jobs[job_id], "cancelled", error="Chiron kapandı.")
            self._queue.clear()
            tree = self._tree
        if tree:
            tree.kill()

    # ── Çalıştırma ───────────────────────────────────────────────────────
    def _trim(self) -> None:
        done = sorted(
            (j for j in self._jobs.values() if j.status not in ACTIVE), key=lambda j: j.created_at
        )
        removed = done[: max(0, len(self._jobs) - KEEP_JOBS)]
        for job in removed:
            self._jobs.pop(job.id, None)
        if removed:
            self._prune_disk()

    def _finish(self, job: Job, status: str, error: str = "") -> None:
        job.status = status
        job.finished_at = time.time()
        if job.engine == "claude":
            job.bekci = bekci.job_hits(job.id)
        if error:
            job.error = error
        self._save(job)
        logger.info("Claude işi bitti: %s → %s", job.id, status)

    def _run_queue(self) -> None:
        while True:
            with self._lock:
                if not self._queue or self._closed:
                    self._worker = None
                    return
                job = self._jobs[self._queue.popleft()]
                job.status = "running"
                job.started_at = time.time()
                self._save(job)
            try:
                self._run(job)
            except Exception as error:  # iş thread'i hiçbir hatada ölmemeli
                logger.exception("Claude işi çöktü: %s", job.id)
                with self._lock:
                    if job.status in ACTIVE:
                        self._finish(job, "failed", error=f"Beklenmeyen hata: {error}")

    def _launch_engine(self, job: Job, log_path: Path) -> subprocess.Popen:
        if job.engine == "claude":
            exe = find_claude_exe()
            if not exe:
                raise FileNotFoundError("claude.exe bulunamadı (npm i -g @anthropic-ai/claude-code).")
            args = [
                exe,
                "-p",
                "--output-format",
                "stream-json",
                "--verbose",
                "--permission-mode",
                job.mode if job.mode == "plan" else PERMISSION_MODE,
                "--append-system-prompt",
                NOTES[job.origin],
                # Bekçi (adım 7): PreToolUse hook'u yalnız bu oturuma; global ayara dokunulmaz.
                "--settings",
                str(bekci.settings_path()),
            ]
            # Başlarken oturum kimliği yalnız sürdürülen işte dolu (yenisinde olaylardan gelir).
            if job.session_id:
                args += ["--resume", job.session_id]
        else:
            node = shutil.which("node")
            script = CODEX_JS if job.engine == "codex" else GEMINI_JS
            if not node or not script.exists():
                raise FileNotFoundError(f"{job.engine} bulunamadı ({script}).")
            if job.engine == "codex":
                # Yazma yalnız -C klasöründe (kartın worktree'si). Son argüman "-": görev stdin'den.
                args = [
                    node, str(script), "exec", "--skip-git-repo-check", "-m", CODEX_MODEL,
                    "--sandbox", "workspace-write", "--json", "-C", job.cwd or str(WORK_DIR), "-",
                ]
            else:
                # Gemini yalnız okur (plan modu = salt okunur); -p sabit, asıl görev stdin'de.
                args = [
                    node, str(script), "--skip-trust", "-m", GEMINI_MODEL,
                    "--approval-mode", "plan", "-o", "text", "-p", "Görev standart girişte; onu yap.",
                ]
        env = dict(os.environ)
        # Chiron bir Claude oturumundan başlatıldıysa iç içe oturum işareti taşınmasın.
        env.pop("CLAUDECODE", None)
        env["CHIRON_CLAUDE_JOB"] = job.id
        # Pano worktree'si: bekçi bu kökün dışına yazmayı yakalar. Kökü olmayan işte (WORK_DIR) bakılmaz.
        env.pop(bekci.ROOT_ENV, None)
        if job.cwd:
            env[bekci.ROOT_ENV] = job.cwd
        # Askıda başlar; _run Job Object'e atayıp uyandırır (bkz. ProcessTree).
        return subprocess.Popen(
            args,
            cwd=job.cwd or str(WORK_DIR),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | CREATE_SUSPENDED,
        )

    def _run(self, job: Job) -> None:
        log_path = self.jobs_dir / f"{job.id}.jsonl"
        try:
            proc = self._launch(job, log_path)
        except Exception as error:
            with self._lock:
                self._finish(job, "failed", error=str(error))
            return

        try:
            tree = ProcessTree(proc)
        except Exception as error:
            logger.exception("Claude işi başlatılamadı: %s", job.id)
            for stream in (proc.stdout, proc.stdin):
                try:
                    if stream:
                        stream.close()
                except Exception:
                    pass
            with self._lock:
                self._finish(job, "failed", error=str(error))
            return
        with self._lock:
            self._proc, self._tree = proc, tree
            # Kayıttan ÖNCE gelen iptal/kapanış burada uygulanır (Astra/Sol: yarış).
            stop_now = job.id in self._cancel or self._closed
        if stop_now:
            tree.kill()

        result: dict[str, Any] | None = None
        tail: deque[str] = deque(maxlen=5)
        events: list[dict[str, Any]] = []
        texts: list[str] = []  # Gemini düz metin yazar; sonucun kendisi bu
        reader: threading.Thread | None = None
        timed_out = False
        try:
            # Görev stdin'den, ayrı thread'de: süreç okumazsa boru dolup _run'ı kilitlemesin.
            task = job.task
            if job.engine != "claude":
                # Codex/Gemini'de --append-system-prompt yok: kural notu görevin başına.
                task = f"{NOTES[job.origin]}\n\n{job.task}"
            threading.Thread(target=_feed_stdin, args=(proc, task), daemon=True).start()
            reader = threading.Thread(
                target=self._read_output, args=(job, proc, log_path, events, tail, texts), daemon=True
            )
            reader.start()
            try:
                proc.wait(timeout=self.time_limit)
            except subprocess.TimeoutExpired:
                timed_out = True
        finally:
            # Ana süreç bitti ya da süre doldu: geride kalan torunlar da ölür,
            # stdout'u tutan kalmaz → okuyucu EOF görür.
            tree.close()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            if reader is not None:
                reader.join(timeout=10)
            for stream in (proc.stdout, proc.stdin):
                try:
                    if stream:
                        stream.close()
                except Exception:
                    pass
            with self._lock:
                self._proc, self._tree = None, None

        for event in events:
            result = self._on_event(job, event) or result
        if result is None and job.engine == "gemini" and proc.returncode == 0 and texts:
            # stderr stdout'a katılı: CLI'nin terminal uyarıları cevaba karışmasın (canlı deneme).
            lines = [ln for ln in "".join(texts).splitlines() if not _GEMINI_NOISE.match(ln)]
            result = {"type": "result", "subtype": "success", "result": "\n".join(lines).strip()}

        with self._lock:
            if job.id in self._cancel or self._closed:
                self._cancel.discard(job.id)
                self._finish(job, "cancelled", error="İptal edildi." if not self._closed else "Chiron kapandı.")
            elif timed_out:
                self._finish(job, "timeout", error=f"{self.time_limit // 60:.0f} dk sınırı doldu, durduruldu.")
            elif result is None:
                detail = " | ".join(tail) or f"çıkış kodu {proc.returncode}"
                self._finish(job, "failed", error=f"{job.engine.capitalize()} sonuç vermeden kapandı: {detail}")
            else:
                text = str(result.get("result") or "")
                job.summary, job.approval = split_approval(text)
                job.cost_usd = result.get("total_cost_usd")
                if result.get("is_error") or result.get("subtype") not in (None, "success"):
                    # Codex hatası (kota, bağlantı) sonucun METNİNDE; Claude'unki subtype'ta.
                    detail = result.get("result") if job.engine != "claude" else None
                    self._finish(job, "failed", error=str(detail or result.get("subtype") or "hata")[:500])
                elif job.approval:
                    self._finish(job, "needs_approval")
                else:
                    self._finish(job, "done")

    def _read_output(
        self,
        job: Job,
        proc: subprocess.Popen,
        log_path: Path,
        events: list[dict[str, Any]],
        tail: deque[str],
        texts: list[str] | None = None,
    ) -> None:
        """stdout'u satır satır okur, log'a yazar (kotalı), canlı adımı günceller."""
        assert proc.stdout is not None
        written = 0
        log = None
        try:
            try:
                self.jobs_dir.mkdir(parents=True, exist_ok=True)
                log = open(log_path, "ab")
            except Exception:
                logger.exception("Claude iş logu açılamadı: %s", log_path)
            for raw in proc.stdout:
                if log is not None and written + len(raw) <= MAX_LOG_BYTES:
                    try:
                        log.write(raw)
                        log.flush()
                        written += len(raw)
                    except Exception:
                        log = None
                text = raw.decode("utf-8", "replace")
                line = text.strip()
                if job.engine == "gemini":
                    if texts is not None and len(texts) < 4000:
                        texts.append(text)
                    if line:
                        tail.append(line[:300])
                        with self._lock:
                            job.last_step = line[:160]
                    continue
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    tail.append(line[:300])
                    continue
                if not isinstance(event, dict):
                    continue
                if job.engine == "codex":
                    event = self._codex_event(job, event)
                    if event is None:
                        continue
                if event.get("type") == "result":
                    events.append(event)
                else:
                    self._on_event(job, event)
        except Exception:
            logger.exception("Claude çıktısı okunamadı")
        finally:
            if log is not None:
                try:
                    log.close()
                except Exception:
                    pass

    def _codex_event(self, job: Job, event: dict[str, Any]) -> dict[str, Any] | None:
        """Codex `--json` olayını Claude stream-json biçimine çevirir; gerisi aynı yoldan akar.
        (codex 0.154: thread.started, item.completed{agent_message|command_execution|file_change},
        turn.completed, turn.failed, error)."""
        kind = event.get("type")
        if kind == "thread.started":
            return {"type": "system", "session_id": event.get("thread_id")}
        if kind == "item.completed":
            item = event.get("item") or {}
            itype = item.get("type")
            if itype == "agent_message":
                text = str(item.get("text") or "")
                self._codex_text[job.id] = text
                return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}
            if itype == "command_execution":
                tool = {"type": "tool_use", "name": "Bash", "input": {"command": str(item.get("command") or "")}}
                return {"type": "assistant", "message": {"content": [tool]}}
            if itype == "file_change":
                changes = item.get("changes") or []
                path = changes[0].get("path") if changes and isinstance(changes[0], dict) else ""
                tool = {"type": "tool_use", "name": "Edit", "input": {"file_path": str(path or "")}}
                return {"type": "assistant", "message": {"content": [tool]}}
            return None
        if kind == "turn.completed":
            return {"type": "result", "subtype": "success", "is_error": False,
                    "result": self._codex_text.pop(job.id, "")}
        if kind in ("turn.failed", "error"):
            message = (event.get("error") or {}).get("message") if isinstance(event.get("error"), dict) else None
            return {"type": "result", "subtype": "hata", "is_error": True,
                    "result": str(message or event.get("message") or kind)}
        return None

    # ── Claude kotası ────────────────────────────────────────────────────
    def limits(self) -> dict[str, Any]:
        """Son görülen Claude kota durumu: {status, five_hour, seven_day, ts} — hiç görülmediyse {}."""
        with self._lock:
            return json.loads(json.dumps(self._limits))

    def _load_limits(self) -> dict[str, Any]:
        try:
            data = json.loads((self.jobs_dir / LIMITS_FILE).read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _note_limits(self, info: dict[str, Any]) -> None:
        """`rate_limit_event`'i saklar (kilit ALTINDA çağrılır)."""
        windows = info.get("unifiedWindows") if isinstance(info.get("unifiedWindows"), dict) else {}
        limits: dict[str, Any] = {"status": str(info.get("status") or ""), "ts": time.time()}
        for name in ("five_hour", "seven_day"):
            w = windows.get(name)
            if isinstance(w, dict) and w.get("utilization") is not None:
                limits[name] = {"used": float(w["utilization"]), "resets_at": float(w.get("resetsAt") or 0)}
        if info.get("status") == "rejected" and info.get("resetsAt"):
            limits["blocked_until"] = float(info["resetsAt"])
        self._limits = limits
        try:
            self.jobs_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.jobs_dir / f"{LIMITS_FILE}.tmp"
            tmp.write_text(json.dumps(limits), encoding="utf-8")
            os.replace(tmp, self.jobs_dir / LIMITS_FILE)
        except Exception:
            logger.exception("Claude kota durumu yazılamadı")

    def _on_event(self, job: Job, event: dict[str, Any]) -> dict[str, Any] | None:
        kind = event.get("type")
        with self._lock:
            if kind == "rate_limit_event" and isinstance(event.get("rate_limit_info"), dict):
                self._note_limits(event["rate_limit_info"])
                return None
            if event.get("session_id") and not job.session_id:
                job.session_id = str(event["session_id"])
            if kind == "result":
                if event.get("session_id"):
                    job.session_id = str(event["session_id"])
                return event
            if kind == "assistant":
                for block in (event.get("message") or {}).get("content") or []:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use":
                        job.steps += 1
                        job.last_step = _tool_line(str(block.get("name")), block.get("input") or {})
                        if len(job.trail) < MAX_TRAIL:
                            job.trail.append(job.last_step)
                    elif block.get("type") == "text" and str(block.get("text", "")).strip():
                        job.last_step = " ".join(str(block["text"]).split())[:160]
        return None


def _feed_stdin(proc: subprocess.Popen, task: str) -> None:
    try:
        assert proc.stdin is not None
        proc.stdin.write(task.encode("utf-8"))
        proc.stdin.close()
    except Exception:
        pass


jobs = ClaudeJobs()
