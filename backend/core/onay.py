"""Onay aracısı — Claude Code'un izin sorusuna Chiron'dan cevap (2026-11-04).

Yunus: "yörüngede onay bekledi geliyor ya, tıkladığımda önüme terminal gelsin, yazayım onaylayayım; ya da sesli
söyleyeyim." Akış:

1. Claude Code bir araç için izin soracakken `PermissionRequest` hook'u `~/.claude/hooks/chiron-onay.py`
   çalışır, isteği buraya bırakır (`add`) ve kararı bekler (`wait`, uzun yoklama).
2. Kullanıcı Gözetim'deki onay terminalinden ya da sesle (`actions/onay.py` → `answer_approval`) karar verir
   (`decide`). "Terminalde cevaplayacağım" derse `release`: hook kararsız çıkar, normal terminal sorusu gelir.
3. Süre dolarsa (varsayılan `WAIT_S`) hook yine kararsız çıkar — Chiron'un yokluğu Claude'u kilitlemesin.

Güvenlik: karar yalnız bu süreçte bellekte; kalıcı izin (`always`) Claude Code'un kendi önerisinden
(`permission_suggestions`) seçilir, uydurulmaz. Uzak istemci (telefon) için /api/ yolları PIN'li
(RemoteAccessMiddleware). Komut metni ekrana gelmeden `ofis.mask` ile gizli değerlerden arındırılır.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from backend.core.ofis import _basename, _first_line, mask

WAIT_S = 60  # hook en fazla bu kadar bekler; sonra karar terminale kalır (terminal sorusu bu süre gecikebilir)
KEEP_DONE_S = 60
MAX_PENDING = 50


@dataclass
class Request:
    id: str
    ts: float
    session_id: str
    cwd: str | None
    tool: str
    summary: str
    detail: str
    suggestions: list[dict[str, Any]]
    deadline: float
    state: str = "bekliyor"  # bekliyor | izin | red | terminal | sure_doldu
    message: str = ""
    always: bool = False
    decided_at: float | None = None
    by: str = ""

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ts": self.ts,
            "session_id": self.session_id,
            "project": _basename(self.cwd) or self.session_id[:8],
            "cwd": self.cwd,
            "tool": self.tool,
            "summary": self.summary,
            "detail": self.detail,
            "can_always": bool(self.suggestions),
            "deadline": self.deadline,
            "state": self.state,
        }


def describe(tool: str, tool_input: dict[str, Any] | None) -> tuple[str, str]:
    """Terminaldeki gibi tek satır özet + ayrıntı. Ayrıntı maskeli ve kırpılmış."""
    ti = tool_input if isinstance(tool_input, dict) else {}
    if tool in ("Bash", "PowerShell"):
        cmd = mask(str(ti.get("command") or ""))
        return f"{tool}({_first_line(cmd, 120)})", mask(str(ti.get("description") or ""))[:400] + (
            "\n\n" + cmd[:3000] if len(cmd) > 120 or "\n" in cmd else "")
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit", "Read"):
        path = str(ti.get("file_path") or ti.get("notebook_path") or "")
        extra = ""
        if tool == "Edit":
            extra = f"− {mask(str(ti.get('old_string') or ''))[:800]}\n+ {mask(str(ti.get('new_string') or ''))[:800]}"
        elif tool == "Write":
            extra = mask(str(ti.get("content") or ""))[:1200]
        return f"{tool}({path})", extra
    if tool in ("WebFetch", "WebSearch"):
        target = str(ti.get("url") or ti.get("query") or "")
        return f"{tool}({_first_line(mask(target), 140)})", ""
    body = mask(str(ti))[:1500]
    return f"{tool}", body


class OnayBroker:
    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._items: dict[str, Request] = {}
        self._news: deque = deque(maxlen=20)

    def _prune(self, now: float) -> None:
        for rid in [k for k, r in self._items.items()
                    if (r.state != "bekliyor" and (r.decided_at or r.ts) < now - KEEP_DONE_S)
                    or (r.state == "bekliyor" and r.deadline < now - 5)]:
            r = self._items.pop(rid)
            if r.state == "bekliyor":
                r.state = "sure_doldu"

    def add(self, payload: dict[str, Any], wait_s: float = WAIT_S) -> dict[str, Any]:
        now = time.time()
        tool = str(payload.get("tool_name") or "?")
        summary, detail = describe(tool, payload.get("tool_input"))
        suggestions = [s for s in (payload.get("permission_suggestions") or []) if isinstance(s, dict)]
        req = Request(
            id=secrets.token_hex(6),
            ts=now,
            session_id=str(payload.get("session_id") or ""),
            cwd=payload.get("cwd"),
            tool=tool,
            summary=summary,
            detail=detail.strip(),
            suggestions=suggestions[:4],
            deadline=now + max(5.0, min(float(wait_s), 600.0)),
        )
        with self._cond:
            self._prune(now)
            if len([r for r in self._items.values() if r.state == "bekliyor"]) >= MAX_PENDING:
                raise ValueError("Çok fazla bekleyen onay var.")
            self._items[req.id] = req
            self._news.append(req.id)
            self._cond.notify_all()
        return {"id": req.id, "deadline": req.deadline}

    def wait(self, rid: str, timeout: float = 25.0) -> dict[str, Any]:
        """Uzun yoklama: karar ya da süre dolması ya da `timeout` (hook yeniden sorar)."""
        end = time.time() + max(0.5, min(timeout, 50.0))
        with self._cond:
            while True:
                req = self._items.get(rid)
                if req is None:
                    return {"state": "yok"}
                now = time.time()
                if req.state == "bekliyor" and now >= req.deadline:
                    req.state, req.decided_at = "sure_doldu", now
                if req.state != "bekliyor":
                    return self._result(req)
                if now >= end:
                    return {"state": "bekliyor", "deadline": req.deadline}
                self._cond.wait(min(end, req.deadline) - now)

    @staticmethod
    def _result(req: Request) -> dict[str, Any]:
        out: dict[str, Any] = {"state": req.state}
        if req.state == "izin" and req.always and req.suggestions:
            out["updated_permissions"] = req.suggestions
        if req.state == "red":
            out["message"] = req.message or "Kullanıcı Chiron'dan reddetti."
        return out

    def decide(self, rid: str, behavior: str, message: str = "", always: bool = False, by: str = "ekran") -> tuple[bool, str]:
        if behavior not in ("izin", "red", "terminal"):
            return False, "Karar izin, red ya da terminal olmalı."
        with self._cond:
            req = self._items.get(rid)
            if req is None:
                return False, "Bu onay isteği artık yok."
            if req.state != "bekliyor":
                return False, "Bu isteğe zaten karar verilmiş."
            if time.time() >= req.deadline:
                req.state = "sure_doldu"
                return False, "Süre doldu; soru terminalde."
            req.state = behavior
            req.message = (message or "").strip()[:2000]
            req.always = bool(always) and behavior == "izin"
            req.decided_at = time.time()
            req.by = by
            self._cond.notify_all()
        return True, ""

    def cancel(self, rid: str) -> None:
        """Hook çıktı (süre/kesinti): kayıt temizlensin."""
        with self._cond:
            req = self._items.get(rid)
            if req is not None and req.state == "bekliyor":
                req.state, req.decided_at = "sure_doldu", time.time()
                self._cond.notify_all()

    def pending(self) -> list[dict[str, Any]]:
        now = time.time()
        with self._cond:
            self._prune(now)
            return [r.public() for r in sorted(self._items.values(), key=lambda r: r.ts)
                    if r.state == "bekliyor" and r.deadline > now]

    def pop_news(self) -> list[dict[str, Any]]:
        """Ses döngüsü için: yeni gelen ve hâlâ bekleyen istekler (bir kez)."""
        with self._cond:
            ids = list(self._news)
            self._news.clear()
            return [self._items[i].public() for i in ids if i in self._items and self._items[i].state == "bekliyor"]


broker = OnayBroker()
