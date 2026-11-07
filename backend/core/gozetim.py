"""Gözetim — bütün Claude Code oturumları tek ekranda (2026-11-04).

Atalay's Terminal'in "orbit HUD"undan alınan fikir, Chiron'un kendi veri hattıyla:

* Oturum, alt ajan, araç, onay, araştırma, dosya ısısı → `ofis.py` (hook olayları).
* Token, bağlam doluluğu, model, maliyet → oturumun Claude Code kaydı
  (`transcript_path`, hook olayı veriyor). Kayıt yalnız OKUNUR, artımlı: her dosyanın
  okunan ofseti tutulur, yeni baytlar ayrıştırılır.
* Kaçak süreçler → psutil. Sahibi ölmüş (yetim) geliştirici süreci bir çekirdeği
  2 dakikadır yakıyorsa ya da port tutuyorsa listelenir. Sonlandırma yalnız kullanıcının
  tıklamasıyla, aynı pid + aynı başlangıç zamanı doğrulanarak (pid yeniden kullanılmış
  olabilir) ve bütün alt süreç ağacıyla (TaskStop alt süreçleri bırakıyordu).

Dürüstlük (Bilinen-Tuzaklar § Arayüzde dürüstlük): maliyet "API liste fiyatıyla eşdeğer"
bir tahmindir — abonelikte gerçekte ödenen bu değil. Fiyatı bilinmeyen model "?" döner,
uydurulmaz. Sayılar yalnız Chiron'un gördüğü oturumlardan gelir.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.core import ofis as ofis_mod

logger = logging.getLogger("chiron.gozetim")

# ── Fiyatlar ($ / 1M token) ─────────────────────────────────────────────────
# Kaynak: claude-api referansı (2026-10-06 önbelleği). cache_read verilmeyenlerde girdi × 0.1.
# Önbelleğe yazma: 5 dk TTL girdi × 1.25, 1 sa TTL girdi × 2 (Anthropic'in genel çarpanları).
PRICES: dict[str, dict[str, float]] = {
    "claude-fable-5-1": {"in": 10.0, "out": 50.0, "cr": 0.25},
    "claude-fable-5": {"in": 10.0, "out": 50.0},
    "claude-mythos-5-1": {"in": 10.0, "out": 50.0, "cr": 0.25},
    "claude-opus-5-5": {"in": 4.0, "out": 20.0, "cr": 0.20},
    "claude-opus-5": {"in": 5.0, "out": 25.0},
    "claude-opus-4-8": {"in": 5.0, "out": 25.0},
    "claude-opus-4-7": {"in": 5.0, "out": 25.0},
    "claude-opus-4-6": {"in": 5.0, "out": 25.0},
    "claude-sonnet-5-5": {"in": 2.0, "out": 10.0, "cr": 0.20},
    "claude-sonnet-5": {"in": 2.0, "out": 10.0},
    "claude-sonnet-4-6": {"in": 3.0, "out": 15.0},
    "claude-haiku-5-5": {"in": 0.10, "out": 0.50},
    "claude-haiku-4-5": {"in": 1.0, "out": 5.0},
}
# Uzundan kısaya: "claude-opus-5-5" "claude-opus-5"ten önce eşleşsin.
_PRICE_KEYS = sorted(PRICES, key=len, reverse=True)
CONTEXT_WINDOW = {"claude-haiku-4-5": 200_000}
DEFAULT_WINDOW = 1_000_000


def price_for(model: str | None) -> dict[str, float] | None:
    if not model:
        return None
    m = model.lower()
    for key in _PRICE_KEYS:
        if m.startswith(key):
            p = dict(PRICES[key])
            p.setdefault("cr", p["in"] * 0.1)
            return p
    return None


def window_for(model: str | None) -> int:
    m = (model or "").lower()
    for key, size in CONTEXT_WINDOW.items():
        if m.startswith(key):
            return size
    return DEFAULT_WINDOW


def short_model(model: str | None) -> str:
    """claude-opus-5-5 → opus 5.5"""
    if not model:
        return "?"
    m = model.lower().split("[")[0]
    for fam in ("fable", "mythos", "opus", "sonnet", "haiku"):
        if f"claude-{fam}-" in m:
            ver = m.split(f"claude-{fam}-", 1)[1].split("-")
            ver = [v for v in ver if v.isdigit() and len(v) <= 2][:2]
            return f"{fam} {'.'.join(ver)}".strip()
    return m


def usage_cost(usage: dict[str, Any], p: dict[str, float] | None) -> float | None:
    if p is None:
        return None
    cc = usage.get("cache_creation") or {}
    w1h = int(cc.get("ephemeral_1h_input_tokens") or 0)
    w5m = int(cc.get("ephemeral_5m_input_tokens") or 0)
    wtot = int(usage.get("cache_creation_input_tokens") or 0)
    if w1h + w5m == 0:
        w5m = wtot
    return (
        int(usage.get("input_tokens") or 0) * p["in"]
        + w5m * p["in"] * 1.25
        + w1h * p["in"] * 2.0
        + int(usage.get("cache_read_input_tokens") or 0) * p["cr"]
        + int(usage.get("output_tokens") or 0) * p["out"]
    ) / 1_000_000


# ── Kayıt sayacı ─────────────────────────────────────────────────────────────
@dataclass
class Meter:
    """Tek bir Claude Code kaydının artımlı özeti."""

    offset: int = 0
    carry: bytes = b""
    seen: set = field(default_factory=set)
    seen_order: deque = field(default_factory=lambda: deque(maxlen=20000))
    tokens: dict[str, int] = field(default_factory=lambda: {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0})
    cost: float = 0.0
    cost_known: bool = True
    by_model: dict[str, float] = field(default_factory=dict)
    ctx_used: int = 0
    model: str | None = None
    effort: str | None = None
    last_ts: float = 0.0
    # (ts, toplam token, maliyet, gün, girdi+yazma+okuma, okuma, kazanç) — oranlar ve bugünün toplamı için
    recent: deque = field(default_factory=lambda: deque(maxlen=5000))


def _iso(ts: str | None) -> float:
    if not ts:
        return time.time()
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return time.time()


class TranscriptMeters:
    MAX_FIRST_READ = 64 * 1024 * 1024  # 64 MB'tan büyük kaydın yalnız sonu okunur

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._meters: dict[str, Meter] = {}

    def read(self, path: str | None) -> Meter | None:
        if not path:
            return None
        try:
            size = os.path.getsize(path)
        except OSError:
            return self._meters.get(path)
        with self._lock:
            m = self._meters.get(path)
            if m is None:
                m = self._meters[path] = Meter()
                if size > self.MAX_FIRST_READ:
                    m.offset = size - self.MAX_FIRST_READ
            if size < m.offset:  # dosya küçüldü/yenilendi: baştan
                self._meters[path] = m = Meter()
            if size == m.offset:
                return m
            try:
                with open(path, "rb") as f:
                    f.seek(m.offset)
                    chunk = f.read(size - m.offset)
            except OSError:
                return m
            m.offset += len(chunk)
            data = m.carry + chunk
            lines = data.split(b"\n")
            m.carry = lines.pop()  # yarım son satır
            for raw in lines:
                if b'"usage"' not in raw:
                    continue
                self._ingest(m, raw)
            return m

    @staticmethod
    def _ingest(m: Meter, raw: bytes) -> None:
        try:
            rec = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return
        if rec.get("type") != "assistant" or rec.get("isSidechain"):
            return
        msg = rec.get("message") or {}
        usage = msg.get("usage")
        if not isinstance(usage, dict):
            return
        key = msg.get("id") or rec.get("requestId")
        if key:
            # Claude Code bir yanıtı içerik bloğu başına ayrı satıra yazıyor, usage hepsinde aynı.
            if key in m.seen:
                return
            if len(m.seen_order) == m.seen_order.maxlen:
                m.seen.discard(m.seen_order[0])
            m.seen.add(key)
            m.seen_order.append(key)
        model = msg.get("model") or m.model
        if model == "<synthetic>":
            return
        ts = _iso(rec.get("timestamp"))
        inp = int(usage.get("input_tokens") or 0)
        cw = int(usage.get("cache_creation_input_tokens") or 0)
        cr = int(usage.get("cache_read_input_tokens") or 0)
        out = int(usage.get("output_tokens") or 0)
        m.tokens["input"] += inp
        m.tokens["cache_write"] += cw
        m.tokens["cache_read"] += cr
        m.tokens["output"] += out
        p = price_for(model)
        c = usage_cost(usage, p)
        saved = 0.0
        if c is None:
            m.cost_known = False
            c = 0.0
        else:
            saved = cr * (p["in"] - p["cr"]) / 1_000_000
            name = short_model(model)
            m.by_model[name] = m.by_model.get(name, 0.0) + c
        m.cost += c
        m.ctx_used = inp + cw + cr
        m.model = model
        if rec.get("effort"):
            m.effort = str(rec.get("effort"))
        m.last_ts = max(m.last_ts, ts)
        m.recent.append((ts, inp + cw + cr + out, c, datetime.fromtimestamp(ts).strftime("%Y-%m-%d"),
                         inp + cw + cr, cr, saved, short_model(model)))


meters = TranscriptMeters()


def last_reply(path: str | None, tail_bytes: int = 4 * 1024 * 1024) -> str:
    """Claude'un son cevabı: kullanıcının son yazdığı şeyden sonra söylediği bütün metin."""
    if not path:
        return ""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.seek(max(0, size - tail_bytes))
            data = f.read()
    except OSError:
        return ""
    lines = data.split(b"\n")
    if size > tail_bytes:
        lines = lines[1:]
    parts: list[str] = []
    for raw in lines:
        try:
            rec = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            continue
        if rec.get("isSidechain"):
            continue
        t = rec.get("type")
        content = (rec.get("message") or {}).get("content")
        if t == "user":
            # Araç sonucu kullanıcı satırı gibi yazılıyor ama cevabın parçası; yalnız gerçek yazı cevabı keser.
            if isinstance(content, str) or (
                isinstance(content, list) and any(isinstance(c, dict) and c.get("type") == "text" for c in content)
            ):
                parts = []
        elif t == "assistant" and isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text" and c.get("text"):
                    parts.append(c["text"])
    return "\n\n".join(parts).strip()


# ── Kaçak süreçler ───────────────────────────────────────────────────────────
DEV_NAMES = {
    "node.exe", "python.exe", "pythonw.exe", "deno.exe", "bun.exe", "esbuild.exe", "ruby.exe",
    "java.exe", "dotnet.exe", "go.exe", "cargo.exe", "php.exe", "uvicorn.exe", "npm.exe",
}
# Derleme bitince arka planda bekleyip boşta kalınca kendi kapananlar: sahipsiz ve port tutmaları normal,
# Sonlandır uyarısı her derlemeden sonra çıkıyordu (2026-11-07). CPU yakarlarsa yine listelenir.
BUILD_DAEMONS = (
    "org.gradle.launcher.daemon.bootstrap.GradleDaemon",
    "org.jetbrains.kotlin.daemon.KotlinCompileDaemon",
)
CPU_LINE = 50.0  # bir çekirdeğin %50'si
CPU_HOLD_S = 120.0
SCAN_EVERY_S = 5.0


def _is_build_daemon(proc: Any) -> bool:
    try:
        return any(marker in part for part in proc.cmdline() for marker in BUILD_DAEMONS)
    except Exception:
        return False


class RunawayWatch:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._procs: dict[int, Any] = {}
        self._over_since: dict[int, float] = {}
        self._items: list[dict[str, Any]] = []
        self._listeners: list[dict[str, Any]] = []
        self._last_scan = 0.0
        self._ok = True

    def _protected(self, psutil: Any) -> set[int]:
        """Chiron'un kendisi, ataları ve çocukları asla aday değil."""
        keep: set[int] = set()
        try:
            me = psutil.Process(os.getpid())
            keep.add(me.pid)
            keep.update(p.pid for p in me.parents())
            keep.update(p.pid for p in me.children(recursive=True))
        except Exception:
            pass
        return keep

    def items(self) -> list[dict[str, Any]]:
        now = time.time()
        with self._lock:
            if now - self._last_scan >= SCAN_EVERY_S and self._ok:
                self._last_scan = now
                try:
                    self._scan(now)
                except Exception:
                    logger.exception("Kaçak süreç taraması başarısız")
            return [dict(x) for x in self._items]

    def _scan(self, now: float) -> None:
        try:
            import psutil
        except ImportError:
            self._ok = False
            return
        me_user = None
        try:
            me_user = psutil.Process(os.getpid()).username()
        except Exception:
            pass
        keep = self._protected(psutil)
        alive: set[int] = set()
        found: list[dict[str, Any]] = []
        listeners: list[dict[str, Any]] = []
        for p in psutil.process_iter(["pid", "name", "ppid", "create_time"]):
            info = p.info
            name = (info.get("name") or "").lower()
            if name not in DEV_NAMES or info["pid"] in keep:
                continue
            pid = info["pid"]
            alive.add(pid)
            proc = self._procs.get(pid)
            if proc is None or proc.create_time() != info["create_time"]:
                proc = self._procs[pid] = p
                try:
                    proc.cpu_percent(None)  # ilk ölçüm hep 0 — taban
                except Exception:
                    continue
                continue
            try:
                if me_user and proc.username() != me_user:
                    continue
                ports: list[int] = []
                try:
                    ports = sorted({c.laddr.port for c in proc.net_connections(kind="inet")
                                    if c.status == psutil.CONN_LISTEN and c.laddr})
                except Exception:
                    ports = []
                build_daemon = bool(ports) and _is_build_daemon(proc)
                if ports and not build_daemon:
                    # Dev sunucusu (sahipli ya da değil): yörüngede oturumunun uydusu olur (orbit_view).
                    listeners.append({"pid": pid, "name": info.get("name"), "ports": ports,
                                      "cwd": _safe(lambda: proc.cwd())})
                ppid = info.get("ppid") or 0
                parent_alive = False
                if ppid and psutil.pid_exists(ppid):
                    try:
                        parent_alive = psutil.Process(ppid).create_time() <= info["create_time"]
                    except Exception:
                        parent_alive = False
                if parent_alive:
                    self._over_since.pop(pid, None)
                    continue
                cpu = proc.cpu_percent(None)
                if cpu >= CPU_LINE:
                    self._over_since.setdefault(pid, now)
                else:
                    self._over_since.pop(pid, None)
                burning = pid in self._over_since and now - self._over_since[pid] >= CPU_HOLD_S
                if not burning and (not ports or build_daemon):
                    continue
                try:
                    cmd = " ".join(proc.cmdline())
                except Exception:
                    cmd = name
                found.append({
                    "pid": pid,
                    "name": info.get("name"),
                    "create_time": info["create_time"],
                    "cpu": round(cpu, 1),
                    "since": self._over_since.get(pid),
                    "ports": ports,
                    "kind": "yakiyor" if burning else "sahipsiz_sunucu",
                    "command": ofis_mod.mask(cmd)[:300],
                    "cwd": _safe(lambda: proc.cwd()),
                })
            except Exception:
                continue
        for pid in list(self._procs):
            if pid not in alive:
                self._procs.pop(pid, None)
                self._over_since.pop(pid, None)
        found.sort(key=lambda x: (x["kind"] != "yakiyor", -x["cpu"]))
        self._items = found
        self._listeners = listeners

    def listeners(self) -> list[dict[str, Any]]:
        """Port dinleyen geliştirme süreçleri (son tarama). `items()` taramayı tetikler."""
        self.items()
        with self._lock:
            return [dict(x) for x in self._listeners]

    def end(self, pid: int, create_time: float) -> tuple[bool, str]:
        try:
            import psutil
        except ImportError:
            return False, "psutil yok"
        with self._lock:
            listed = next((x for x in self._items if x["pid"] == pid), None)
        if listed is None:
            return False, "Bu süreç listede değil (bitmiş ya da artık kaçak sayılmıyor)."
        try:
            proc = psutil.Process(pid)
            if abs(proc.create_time() - create_time) > 0.01 or abs(listed["create_time"] - create_time) > 0.01:
                return False, "Aynı pid'de başka bir süreç var — dokunulmadı."
            tree = proc.children(recursive=True)
            tree.reverse()  # en derinden başla (npm'in çocuk sunucusu da gitsin)
            victims = tree + [proc]
            for v in victims:
                try:
                    v.terminate()
                except psutil.NoSuchProcess:
                    pass
            _, still = psutil.wait_procs(victims, timeout=2)
            for v in still:
                try:
                    v.kill()
                except psutil.NoSuchProcess:
                    pass
        except psutil.NoSuchProcess:
            pass
        except psutil.AccessDenied:
            return False, "Erişim engellendi."
        with self._lock:
            self._items = [x for x in self._items if x["pid"] != pid]
            self._over_since.pop(pid, None)
        logger.info("Kaçak süreç sonlandırıldı: pid=%s %s", pid, listed.get("name"))
        return True, ""


def _safe(fn: Any) -> Any:
    try:
        return fn()
    except Exception:
        return None


runaways = RunawayWatch()


# ── Görünüm ──────────────────────────────────────────────────────────────────
ACTIVE = (ofis_mod.WORKING, ofis_mod.WAITING, ofis_mod.IDLE)
LANE_WINDOW_S = 30 * 60
SUB_RECENT_S = 15 * 60
STALE_S = 6 * 3600


def _project(w: Any) -> str:
    return ofis_mod._basename(w.cwd) or (w.session_id or "")[:8]


def view(state: Any | None = None) -> dict[str, Any]:
    office = state or ofis_mod.office
    now = time.time()
    today = datetime.fromtimestamp(now).strftime("%Y-%m-%d")
    with office._lock:
        chiefs = [w for w in office.workers.values() if w.kind == "chief"]
        # Pencere kapatılınca SessionEnd gelmeyebilir: 6 saattir sesi çıkmayan oturum canlı sayılmaz
        # (OfficeState.session_active ile aynı ufuk).
        live = [w for w in chiefs if w.status in ACTIVE and (w.last_ts or w.started) > now - STALE_S]
        subs = [w for w in office.workers.values() if w.kind in ("subagent", "lane")]
        approvals = sorted(office.approvals.values(), key=lambda a: a["ts"])
        names = {w.id: _project(w) for w in chiefs}
        sessions = []
        for w in sorted(live, key=lambda x: x.started):
            mine = [s for s in subs if s.given_by == w.id
                    and (s.status in ACTIVE or (s.ended or 0) > now - SUB_RECENT_S)]
            sessions.append({
                "id": w.id,
                "session_id": w.session_id,
                "project": _project(w),
                "cwd": w.cwd,
                "title": w.title,
                "status": w.status,
                "current": w.current,
                "started": w.started,
                "last_ts": w.last_ts,
                "tool_count": w.tool_count,
                "files_written": list(w.files_written[-12:]),
                "files_written_count": len(w.files_written),
                "transcript_path": w.transcript_path,
                "marks": [[ts, cat] for ts, cat in w.marks if ts > now - LANE_WINDOW_S],
                "subagents": [{
                    "id": s.id, "name": s.name, "title": s.title, "status": s.status,
                    "tool_count": s.tool_count, "started": s.started, "ended": s.ended,
                    "current": s.current, "kind": s.kind,
                    "marks": [[ts, cat] for ts, cat in s.marks if ts > now - LANE_WINDOW_S],
                } for s in sorted(mine, key=lambda x: x.started)],
                "approvals": [a for a in approvals if a["worker_id"] == w.id
                              or office.workers.get(a["worker_id"], w).given_by == w.id],
            })
        log = []
        for w in live + [s for s in subs if s.status in ACTIVE]:
            owner = names.get(w.id) or names.get(w.given_by) or _project(w)
            for a in list(w.activity)[-25:]:
                log.append({**a, "who": owner, "worker": w.name if w.kind != "chief" else ""})
        log.sort(key=lambda a: a["ts"], reverse=True)
        tool_mix = dict(office.tool_mix) if office.radar_day == today else {}
        research = [{**r, "project": names.get(r["session"], "")} for r in reversed(office.research)][:14]
        heat = office.file_heat if office.radar_day == today else {}
        files = sorted(heat.items(), key=lambda kv: kv[1]["writes"] * 2 + kv[1]["reads"], reverse=True)[:12]
        files_out = [{
            "path": p, "reads": h["reads"], "writes": h["writes"],
            "writers": [names.get(x, x) for x in h["writers"]],
            "collision": len(h["writers"]) > 1,
        } for p, h in files]
        today_paths = {w.transcript_path for w in chiefs
                       if w.transcript_path and datetime.fromtimestamp(w.last_ts or 0).strftime("%Y-%m-%d") == today}
        all_marks = [ts for w in office.workers.values() for ts, cat in w.marks
                     if ts > now - 300 and cat not in ("onay", "hata")]
        subs_running = sum(1 for s in subs if s.status in (ofis_mod.WORKING, ofis_mod.WAITING))
        subs_today = sum(1 for s in subs if datetime.fromtimestamp(s.started).strftime("%Y-%m-%d") == today)
        last_event = office.last_event_ts

        def owner_of(worker_id: str) -> str:
            w = office.workers.get(worker_id)
            return names.get(worker_id) or (names.get(w.given_by, "") if w else "")

        approvals_out = [{**a, "project": owner_of(a["worker_id"])} for a in approvals]

    # Kayıt okuma kilit DIŞINDA — büyük bir kayıt ofisi bekletmesin.
    totals = {"cost": 0.0, "cost_known": True, "tokens_5m": 0, "cost_60m": 0.0, "input_like": 0,
              "cache_read": 0, "saved": 0.0, "by_model": {}}
    for s in sessions:
        m = meters.read(s["transcript_path"])
        if m is None:
            s.update({"model": None, "model_short": "?", "ctx": None, "tokens": None, "cost": None})
        else:
            s.update({
                "model": m.model,
                "model_short": short_model(m.model),
                "effort": m.effort,
                "ctx": {"used": m.ctx_used, "window": window_for(m.model)},
                "tokens": dict(m.tokens),
                "cost": round(m.cost, 4) if m.cost_known else None,
                "cost_partial": round(m.cost, 4),
            })
        s.pop("transcript_path", None)
    for path in today_paths:
        m = meters.read(path)
        if m is None:
            continue
        if not m.cost_known:
            totals["cost_known"] = False
        for ts, tok, c, day, inl, cr, saved, model in m.recent:
            if day != today:
                continue
            totals["cost"] += c
            totals["input_like"] += inl
            totals["cache_read"] += cr
            totals["saved"] += saved
            totals["by_model"][model] = totals["by_model"].get(model, 0.0) + c
            if ts > now - 300:
                totals["tokens_5m"] += tok
            if ts > now - 3600:
                totals["cost_60m"] += c

    return {
        "now": now,
        "last_event_ts": last_event,
        "sessions": sessions,
        "totals": {
            "sessions_live": len(sessions),
            "subagents_running": subs_running,
            "subagents_today": subs_today,
            "tools_per_min": round(len(all_marks) / 5, 1),
            "tokens_per_min": round(totals["tokens_5m"] / 5),
            "cost_today": round(totals["cost"], 4),
            "cost_known": totals["cost_known"],
            "cost_per_hour": round(totals["cost_60m"], 4),
            "cache_hit": round(totals["cache_read"] / totals["input_like"], 3) if totals["input_like"] else None,
            "cache_saved": round(totals["saved"], 4),
            "by_model": {k: round(v, 4) for k, v in sorted(totals["by_model"].items(), key=lambda kv: -kv[1])},
        },
        "tool_mix": tool_mix,
        "research": research,
        "files": files_out,
        "log": log[:40],
        "approvals": approvals_out,
        "runaways": runaways.items(),
        # Chiron'dan cevaplanabilen izin soruları (backend/core/onay.py) — oturuma bağlı.
        "decisions": _decisions(sessions),
    }


def _decisions(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from backend.core.onay import broker

    by_sid = {s["session_id"]: s["id"] for s in sessions}
    return [{**d, "worker_id": by_sid.get(d["session_id"])} for d in broker.pending()]


# ── Yörünge özeti ────────────────────────────────────────────────────────────
def _norm(path: str | None) -> str:
    return os.path.normcase(os.path.normpath(path)) if path else ""


def _same_tree(a: str | None, b: str | None) -> bool:
    """Biri ötekinin içinde mi (oturum frontend/'de, sunucu kökte çalışıyor olabilir)."""
    x, y = _norm(a), _norm(b)
    if not x or not y:
        return False
    return x == y or x.startswith(y + os.sep) or y.startswith(x + os.sep)


def orbit_view(state: Any | None = None) -> dict[str, Any]:
    """Yörüngenin ekleri için hafif özet (3D sahne 5 sn'de bir sorar): bağlam halkası, arka plan işleri,
    dev sunucu uyduları, kaçak süreç meteorları, bekleyen onaylar. `view()`'den ucuz — günün bütün
    kayıtlarını değil yalnız canlı oturumların kaydını okur."""
    from backend.core.onay import broker

    office = state or ofis_mod.office
    now = time.time()
    with office._lock:
        live = [w for w in office.workers.values() if w.kind == "chief" and w.status in ACTIVE
                and (w.last_ts or w.started) > now - STALE_S]
        heads = [(w.id, w.session_id, w.cwd, w.transcript_path) for w in live]
        bg = [dict(j) for j in office.bg_jobs.values()
              if j["ended"] is None or j["ended"] > now - 20]
    by_sid = {sid: wid for wid, sid, _, _ in heads}
    ctx: dict[str, Any] = {}
    for wid, _, _, path in heads:
        m = meters.read(path)
        if m is not None and m.ctx_used:
            ctx[wid] = {"used": m.ctx_used, "window": window_for(m.model)}
    run = runaways.items()
    run_pids = {r["pid"] for r in run}
    dev = []
    for item in runaways.listeners():
        if item["pid"] in run_pids:
            continue  # kaçaksa meteor olarak görünür
        owner = next((wid for wid, _, cwd, _ in heads if _same_tree(item.get("cwd"), cwd)), None)
        if owner:
            dev.append({**item, "session": owner})
    decisions = []
    for d in broker.pending():
        decisions.append({**d, "worker_id": by_sid.get(d["session_id"])})
    return {"now": now, "ctx": ctx, "bg": bg, "dev": dev, "runaways": run, "decisions": decisions}


def phone_view(full: dict[str, Any], decisions: list[dict[str, Any]], limits: dict[str, Any]) -> dict[str, Any]:
    """Telefondaki Gözetim özeti (taslak F): `view()` çıktısının hafif hali.

    Telefon her 5 sn yokluyor; `log`, `files`, `research`, transcript yolları gitmez. `decisions`
    onay kapısındaki (broker) cevap bekleyen sorular — telefon İzin ver/Reddet'i bunlara verir.
    """
    totals = full.get("totals") or {}
    sessions = []
    for s in full.get("sessions") or []:
        ctx = s.get("ctx") or {}
        window = ctx.get("window") or 0
        sessions.append({
            "id": s.get("id"),
            "project": s.get("project") or "",
            "title": (s.get("title") or "")[:80],
            "status": s.get("status"),
            "current": (s.get("current") or "")[:120],
            "last_ts": s.get("last_ts"),
            "cost": s.get("cost"),
            "ctx_pct": round(100 * (ctx.get("used") or 0) / window) if window else None,
            "subagents": sum(1 for a in s.get("subagents") or [] if a.get("status") in ACTIVE),
            "waiting": bool(s.get("approvals")),
        })
    queue = [{
        "id": d.get("id"),
        "project": d.get("project") or "",
        "tool": d.get("tool") or "",
        "summary": (d.get("summary") or "")[:160],
        "detail": (d.get("detail") or "")[:600],
        "can_always": bool(d.get("can_always")),
        "ts": d.get("ts"),
        "deadline": d.get("deadline"),
    } for d in decisions]
    windows = {}
    for key in ("five_hour", "seven_day"):
        w = limits.get(key) if isinstance(limits, dict) else None
        if isinstance(w, dict) and isinstance(w.get("used"), (int, float)):
            windows[key] = {"used": float(w["used"]), "resets_at": w.get("resets_at")}
    return {
        "now": full.get("now"),
        "live": totals.get("sessions_live", len(sessions)),
        "cost_today": totals.get("cost_today"),
        "cost_known": bool(totals.get("cost_known")),
        "limits": windows,
        "queue": queue,
        "sessions": sessions,
        "runaways": len(full.get("runaways") or []),
    }
