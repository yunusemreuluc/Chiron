"""Ajan Ofisi — "kim ne yapıyor" durumu (Faz A, 2026-10-02).

Ofis kendi ajanını çalıştırmaz; var olan düzeni GÖZLER. İki kaynak var:

1. Claude Code hook olayları — `~/.claude/hooks/ofis-olay.py` her olayı
   `%LOCALAPPDATA%\\airon\\ofis\\events.jsonl`'e tek satır yazar. Claude ana döngüsü,
   alt ajanlar ve Bash/PowerShell ile çağrılan Codex/Bunny/Gemini/OpenCode lane'leri
   buradan çıkarılır.
2. Codex'in kendi oturum kayıtları — `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`.
   Model, sandbox, adım adım komutlar, gerçek token ve kota yüzdesi buradan gelir.

Dürüstlük kuralı (Bilinen-Tuzaklar § Arayüzde dürüstlük): gösterilen her şey bir
olaydan gelir. Bilinmeyen şey "bilinmiyor" diye gösterilir, tahmin edilmez —
ör. arka planda başlatılan bir Bunny/Gemini lane'inin bitişini hiçbir hook
söylemiyor; onun izi `tracking="sinirli"` ile işaretlenir.

Durum makinesi (`OfficeState`) saf ve senkron — testler doğrudan olay besler.
Dosya izleme (`OfficeWatcher`) ayrı bir thread; saniyede bir `stat`, yalnız yeni
baytları okur. Plan: Notes/Plan-Claude-Entegrasyonu.md § Faz A.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("airon.ofis")

EVENTS_PATH = (
    Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "airon" / "ofis" / "events.jsonl"
)
CODEX_SESSIONS = Path.home() / ".codex" / "sessions"

# ── Kadro — kalıcı kimlikler (masalar) ───────────────────────────────────────
# Roller ~/.claude/CLAUDE.md'deki "Hangi iş kime" tablosundan. Yeni bir model
# eklenince buraya bir masa eklenir.
ROSTER: list[dict[str, str]] = [
    {
        "id": "claude",
        "name": "Claude",
        "model": "Claude Opus",
        "role": "Şef — plan, mimari, hata teşhisi, güvenlik, birleştirme",
        "color": "#ffb38a",
    },
    {
        "id": "sol",
        "name": "Codex Sol",
        "model": "gpt-5.6-sol",
        "role": "Yürütme — mekanik ve standart kod",
        "color": "#6fd3ff",
    },
    {
        "id": "astra",
        "name": "Codex Astra",
        "model": "gpt-6-astra",
        "role": "Kıdemli yürütme ve çapraz inceleme",
        "color": "#b59cff",
    },
    {
        "id": "bunny",
        "name": "Space Bunny",
        "model": "stealth/space-bunny-alpha",
        "role": "Arşiv — 200k+ token okuma, uzun özet",
        "color": "#ff9ec7",
    },
    {
        "id": "gemini",
        "name": "Gemini",
        "model": "gemini-3.8-flash",
        "role": "Araştırma — ≤200k okuma, karşılaştırma",
        "color": "#7ee0b5",
    },
    {
        "id": "opencode",
        "name": "OpenCode",
        "model": "space-bunny-alpha (OpenCode)",
        "role": "Ucuz kod — hassas olmayan küçük iş",
        "color": "#ffd27a",
    },
    {
        "id": "subagents",
        "name": "Alt ajanlar",
        "model": "Claude",
        "role": "Geçici masalar — Explore, Plan, general-purpose…",
        "color": "#a9c4e6",
    },
]
DESK_IDS = {d["id"] for d in ROSTER}

# Durumlar
WORKING, WAITING, IDLE, DONE, FAILED, LEFT = (
    "calisiyor",
    "onay_bekliyor",
    "bosta",
    "bitti",
    "hata",
    "ayrildi",
)
# Pano kolonları
COL_RUN, COL_APPROVAL, COL_REVIEW, COL_DONE, COL_FAILED, COL_STOPPED = (
    "yurutuluyor",
    "onay",
    "incelemede",
    "bitti",
    "hata",
    "durdu",
)

MAX_WORKERS = 300
MAX_TASKS = 400
ACTIVITY_LEN = 60
FILES_CAP = 200
SNAPSHOT_TASKS = 80
SNAPSHOT_FINISHED_WORKERS = 40
CODEX_LINK_WINDOW_S = 90.0

# ── Lane tanıma ──────────────────────────────────────────────────────────────
# Komut segmentinin BAŞINDA olmalı: `grep "codex exec" dosya` bir lane değil.
_SEG = r"(?:^|[;&|\n(])\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*"
_LANE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("codex", re.compile(_SEG + r"(?:\S*[\\/])?codex(?:\.exe|\.cmd)?\s+exec\b", re.I)),
    ("bunny", re.compile(_SEG + r"\S*python\S*\s+\S*bunny\.py\b", re.I)),
    ("opencode", re.compile(_SEG + r"(?:\S*[\\/])?opencode(?:\.cmd|\.exe)?\s+run\b", re.I)),
    ("gemini", re.compile(_SEG + r"(?:\S*[\\/])?gemini(?:\.cmd|\.exe)?\s[^\n;&|]*?-p\b", re.I)),
]
_QUOTED = re.compile(r'"((?:[^"\\]|\\.){20,})"|\'([^\']{20,})\'', re.S)
_FLAG_M = re.compile(r"(?:^|\s)-m\s+([^\s\"']+)")
_FLAG_SANDBOX = re.compile(r"--sandbox\s+([\w-]+)")
_FLAG_C = re.compile(r"(?:^|\s)-C\s+(\"[^\"]+\"|'[^']+'|\S+)")
_TEST_CMD = re.compile(
    r"\b(pytest|unittest|npm\s+(?:run\s+)?(?:test|build|lint)|npx\s+tsc|tsc\b|ruff\b|eslint\b"
    r"|cargo\s+test|go\s+test|gradlew\b|vitest|jest\b)",
    re.I,
)
_TEST_FAIL = re.compile(r"\b\d+\s+failed\b|\bFAILED\b|npm ERR!|error TS\d+|\bTraceback\b|\bBUILD FAILED\b")
_TEST_PASS = re.compile(r"\b\d+\s+passed\b|\bBUILD SUCCESSFUL\b|Compiled successfully|\bOK\b")
_CODEX_CMD = re.compile(r'cmd:\s*"((?:[^"\\]|\\.)*)"')
# Claude Code arka plan işi bitince bir sonraki "kullanıcı" mesajı olarak bu bloğu
# enjekte ediyor — içinde işi başlatan çağrının tool_use_id'si ve sonucu var.
_NOTIF_TOOL = re.compile(r"<tool-use-id>\s*([^<\s]+)\s*</tool-use-id>")
_NOTIF_STATUS = re.compile(r"<status>\s*([^<\s]+)\s*</status>")
_NOTIF_SUMMARY = re.compile(r"<summary>(.*?)</summary>", re.S)
_EXIT_CODE = re.compile(r"exit code (\d+)")
_CD_PREFIX = re.compile(r"(?:^|[;&|\n]\s*)cd\s+(\"[^\"]+\"|'[^']+'|[^\s;&|]+)\s*(?:&&|;)")
# Tırnaklı çalıştırılabilir: PowerShell `& "C:/Program Files/Codex/codex.exe" exec` → `codex.exe`
_QUOTED_EXE = re.compile(r"[\"']([^\"']*[\\/])?((?:codex|opencode|gemini|python\d*)(?:\.exe|\.cmd)?)[\"']", re.I)
_ANY_QUOTED = re.compile(r'"(?:[^"\\]|\\.)*"|\'[^\']*\'', re.S)

# ── Gizli değer maskeleme ────────────────────────────────────────────────────
# Hook (~/.claude/hooks/ofis-olay.py) kendi yazdıklarını zaten maskeliyor; bu
# kopya Codex kayıtlarından gelen komutlar ve mesajlar için (Astra incelemesi,
# 2026-10-02 — o yol maskesizdi). İki liste birlikte değişir.
_SECRET_NAME = r"(?:api[_-]?key|access[_-]?token|auth[_-]?token|token|secret|passw(?:or)?d|pwd)"
_SECRET_PATTERNS = [
    (re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_\-]{16,}"), "[gizli]"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"), "[gizli]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}|\bgh[pousr]_[A-Za-z0-9]{30,}"), "[gizli]"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"), "[gizli]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[gizli]"),
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=\-]{12,}"), r"\1 [gizli]"),
    (re.compile(r"(?i)([\"']" + _SECRET_NAME + r"[\"']\s*:\s*)([\"'])[^\"']{4,}\2"), r"\1\2[gizli]\2"),
    (re.compile(r"(?i)(--?" + _SECRET_NAME + r"(?:[=\s]+))(\"[^\"]*\"|'[^']*'|\S+)"), r"\1[gizli]"),
    (re.compile(r"(?i)(\b[A-Z0-9_]*" + _SECRET_NAME + r"[A-Z0-9_]*\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|\S{6,})"), r"\1[gizli]"),
]


def mask(text: str | None) -> str:
    if not text:
        return ""
    for pattern, repl in _SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def classify_lane(command: str | None) -> dict[str, Any] | None:
    """Bash/PowerShell komutu bir model lane'i mi? Öyleyse masa + ayrıntı.

    Eşleşme, tırnak İÇERİĞİ silinmiş komut üzerinde aranır: `echo "a; codex exec"`
    bir lane değil (tırnak içindeki `;` ayraç sayılmasın). Tırnaklı çalıştırılabilir
    yolu (`& "C:/…/codex.exe" exec`) önce çıplak ada indirilir.
    """
    if not command:
        return None
    bare = _QUOTED_EXE.sub(lambda m: m.group(2), command)
    bare = _ANY_QUOTED.sub('""', bare)
    for kind, pattern in _LANE_PATTERNS:
        if not pattern.search(bare):
            continue
        info: dict[str, Any] = {"kind": kind}
        model = _FLAG_M.search(command)
        cd = _CD_PREFIX.search(command)
        info["target_dir"] = cd.group(1).strip("\"'") if cd else None
        if kind == "codex":
            m = (model.group(1) if model else "").lower()
            info["desk"] = "astra" if "astra" in m else "sol"
            info["model"] = model.group(1) if model else None
            sandbox = _FLAG_SANDBOX.search(command)
            info["sandbox"] = sandbox.group(1) if sandbox else None
            target = _FLAG_C.search(command)
            # `-C .` göreli: asıl dizin öndeki `cd` (varsa).
            if target and target.group(1).strip("\"'") not in (".", "./", ".\\"):
                info["target_dir"] = target.group(1).strip("\"'")
        else:
            info["desk"] = kind
            info["model"] = model.group(1) if model else None
        quoted = [a or b for a, b in _QUOTED.findall(command)]
        info["brief"] = max(quoted, key=len) if quoted else command
        return info
    return None


def _first_line(text: str | None, limit: int = 90) -> str:
    if not text:
        return ""
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line if len(line) <= limit else line[: limit - 1] + "…"


def _basename(path: str | None) -> str:
    if not path:
        return ""
    return re.split(r"[\\/]", path.rstrip("\\/"))[-1]


# ── Veri modeli ──────────────────────────────────────────────────────────────
@dataclass
class Worker:
    id: str
    desk: str
    kind: str  # chief | subagent | lane
    name: str
    session_id: str | None
    started: float
    title: str = ""
    brief: str = ""
    given_by: str = "Yunus"
    cwd: str | None = None
    status: str = WORKING
    current: str = ""
    last_ts: float = 0.0
    ended: float | None = None
    model: str | None = None
    sandbox: str | None = None
    background: bool = False
    tracking: str = "tam"  # tam | sinirli
    tool_use_id: str | None = None
    agent_id: str | None = None
    agent_type: str | None = None
    task_id: str | None = None
    result: str = ""
    tool_count: int = 0
    tokens: dict[str, int] = field(default_factory=dict)
    files_read: list[str] = field(default_factory=list)
    files_written: list[str] = field(default_factory=list)
    activity: deque = field(default_factory=lambda: deque(maxlen=ACTIVITY_LEN))
    codex_rollout: str | None = None
    cmd_model: str | None = None
    pinned_dir: bool = False  # cwd komuttaki -C / cd'den mi geldi (kesin) yoksa oturumdan mı
    turns: int = 0

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "desk": self.desk,
            "kind": self.kind,
            "name": self.name,
            "title": self.title,
            "brief": _first_line(self.brief, 300),
            "given_by": self.given_by,
            "status": self.status,
            "current": self.current,
            "started": self.started,
            "last_ts": self.last_ts,
            "ended": self.ended,
            "model": self.model,
            "sandbox": self.sandbox,
            "background": self.background,
            "tracking": self.tracking,
            "session_id": self.session_id,
            "project": _basename(self.cwd),
            "task_id": self.task_id,
            "tool_count": self.tool_count,
            "tokens": dict(self.tokens),
            "files_written": len(self.files_written),
            "files_read": len(self.files_read),
        }

    def detail(self) -> dict[str, Any]:
        out = self.summary()
        out.update(
            {
                "brief": self.brief,
                "cwd": self.cwd,
                "result": self.result,
                "agent_type": self.agent_type,
                "files_read_list": list(self.files_read),
                "files_written_list": list(self.files_written),
                "activity": list(self.activity),
            }
        )
        return out


@dataclass
class Task:
    id: str
    title: str
    worker_id: str
    created: float
    column: str = COL_RUN
    parent: str | None = None
    updated: float = 0.0
    prompt: str = ""
    result: str = ""
    tests: list[dict[str, Any]] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    counted: bool = False

    def to_dict(self, office: "OfficeState") -> dict[str, Any]:
        kids = [office.tasks[c] for c in self.children if c in office.tasks]
        return {
            "id": self.id,
            "title": self.title,
            "worker_id": self.worker_id,
            "column": self.column,
            "parent": self.parent,
            "created": self.created,
            "updated": self.updated,
            "prompt": _first_line(self.prompt, 400),
            "result": _first_line(self.result, 400),
            "proof": {
                "tests": self.tests[-10:],
                "files_changed": self.files_changed[-30:],
                "delegations": len(kids),
                "reviews": sum(1 for k in kids if office._is_review(k.worker_id)),
                "children_done": sum(1 for k in kids if k.column == COL_DONE),
                "children_failed": sum(1 for k in kids if k.column == COL_FAILED),
            },
            "children": [k.id for k in kids],
        }


class OfficeState:
    """Olaylardan kurulan ofis durumu. Thread-safe: her giriş noktası kilitli."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.workers: dict[str, Worker] = {}
        self.tasks: dict[str, Task] = {}
        self.approvals: dict[str, dict[str, Any]] = {}
        self.quota: dict[str, Any] = {}
        self.desk_stats: dict[str, dict[str, Any]] = {
            d: {"jobs": 0, "done": 0, "failed": 0, "busy_seconds": 0.0, "tokens": 0}
            for d in DESK_IDS
        }
        self._agent_to_worker: dict[str, str] = {}
        self._pending_agents: dict[str, list[str]] = {}  # session -> [worker id] (FIFO)
        self._rollout_to_worker: dict[str, str] = {}
        # tool_use_id → işçi: alt ajan bazen SubagentStart'tan açılıp sonra
        # PreToolUse(Agent) ile sahiplenildiği için kimliği tool id'den türemeyebilir.
        self._tool_to_worker: dict[str, str] = {}
        self._task_seq = 0
        self.events_seen = 0
        self.last_event_ts: float | None = None
        self.version = 0

    def session_active(self, session_id: str, horizon: float = 6 * 3600) -> bool:
        """Bu Claude oturumu açık görünüyor mu: SessionEnd gelmemiş ve son olayı `horizon` içinde.
        Pencere kapatılınca SessionEnd gelmeyebilir — ufuk bu yüzden var."""
        with self._lock:
            w = self.workers.get(self._chief_id(session_id))
            return bool(w and w.status != LEFT and w.last_ts > time.time() - horizon)

    # ── yardımcılar ──
    def _touch(self) -> None:
        self.version += 1

    def _chief_id(self, session_id: str) -> str:
        return f"claude:{session_id}"

    def _chief(self, rec: dict[str, Any]) -> Worker | None:
        sid = rec.get("session_id")
        if not sid:
            return None
        wid = self._chief_id(sid)
        w = self.workers.get(wid)
        if w is None:
            w = Worker(
                id=wid,
                desk="claude",
                kind="chief",
                name="Claude",
                session_id=sid,
                started=rec["ts"],
                cwd=rec.get("cwd"),
                status=IDLE,
                title=f"Oturum · {_basename(rec.get('cwd')) or sid[:8]}",
            )
            self._add_worker(w)
        if rec.get("cwd"):
            w.cwd = rec["cwd"]
        return w

    def _add_worker(self, w: Worker) -> None:
        self.workers[w.id] = w
        if len(self.workers) > MAX_WORKERS:
            finished = sorted(
                (x for x in self.workers.values() if x.status in (DONE, FAILED, LEFT)),
                key=lambda x: x.last_ts,
            )
            for old in finished[: len(self.workers) - MAX_WORKERS]:
                self._forget(old)

    def _forget(self, w: Worker) -> None:
        """İşçiyi ve ona bakan bütün indeksleri sil — uzun çalışmada tablo büyümesin."""
        self.workers.pop(w.id, None)
        if w.agent_id:
            self._agent_to_worker.pop(w.agent_id, None)
        if w.codex_rollout:
            self._rollout_to_worker.pop(w.codex_rollout, None)
        if w.tool_use_id:
            self._tool_to_worker.pop(w.tool_use_id, None)
        for queue in self._pending_agents.values():
            if w.id in queue:
                queue.remove(w.id)

    def _new_task(self, title: str, worker: Worker, ts: float, parent: str | None = None,
                  task_id: str | None = None) -> Task:
        if task_id is None:
            self._task_seq += 1
            task_id = f"G-{self._task_seq:04d}"
        t = Task(id=task_id, title=title or "(başlıksız)", worker_id=worker.id, created=ts,
                 updated=ts, parent=parent)
        self.tasks[t.id] = t
        worker.task_id = t.id
        if parent and parent in self.tasks:
            self.tasks[parent].children.append(t.id)
        if len(self.tasks) > MAX_TASKS:
            for old in sorted(self.tasks.values(), key=lambda x: x.updated)[: len(self.tasks) - MAX_TASKS]:
                self.tasks.pop(old.id, None)
        return t

    def _actor(self, rec: dict[str, Any]) -> Worker | None:
        """Olayı yapan: alt ajan (agent_id varsa) ya da oturumun şefi."""
        aid = rec.get("agent_id")
        if aid:
            wid = self._agent_to_worker.get(aid)
            if wid and wid in self.workers:
                return self.workers[wid]
            # SubagentStart kaçırıldıysa (hook sonradan bağlandı vb.) yerinde aç.
            chief = self._chief(rec)
            w = Worker(
                id=f"sub:{aid}",  # yetim: PreToolUse(Agent) gelirse onu sahiplenir
                desk="subagents",
                kind="subagent",
                name=rec.get("agent_type") or "Alt ajan",
                session_id=rec.get("session_id"),
                started=rec["ts"],
                cwd=rec.get("cwd"),
                agent_id=aid,
                agent_type=rec.get("agent_type"),
                given_by=chief.id if chief else "Yunus",
                title=rec.get("agent_type") or "Alt ajan",
            )
            self._add_worker(w)
            self._agent_to_worker[aid] = w.id
            self._start_job(w)
            return w
        return self._chief(rec)

    def _root_task(self, worker: Worker) -> Task | None:
        """İşçinin bağlı olduğu en üst görev (şefin o turdaki görevi)."""
        t = self.tasks.get(worker.task_id or "")
        seen = 0
        while t is not None and t.parent and t.parent in self.tasks and seen < 10:
            t = self.tasks[t.parent]
            seen += 1
        return t

    def _log(self, w: Worker, ts: float, kind: str, text: str) -> None:
        w.activity.append({"ts": ts, "kind": kind, "text": text})
        w.current = text
        w.last_ts = max(w.last_ts, ts)

    def _start_job(self, w: Worker) -> None:
        self.desk_stats[w.desk]["jobs"] += 1

    def _finish(self, w: Worker, ts: float, ok: bool, result: str = "") -> None:
        if w.status in (DONE, FAILED, LEFT) and w.ended:
            return
        w.status = DONE if ok else FAILED
        w.ended = ts
        w.last_ts = max(w.last_ts, ts)
        if result:
            w.result = result
        st = self.desk_stats[w.desk]
        st["done" if ok else "failed"] += 1
        st["busy_seconds"] += max(0.0, ts - w.started)
        t = self.tasks.get(w.task_id or "")
        if t is not None and w.kind != "chief":
            t.column = COL_DONE if ok else COL_FAILED
            t.updated = ts
            t.result = w.result
        self._log(w, ts, "bitti" if ok else "hata", "Bitti" if ok else "Hata ile bitti")

    def _is_review(self, worker_id: str) -> bool:
        w = self.workers.get(worker_id)
        return bool(w and w.desk == "astra" and (w.sandbox or "") == "read-only")

    @staticmethod
    def _add_file(bucket: list[str], path: str | None) -> None:
        if path and path not in bucket:
            bucket.append(path)
            if len(bucket) > FILES_CAP:
                del bucket[0]

    # ── olay girişi ──
    def apply(self, rec: dict[str, Any]) -> None:
        with self._lock:
            ev = rec.get("event")
            ts = float(rec.get("ts") or time.time())
            rec["ts"] = ts
            self.events_seen += 1
            self.last_event_ts = ts
            handler = getattr(self, f"_on_{ev}", None)
            if handler is not None:
                handler(rec)
                self._touch()

    def _on_SessionStart(self, rec: dict[str, Any]) -> None:
        w = self._chief(rec)
        if w is None:
            return
        if w.status == LEFT:
            w.status, w.ended = IDLE, None
        self._log(w, rec["ts"], "oturum", f"Oturum açıldı ({rec.get('source') or 'yeni'})")

    def _on_UserPromptSubmit(self, rec: dict[str, Any]) -> None:
        w = self._chief(rec)
        if w is None:
            return
        prompt = rec.get("prompt") or ""
        if prompt.lstrip().startswith("<task-notification>"):
            self._on_task_notification(w, rec, prompt)
            return
        w.status, w.ended = WORKING, None
        w.turns += 1
        w.brief = prompt
        w.title = _first_line(prompt, 80) or w.title
        w.given_by = "Yunus"
        t = self._new_task(_first_line(prompt, 80), w, rec["ts"])
        t.prompt = prompt
        self.desk_stats["claude"]["jobs"] += 1
        w.started = rec["ts"] if w.turns == 1 else w.started
        self._log(w, rec["ts"], "gorev", f"Yeni görev: {_first_line(prompt, 70)}")

    def _on_task_notification(self, chief: Worker, rec: dict[str, Any], prompt: str) -> None:
        """Arka plan işi bitti bildirimi: yeni görev DEĞİL, bir bitiş sinyali.

        Bash/Agent'ı arka planda başlatan çağrının tool_use_id'si burada geliyor —
        hook'ların söylemediği bitişi (Bunny/Gemini/OpenCode lane'leri) bu kapatır.
        """
        ts = rec["ts"]
        tool = _NOTIF_TOOL.search(prompt)
        status = (_NOTIF_STATUS.search(prompt) or [None, ""])[1]
        summary = (_NOTIF_SUMMARY.search(prompt) or [None, ""])[1].strip()
        code = _EXIT_CODE.search(summary)
        ok = status == "completed" and (code is None or code.group(1) == "0")
        target = None
        if tool:
            target = self._by_tool(tool.group(1), "lane") or self._by_tool(tool.group(1), "subagent")
        if target is not None and target.status in (WORKING, WAITING, IDLE, LEFT):
            if target.status == LEFT:  # oturum kapanınca "izlenemedi" denmişti; artık biliniyor
                target.status, target.ended = WORKING, None
            target.tracking = "tam"
            self._finish(target, ts, ok, summary)
        # Claude bildirimi işlemek için yeniden çalışıyor: son görevi sürdür.
        chief.status, chief.ended = WORKING, None
        t = self.tasks.get(chief.task_id or "")
        if t is not None and t.column == COL_DONE:
            t.column, t.updated = COL_RUN, ts
        self._log(chief, ts, "bildirim", f"Arka plan işi {'bitti' if ok else 'başarısız'}: {_first_line(summary, 70)}")

    def _on_PreToolUse(self, rec: dict[str, Any]) -> None:
        actor = self._actor(rec)
        if actor is None:
            return
        ts = rec["ts"]
        name = rec.get("tool_name") or "?"
        actor.tool_count += 1
        if actor.status in (IDLE, WAITING):
            actor.status = WORKING
        if actor.kind == "chief":
            t = self.tasks.get(actor.task_id or "")
            if t is not None and t.column == COL_APPROVAL:
                t.column = COL_RUN
        text = self._describe_tool(rec)

        if name in ("Agent", "Task"):
            self._spawn_subagent(actor, rec)
        elif name in ("Bash", "PowerShell"):
            lane = classify_lane(rec.get("command"))
            if lane:
                self._spawn_lane(actor, rec, lane)
        if name in ("Write", "Edit", "NotebookEdit"):
            self._add_file(actor.files_written, rec.get("file_path"))
            root = self._root_task(actor)
            if root is not None:
                self._add_file(root.files_changed, rec.get("file_path"))
        elif name == "Read":
            self._add_file(actor.files_read, rec.get("file_path"))
        self._log(actor, ts, "arac", text)

    def _on_PostToolUse(self, rec: dict[str, Any], failed: bool = False) -> None:
        actor = self._actor(rec)
        if actor is None:
            return
        ts = rec["ts"]
        actor.last_ts = max(actor.last_ts, ts)
        self._clear_approval(rec)
        if actor.status == WAITING:
            actor.status = WORKING
        tuid = rec.get("tool_use_id")
        name = rec.get("tool_name")
        interrupted = bool(rec.get("interrupted"))
        bad = failed or interrupted or bool(rec.get("is_error"))
        # Lane / alt ajan bu çağrıyla mı başlamıştı?
        child = self._by_tool(tuid, "lane")
        if child is not None and child.status == WORKING:
            if child.background and not bad:
                self._log(child, ts, "arac", "Arka planda çalışıyor")
            else:
                self._finish(child, ts, not bad, rec.get("result_tail") or rec.get("error") or "")
        sub = self._by_tool(tuid, "subagent")
        if sub is not None and sub.status in (WORKING, WAITING) and sub.agent_id is None:
            # SubagentStart hiç gelmediyse bitiş buradan. Başarısız ya da biten
            # çağrı bekleme kuyruğundan da çıkar — yoksa sonraki alt ajan ona
            # bağlanırdı (Astra incelemesi). Arka plana atılan ajan kuyrukta kalır.
            launched = (rec.get("result_tail") or "").lstrip().startswith(("Async agent", "Agent is running"))
            if bad or not launched:
                self._unqueue(sub)
                self._finish(sub, ts, not bad, rec.get("result_tail") or rec.get("error") or "")
        if name in ("Bash", "PowerShell") and _TEST_CMD.search(rec.get("command") or ""):
            tail = (rec.get("result_tail") or "") + " " + (rec.get("error") or "")
            if bad or _TEST_FAIL.search(tail):
                verdict = "kirmizi"
            elif _TEST_PASS.search(tail):
                verdict = "yesil"
            else:
                verdict = "bilinmiyor"
            root = self._root_task(actor)
            if root is not None:
                root.tests.append({"ts": ts, "command": _first_line(rec.get("command"), 160),
                                   "verdict": verdict, "by": actor.id})
            self._log(actor, ts, "test", f"Test {verdict}: {_first_line(rec.get('command'), 60)}")
        elif bad:
            self._log(actor, ts, "hata", f"{name} başarısız: {_first_line(rec.get('error') or rec.get('result_tail'), 70)}")

    def _by_tool(self, tuid: str | None, kind: str) -> Worker | None:
        if not tuid:
            return None
        w = self.workers.get(self._tool_to_worker.get(tuid, ""))
        return w if w is not None and w.kind == kind else None

    def _unqueue(self, w: Worker) -> None:
        queue = self._pending_agents.get(w.session_id or "")
        if queue and w.id in queue:
            queue.remove(w.id)

    def _on_PostToolUseFailure(self, rec: dict[str, Any]) -> None:
        self._on_PostToolUse(rec, failed=True)

    def _on_PermissionRequest(self, rec: dict[str, Any]) -> None:
        actor = self._actor(rec)
        if actor is None:
            return
        key = f"{rec.get('session_id')}:{rec.get('agent_id') or '-'}:{rec.get('tool_name')}"
        self.approvals[key] = {
            "id": key,
            "ts": rec["ts"],
            "worker_id": actor.id,
            "tool": rec.get("tool_name"),
            "what": _first_line(rec.get("command") or rec.get("file_path") or rec.get("description")
                                or rec.get("input") or "", 200),
        }
        actor.status = WAITING
        root = self._root_task(actor)
        if root is not None:
            root.column = COL_APPROVAL
            root.updated = rec["ts"]
        self._log(actor, rec["ts"], "onay", f"Onay bekliyor: {rec.get('tool_name')}")

    def _clear_approval(self, rec: dict[str, Any]) -> None:
        key = f"{rec.get('session_id')}:{rec.get('agent_id') or '-'}:{rec.get('tool_name')}"
        if self.approvals.pop(key, None) is not None:
            actor = self._actor(rec)
            root = self._root_task(actor) if actor else None
            if root is not None and root.column == COL_APPROVAL:
                root.column = COL_RUN

    def _on_Notification(self, rec: dict[str, Any]) -> None:
        w = self._chief(rec)
        if w is None:
            return
        ntype = rec.get("notification_type") or ""
        msg = rec.get("message") or ""
        if ntype == "permission_prompt" or "permission" in msg.lower():
            w.status = WAITING
        elif ntype == "idle_prompt":
            w.status = IDLE
        self._log(w, rec["ts"], "bildirim", _first_line(msg, 90) or ntype)

    def _on_SubagentStart(self, rec: dict[str, Any]) -> None:
        aid = rec.get("agent_id")
        sid = rec.get("session_id")
        if not aid or aid in self._agent_to_worker:
            return
        queue = self._pending_agents.get(sid or "", [])
        atype = rec.get("agent_type")
        pick = None
        for wid in queue:  # aynı türden en eski bekleyen Agent çağrısı
            w = self.workers.get(wid)
            if w is not None and (not atype or w.agent_type in (None, atype)):
                pick = w
                break
        if pick is None and queue:
            pick = self.workers.get(queue[0])
        if pick is None:
            self._actor(rec)  # yerinde açar
            return
        queue.remove(pick.id)
        pick.agent_id = aid
        pick.agent_type = atype or pick.agent_type
        self._agent_to_worker[aid] = pick.id
        self._log(pick, rec["ts"], "oturum", "Çalışmaya başladı")

    def _drop_approvals(self, prefix: str) -> None:
        for key in [k for k in self.approvals if k.startswith(prefix)]:
            self.approvals.pop(key, None)

    def _on_SubagentStop(self, rec: dict[str, Any]) -> None:
        aid = rec.get("agent_id")
        self._drop_approvals(f"{rec.get('session_id')}:{aid}:")
        wid = self._agent_to_worker.get(aid or "")
        w = self.workers.get(wid or "")
        if w is None:
            return
        self._unqueue(w)
        self._finish(w, rec["ts"], True, rec.get("last_message") or "")

    def _on_Stop(self, rec: dict[str, Any]) -> None:
        w = self._chief(rec)
        if w is None:
            return
        ts = rec["ts"]
        self._drop_approvals(f"{rec.get('session_id')}:-:")
        w.status = IDLE
        w.result = rec.get("last_message") or w.result
        t = self.tasks.get(w.task_id or "")
        if t is not None and t.column in (COL_RUN, COL_APPROVAL):
            t.column = COL_DONE
            t.updated = ts
            t.result = w.result
            if not t.counted:
                t.counted = True
                self.desk_stats["claude"]["done"] += 1
        self._log(w, ts, "bitti", "Turu bitirdi, mesajını bekliyor")

    def _on_SessionEnd(self, rec: dict[str, Any]) -> None:
        w = self._chief(rec)
        if w is None:
            return
        ts = rec["ts"]
        w.status, w.ended = LEFT, ts
        t = self.tasks.get(w.task_id or "")
        if t is not None and t.column in (COL_RUN, COL_APPROVAL, COL_REVIEW):
            t.column, t.updated = COL_STOPPED, ts
        sid = w.session_id
        for x in self.workers.values():
            if x.session_id == sid and x.kind != "chief" and x.status in (WORKING, WAITING, IDLE):
                if x.codex_rollout:
                    continue  # Codex kendi kaydından bitecek
                x.status, x.ended, x.tracking = LEFT, ts, "sinirli"
                tx = self.tasks.get(x.task_id or "")
                if tx is not None and tx.column in (COL_RUN, COL_REVIEW):
                    tx.column, tx.updated = COL_STOPPED, ts
                self._log(x, ts, "oturum", "Oturum kapandı — bitişi izlenemedi")
        self._pending_agents.pop(sid or "", None)
        self._drop_approvals(f"{sid}:")
        self._log(w, ts, "oturum", f"Oturum kapandı ({rec.get('source') or '-'})")

    # ── iş devri ──
    def _spawn_subagent(self, parent: Worker, rec: dict[str, Any]) -> None:
        tuid = rec.get("tool_use_id") or f"x{self.events_seen}"
        stype = rec.get("subagent_type") or "general-purpose"
        # Hook'lar async: SubagentStart bu PreToolUse'dan ÖNCE yazılmış olabilir
        # (Astra incelemesi). O zaman zaten açılmış yetim işçiyi sahiplen, ikinci
        # bir işçi açma — aynı iş iki kez sayılmasın.
        orphan = next(
            (
                x for x in self.workers.values()
                if x.kind == "subagent" and x.tool_use_id is None and x.agent_id
                and x.session_id == rec.get("session_id") and x.agent_type in (None, stype)
                and abs(x.started - rec["ts"]) <= 10 and x.status in (WORKING, WAITING)
            ),
            None,
        )
        if orphan is not None:
            orphan.tool_use_id = tuid
            orphan.title = rec.get("description") or stype
            orphan.brief = rec.get("prompt") or ""
            orphan.given_by = parent.id
            orphan.model = rec.get("model")
            orphan.name = stype
            self._tool_to_worker[tuid] = orphan.id
            self._new_task(orphan.title, orphan, orphan.started, parent=parent.task_id, task_id=orphan.id)
            self._log(orphan, rec["ts"], "gorev", f"{parent.name} iş verdi: {_first_line(orphan.title, 60)}")
            return
        w = Worker(
            id=f"sub:{tuid}",
            desk="subagents",
            kind="subagent",
            name=stype,
            session_id=rec.get("session_id"),
            started=rec["ts"],
            cwd=rec.get("cwd"),
            title=rec.get("description") or stype,
            brief=rec.get("prompt") or "",
            given_by=parent.id,
            model=rec.get("model"),
            tool_use_id=tuid,
            agent_type=stype,
        )
        self._add_worker(w)
        self._tool_to_worker[tuid] = w.id
        self._pending_agents.setdefault(rec.get("session_id") or "", []).append(w.id)
        self._new_task(w.title, w, rec["ts"], parent=parent.task_id, task_id=w.id)
        self._start_job(w)
        self._log(w, rec["ts"], "gorev", f"{parent.name} iş verdi: {_first_line(w.title, 60)}")

    def _spawn_lane(self, parent: Worker, rec: dict[str, Any], lane: dict[str, Any]) -> None:
        tuid = rec.get("tool_use_id") or f"x{self.events_seen}"
        desk = lane["desk"]
        roster = next(d for d in ROSTER if d["id"] == desk)
        w = Worker(
            id=f"lane:{tuid}",
            desk=desk,
            kind="lane",
            name=roster["name"],
            session_id=rec.get("session_id"),
            started=rec["ts"],
            cwd=lane.get("target_dir") or rec.get("cwd"),
            title=rec.get("description") or _first_line(lane["brief"], 80),
            brief=lane["brief"],
            given_by=parent.id,
            model=lane.get("model") or roster["model"],
            sandbox=lane.get("sandbox"),
            background=bool(rec.get("background")),
            tool_use_id=tuid,
            cmd_model=lane.get("model"),
            pinned_dir=bool(lane.get("target_dir")),
        )
        if w.background and lane["kind"] != "codex":
            w.tracking = "sinirli"  # bitişini söyleyen bir hook yok
        self._add_worker(w)
        self._tool_to_worker[tuid] = w.id
        t = self._new_task(w.title, w, rec["ts"], parent=parent.task_id, task_id=w.id)
        if self._is_review(w.id):
            t.column = COL_REVIEW
        self._start_job(w)
        self._log(w, rec["ts"], "gorev", f"{parent.name} iş verdi")

    @staticmethod
    def _describe_tool(rec: dict[str, Any]) -> str:
        name = rec.get("tool_name") or "?"
        if name in ("Bash", "PowerShell"):
            return rec.get("description") or _first_line(rec.get("command"), 90)
        if name == "Read":
            return f"Okuyor: {_basename(rec.get('file_path'))}"
        if name in ("Write", "Edit", "NotebookEdit"):
            return f"Düzenliyor: {_basename(rec.get('file_path'))}"
        if name in ("Grep", "Glob"):
            return f"Arıyor: {_first_line(rec.get('pattern'), 60)}"
        if name in ("WebFetch", "WebSearch"):
            return f"Web: {_first_line(rec.get('target'), 70)}"
        if name in ("Agent", "Task"):
            return f"Alt ajana iş verdi: {_first_line(rec.get('description'), 60)}"
        if name == "Skill":
            return f"Skill: {rec.get('skill')}"
        return name

    # ── Codex kayıtları ──
    def codex_turn(self, rollout_id: str, ts: float, cwd: str | None, model: str | None,
                   sandbox: str | None) -> bool:
        """Bir `codex exec` oturumu başladı: onu başlatan lane'e bağla.

        Süzgeç (Astra incelemesi, 2026-10-02): komutta açık bir -m varsa model
        uymalı; lane'in dizini komuttan kesin biliniyorsa dizin de uymalı. Uyan
        birden çok lane varsa en eski bağlanır (FIFO) ve bu "tahmini" diye
        yazılır — kesin kimlik gibi sunulmaz. Eşleşme yoksa False döner; izleyici
        lane'in hook olayı gecikmiş olabileceği için kısa süre yeniden dener.
        """
        with self._lock:
            if rollout_id in self._rollout_to_worker:
                return True
            want = "astra" if model and "astra" in model.lower() else "sol"
            candidates: list[Worker] = []
            for w in self.workers.values():
                if w.kind != "lane" or w.desk not in ("sol", "astra") or w.codex_rollout:
                    continue
                if not (w.started - 5 <= ts <= w.started + CODEX_LINK_WINDOW_S):
                    continue
                if w.cmd_model and model and w.cmd_model.lower() != model.lower():
                    continue
                if w.pinned_dir and cwd and not _same_dir(cwd, w.cwd):
                    continue
                candidates.append(w)
            if not candidates:
                return False
            # Dizini de uyan önce, sonra en eski.
            candidates.sort(key=lambda w: (not _same_dir(cwd, w.cwd), w.started))
            best = candidates[0]
            best.codex_rollout = rollout_id
            best.model = model or best.model
            best.sandbox = sandbox or best.sandbox
            if best.desk != want and model:
                self._move_desk(best, want)  # -m yoktu; gerçek model başka masanın
            self._rollout_to_worker[rollout_id] = best.id
            t = self.tasks.get(best.task_id or "")
            if t is not None and self._is_review(best.id) and t.column == COL_RUN:
                t.column = COL_REVIEW
            guess = f" · tahmini eşleşme, {len(candidates)} aday" if len(candidates) > 1 else ""
            self._log(best, ts, "oturum", f"Codex oturumu bağlandı ({best.model}, {best.sandbox or '-'}){guess}")
            self._touch()
            return True

    def _move_desk(self, w: Worker, desk: str) -> None:
        """İşçiyi başka masaya taşı — bütün sayaç katkılarıyla birlikte."""
        old, new = self.desk_stats[w.desk], self.desk_stats[desk]
        old["jobs"] -= 1
        new["jobs"] += 1
        if w.status in (DONE, FAILED) and w.ended:
            key = "done" if w.status == DONE else "failed"
            busy = max(0.0, w.ended - w.started)
            old[key] -= 1
            new[key] += 1
            old["busy_seconds"] -= busy
            new["busy_seconds"] += busy
        tok = w.tokens.get("total", 0)
        old["tokens"] -= tok
        new["tokens"] += tok
        w.desk = desk
        w.name = next(d["name"] for d in ROSTER if d["id"] == desk)

    def codex_event(self, rollout_id: str, ts: float, kind: str, data: dict[str, Any]) -> None:
        with self._lock:
            if kind == "quota":
                self.quota["codex"] = data
                self._touch()
                return
            w = self.workers.get(self._rollout_to_worker.get(rollout_id, ""))
            if w is None:
                return
            if kind == "tokens":
                prev = w.tokens.get("total", 0)
                w.tokens = data
                self.desk_stats[w.desk]["tokens"] += max(0, data.get("total", 0) - prev)
                w.last_ts = max(w.last_ts, ts)
            elif kind == "command":
                w.tool_count += 1
                if w.status != WORKING:
                    w.last_ts = max(w.last_ts, ts)
                else:
                    self._log(w, ts, "arac", _first_line(mask(data.get("cmd")), 90))
            elif kind == "done":
                self._finish(w, ts, True, mask(data.get("message")))
            self._touch()

    # ── çıktı ──
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            active = [w for w in self.workers.values() if w.status in (WORKING, WAITING, IDLE)]
            finished = sorted(
                (w for w in self.workers.values() if w.status not in (WORKING, WAITING, IDLE)),
                key=lambda w: w.last_ts,
                reverse=True,
            )[:SNAPSHOT_FINISHED_WORKERS]
            desks = []
            for d in ROSTER:
                on_desk = [w for w in active if w.desk == d["id"]]
                desks.append(
                    {
                        **d,
                        "status": _desk_status(on_desk),
                        "workers": [w.id for w in on_desk],
                        "stats": dict(self.desk_stats[d["id"]]),
                    }
                )
            tasks = sorted(self.tasks.values(), key=lambda t: t.updated, reverse=True)[:SNAPSHOT_TASKS]
            return {
                "now": time.time(),
                "version": self.version,
                "desks": desks,
                "workers": [w.summary() for w in active + finished],
                "tasks": [t.to_dict(self) for t in tasks],
                "approvals": sorted(self.approvals.values(), key=lambda a: a["ts"]),
                "quota": dict(self.quota),
                "tracking": {
                    "events_seen": self.events_seen,
                    "last_event_ts": self.last_event_ts,
                },
            }

    def worker_detail(self, worker_id: str) -> dict[str, Any] | None:
        with self._lock:
            w = self.workers.get(worker_id)
            if w is None:
                return None
            out = w.detail()
            out["task"] = self.tasks[w.task_id].to_dict(self) if w.task_id in self.tasks else None
            out["delegated"] = [
                x.summary() for x in self.workers.values() if x.given_by == w.id
            ][-30:]
            return out

    def desk_detail(self, desk_id: str) -> dict[str, Any] | None:
        with self._lock:
            d = next((x for x in ROSTER if x["id"] == desk_id), None)
            if d is None:
                return None
            mine = sorted((w for w in self.workers.values() if w.desk == desk_id),
                          key=lambda w: w.last_ts, reverse=True)
            return {
                **d,
                "stats": dict(self.desk_stats[desk_id]),
                "active": [w.summary() for w in mine if w.status in (WORKING, WAITING, IDLE)],
                "history": [w.summary() for w in mine if w.status not in (WORKING, WAITING, IDLE)][:30],
            }


def _desk_status(on_desk: list[Worker]) -> str:
    if any(w.status == WAITING for w in on_desk):
        return WAITING
    if any(w.status == WORKING for w in on_desk):
        return WORKING
    return IDLE


def _same_dir(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    def norm(path: str) -> str:
        path = path.strip().strip("\"'")
        msys = re.match(r"^/([a-zA-Z])(/|$)(.*)", path)  # Git Bash: /c/Users → C:/Users
        if msys:
            path = f"{msys.group(1)}:/{msys.group(3)}"
        return os.path.normcase(os.path.normpath(path.replace("/", os.sep)))

    return norm(a) == norm(b)


# ── Dosya izleme ─────────────────────────────────────────────────────────────
class _Tail:
    """Bir JSONL dosyasının yalnız yeni satırlarını okur.

    Döndürmeyi dosya KİMLİĞİNDEN (st_ino) tanır, boyuttan değil: aynı boyda yeni
    bir dosya da yakalanır. Ofset, stat'taki boyuta değil gerçekten okunan bayta
    göre ilerler — stat ile open arasında dosya değişirse kayma olmaz (Astra
    incelemesi, 2026-10-02).
    """

    def __init__(self, path: Path, start_back: int | None = None) -> None:
        self.path = path
        self.offset = 0
        self.partial = b""
        self.ident: tuple[int, int] | None = None
        self._start_back = start_back
        self._started = False

    def read(self) -> list[dict[str, Any]]:
        try:
            st = self.path.stat()
        except OSError:
            return []
        ident = (st.st_dev, st.st_ino)
        skip_first = False
        if not self._started:
            self._started = True
            self.ident = ident
            if self._start_back is not None and st.st_size > self._start_back:
                self.offset = st.st_size - self._start_back
                skip_first = True
        elif ident != self.ident or st.st_size < self.offset:
            # Döndürüldü: yeni dosyayı baştan oku. (Eski dosyanın son birkaç
            # satırı kaçabilir — hook 20 MB'ta bir döndürüyor, kabul edilen kayıp.)
            self.ident, self.offset, self.partial = ident, 0, b""
        if st.st_size == self.offset:
            return []
        try:
            with open(self.path, "rb") as f:
                f.seek(self.offset)
                chunk = f.read(max(0, st.st_size - self.offset) + 65536)
        except OSError:
            return []
        self.offset += len(chunk)
        data = self.partial + chunk
        lines = data.split(b"\n")
        self.partial = lines.pop()
        if skip_first and lines:
            lines.pop(0)
        out = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line.decode("utf-8", "replace")))
            except ValueError:
                continue
        return out


def _iso_ts(value: str | None) -> float:
    if not value:
        return time.time()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return time.time()


class OfficeWatcher:
    """Olay dosyasını ve Codex kayıtlarını izler, değişince `on_change` çağırır."""

    def __init__(
        self,
        state: OfficeState,
        on_change: Callable[[dict[str, Any]], None] | None = None,
        events_path: Path = EVENTS_PATH,
        codex_dir: Path = CODEX_SESSIONS,
        history_bytes: int = 4 * 1024 * 1024,
        interval: float = 1.0,
    ) -> None:
        self.state = state
        self.on_change = on_change
        self.events = _Tail(events_path, start_back=history_bytes)
        self.codex_dir = codex_dir
        self.interval = interval
        self._codex: dict[Path, _Tail] = {}
        self._codex_meta: dict[Path, dict[str, Any]] = {}
        self._last_scan = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_sent = -1
        self._born = time.time()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="airon-ofis", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll()
            except Exception:  # izleyici asla ölmemeli
                logger.debug("Ofis izleyici turu başarısız", exc_info=True)
            self._stop.wait(self.interval)

    def poll(self) -> None:
        # Hook'lar async: aynı anda biten iki hook satırları ters sırada yazabilir.
        # Bir tur içindeki partiyi olay zamanına göre sırala (kararlı sıralama).
        batch = [r for r in self.events.read() if isinstance(r, dict)]
        batch.sort(key=lambda r: float(r.get("ts") or 0))
        for rec in batch:
            self.state.apply(rec)
        now = time.time()
        if now - self._last_scan >= 2.0:
            self._last_scan = now
            self._scan_codex(now)
        for path, tail in list(self._codex.items()):
            for rec in tail.read():
                self._codex_record(path, rec)
        self._retry_codex_links(now)
        if self.on_change and self.state.version != self._last_sent:
            self._last_sent = self.state.version
            self.on_change(self.state.snapshot())

    def _scan_codex(self, now: float) -> None:
        # Klasörler yerel tarihe göre; gece yarısını kaçırmamak için dün de bakılır.
        horizon = self._born - 6 * 3600
        for day in (datetime.now(), datetime.now() - timedelta(days=1)):
            folder = self.codex_dir / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}"
            try:
                entries = list(folder.glob("rollout-*.jsonl"))
            except OSError:
                continue
            for path in entries:
                if path in self._codex:
                    continue
                try:
                    if path.stat().st_mtime < horizon:
                        continue
                except OSError:
                    continue
                self._codex[path] = _Tail(path)
        # Bir gündür yazılmayan kayıtları bırak.
        for path in [p for p in self._codex if not p.exists() or p.stat().st_mtime < now - 86400]:
            self._codex.pop(path, None)
            self._codex_meta.pop(path, None)

    def _try_link(self, path: Path, meta: dict[str, Any]) -> None:
        pending = meta.get("pending")
        if not pending:
            return
        rid = meta.get("id") or path.stem
        if self.state.codex_turn(rid, *pending):
            meta["linked"], meta["pending"] = True, None
            # Bağlanmadan önce gelen token ve bitiş kaybolmasın.
            if meta.get("last_tokens"):
                self.state.codex_event(rid, meta["last_tokens"][0], "tokens", meta.pop("last_tokens")[1])
            if meta.get("done"):
                ts, done = meta.pop("done")
                self.state.codex_event(rid, ts, "done", done)

    def _retry_codex_links(self, now: float) -> None:
        for path, meta in list(self._codex_meta.items()):
            pending = meta.get("pending")
            if not pending:
                continue
            if now - pending[0] > CODEX_LINK_WINDOW_S + 30:
                meta["pending"] = None  # lane'i olmayan bir exec (elle çalıştırılmış) — bırak
                continue
            self._try_link(path, meta)

    def _codex_record(self, path: Path, rec: dict[str, Any]) -> None:
        payload = rec.get("payload") or {}
        rtype = rec.get("type")
        ptype = payload.get("type") if isinstance(payload, dict) else None
        ts = _iso_ts(rec.get("timestamp"))
        meta = self._codex_meta.setdefault(path, {})
        rid = meta.get("id") or path.stem
        if rtype == "session_meta":
            meta.update(id=payload.get("id") or rid, cwd=payload.get("cwd"),
                        exec=payload.get("originator") == "codex_exec")
            return
        if rtype == "turn_context":
            if meta.get("linked") or meta.get("pending") or not meta.get("exec"):
                return  # etkileşimli Codex oturumları lane değil
            sandbox = (payload.get("sandbox_policy") or {}).get("type")
            meta["pending"] = (ts, payload.get("cwd") or meta.get("cwd"), payload.get("model"), sandbox)
            self._try_link(path, meta)
            return
        if rtype == "event_msg" and ptype == "token_count":
            info = payload.get("info") or {}
            total = info.get("total_token_usage") or {}
            tokens_data = {
                "input": int(total.get("input_tokens") or 0),
                "cached": int(total.get("cached_input_tokens") or 0),
                "output": int(total.get("output_tokens") or 0),
                "reasoning": int(total.get("reasoning_output_tokens") or 0),
                "total": int(total.get("total_tokens") or 0),
            }
            if meta.get("linked"):
                self.state.codex_event(rid, ts, "tokens", tokens_data)
            else:
                meta["last_tokens"] = (ts, tokens_data)
            limits = payload.get("rate_limits") or {}
            if limits:
                self.state.codex_event(rid, ts, "quota", {
                    "ts": ts,
                    "plan": limits.get("plan_type"),
                    "primary": limits.get("primary"),
                    "secondary": limits.get("secondary"),
                })
        elif rtype == "event_msg" and ptype == "task_complete":
            done = {"message": payload.get("last_agent_message")}
            if meta.get("linked"):
                self.state.codex_event(rid, ts, "done", done)
            else:
                meta["done"] = (ts, done)
        elif rtype == "response_item" and ptype in ("custom_tool_call", "function_call"):
            text = payload.get("input") or payload.get("arguments") or ""
            cmds = _CODEX_CMD.findall(text) if isinstance(text, str) else []
            for cmd in cmds[:3] or [payload.get("name") or "araç"]:
                self.state.codex_event(rid, ts, "command", {"cmd": cmd.replace('\\"', '"')})


office = OfficeState()
