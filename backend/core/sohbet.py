"""Sohbet — Chiron'dan ajanla süren konuşma (Komuta ekranı, 2026-10-27).

Kullanıcı isteği: "sana terminalde nasıl iş veriyorsam Chiron'da da öyle olsun". Pano kartı tek
seferlik iş; sohbette her mesaj AYNI Claude oturumunu `--resume` ile sürdürür, yani ajan önceki
mesajları bilir. İşi yine `claude_jobs` koşar: aynı kuyruk, bekçi, kota freni, süre sınırı.

- Claude sohbeti: ilk mesaj yeni oturum açar, sonrakiler o oturumu sürdürür.
- Gemini sohbeti: Gemini CLI oturum sürdürmüyor; son mesajlar görevin başına bağlam olarak eklenir.
- Terminali devral: PC'deki etkileşimli Claude Code oturumu (`~/.claude/projects/*/<id>.jsonl`)
  sohbete alınır ve oradan sürer. PC'de açıkken devralınmaz — iki süreç aynı kayda yazar.
  "Açık" sayılması: kaydı son 2 dakikada değişti ya da ofis hook'ları SessionEnd görmedi.

Onay: ajan geri alınamayan adımda `ONAY_GEREKLI:` ile durur; mesaj "onay" durumuna geçer,
Yunus'un bir sonraki mesajı (ya da Onayla/Reddet düğmesi) aynı oturumu sürdürür.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Callable

from backend.core import claude_jobs

logger = logging.getLogger("chiron.sohbet")

BASE_DIR = Path(__file__).resolve().parents[2]
STORE_PATH = BASE_DIR / "config" / "sohbet.json"
PROJECTS_DIR = Path.home() / ".claude" / "projects"

AGENTS = ("claude", "gemini")
MAX_CHATS = 30
MAX_MESSAGES = 200
MAX_TEXT = claude_jobs.MAX_TASK_CHARS
MAX_TITLE = 80
GEMINI_CONTEXT = 8  # Gemini'ye bağlam olarak giden son mesaj sayısı
CONTEXT_CHARS = 600  # bağlamdaki mesaj başına kırpma

# Sesli Chiron'a verilen "süren iş" bağlamı (work_context, 2026-10-30)
WORK_CONTEXT_DAYS = 3  # bundan eski sohbet "süren iş" sayılmaz
WORK_CONTEXT_MESSAGES = 4
WORK_CONTEXT_CHARS = 300

# Terminal oturumları
TERMINAL_DAYS = 14
TERMINAL_LIMIT = 12
OPEN_SECONDS = 120  # kaydı bu kadar yakın zamanda değiştiyse PC'de açık say
HEAD_LINES = 40
TAIL_BYTES = 256 * 1024

APPROVE_TEXT = "Onaylıyorum, o adımı yap ve devam et."
REJECT_TEXT = "Onaylamıyorum; o adımı yapma. Ne yaptığını ve durumu kısaca söyle."

_JOB_TO_STATUS = {
    "queued": "sirada",
    "running": "calisiyor",
    "done": "bitti",
    "needs_approval": "onay",
    "failed": "hata",
    "timeout": "hata",
    "interrupted": "hata",
    "cancelled": "durdu",
}
LIVE = ("sirada", "calisiyor")


class SohbetError(Exception):
    """Kullanıcıya gösterilecek hata (409)."""


def _now() -> float:
    return time.time()


class Sohbet:
    """Sohbetler bellekte + `config/sohbet.json`'da. İşler `claude_jobs`'ta; mesaj durumu
    her okumada iş kaydından tazelenir (ayrı bir izleyici thread'i yok)."""

    def __init__(
        self,
        store_path: Path = STORE_PATH,
        jobs: Any = None,
        projects_dir: Path = PROJECTS_DIR,
        session_active: Callable[[str], bool] | None = None,
        clock: Callable[[], float] = _now,
    ) -> None:
        self.store_path = store_path
        self.jobs = jobs or claude_jobs.jobs
        self.projects_dir = projects_dir
        self._session_active = session_active
        self.clock = clock
        self._lock = threading.RLock()
        self._chats: dict[str, dict[str, Any]] = {}
        self._load()

    # ── Kalıcılık ────────────────────────────────────────────────────────
    def _load(self) -> None:
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except Exception:
            logger.exception("Sohbet kaydı okunamadı")
            return
        for chat in data.get("chats", []) if isinstance(data, dict) else []:
            if isinstance(chat, dict) and chat.get("id"):
                chat.setdefault("messages", [])
                self._chats[chat["id"]] = chat

    def _save(self) -> None:
        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.store_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps({"chats": list(self._chats.values())}, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.store_path)
        except Exception:
            logger.exception("Sohbet kaydı yazılamadı")

    # ── Okuma ────────────────────────────────────────────────────────────
    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            changed = any([self._sync(chat) for chat in self._chats.values()])
            if changed:
                self._save()
            chats = sorted(self._chats.values(), key=lambda c: c["updated"], reverse=True)
            return [self._summary(c) for c in chats]

    def get(self, chat_id: str) -> dict[str, Any]:
        with self._lock:
            chat = self._find(chat_id)
            if self._sync(chat):
                self._save()
            return {**self._summary(chat), "messages": [dict(m) for m in chat["messages"]]}

    def _summary(self, chat: dict[str, Any]) -> dict[str, Any]:
        last = chat["messages"][-1] if chat["messages"] else None
        live = next((m for m in reversed(chat["messages"]) if m.get("status") in LIVE), None)
        waiting = bool(last and last.get("status") == "onay")
        return {
            "id": chat["id"],
            "title": chat["title"],
            "agent": chat["agent"],
            "source": chat.get("source", "chiron"),
            "cwd": chat.get("cwd"),
            "created": chat["created"],
            "updated": chat["updated"],
            "count": len(chat["messages"]),
            "busy": live is not None,
            "status": live["status"] if live else ("onay" if waiting else ""),
            "last_step": live.get("last_step", "") if live else "",
            "approval": last.get("approval", "") if waiting and last else "",
            "preview": (last or {}).get("text", "")[:120],
        }

    def _find(self, chat_id: str) -> dict[str, Any]:
        chat = self._chats.get(chat_id)
        if not chat:
            raise SohbetError("Sohbet bulunamadı.")
        return chat

    def _sync(self, chat: dict[str, Any]) -> bool:
        """Canlı mesajları iş kaydından tazeler. Değişiklik olduysa True."""
        changed = False
        for msg in chat["messages"]:
            if msg.get("status") not in LIVE or not msg.get("job_id"):
                continue
            job = self.jobs.get(msg["job_id"])
            if not job:
                msg.update(status="hata", text=msg.get("text") or "İş kaydı kayboldu (Chiron yeniden başlamış olabilir).")
                changed = True
                continue
            status = _JOB_TO_STATUS.get(job.get("status"), "hata")
            steps = list(job.get("trail") or [])
            before = (msg.get("status"), len(msg.get("steps", [])), msg.get("last_step"))
            msg["status"] = status
            msg["steps"] = steps
            msg["last_step"] = job.get("last_step", "")
            if job.get("session_id") and chat["agent"] == "claude" and not chat.get("session_id"):
                chat["session_id"] = job["session_id"]
                changed = True
            if status not in LIVE:
                msg["text"] = job.get("summary") or job.get("error") or "Sonuç gelmedi."
                msg["approval"] = job.get("approval", "")
                msg["cost_usd"] = job.get("cost_usd")
                msg["bekci"] = [h.get("ad") for h in job.get("bekci") or [] if h.get("ad")][:5]
                msg["at"] = job.get("finished_at") or self.clock()
                chat["updated"] = msg["at"]
                # Kalıcı oturum: iş bitince kesinleşen kimliği al (ilk mesajda sohbetin oturumu doğar).
                if job.get("session_id") and chat["agent"] == "claude":
                    chat["session_id"] = job["session_id"]
            if before != (msg.get("status"), len(msg.get("steps", [])), msg.get("last_step")):
                changed = True
        return changed

    # ── Yazma ────────────────────────────────────────────────────────────
    def create(self, agent: str = "claude", title: str = "", cwd: str | None = None) -> dict[str, Any]:
        if agent not in AGENTS:
            raise SohbetError("Bu ajanla sohbet yok; Claude ya da Gemini seç.")
        if cwd is not None and not Path(cwd).is_dir():
            raise SohbetError(f"Klasör yok: {cwd}")
        now = self.clock()
        chat = {
            "id": secrets.token_hex(4),
            "title": (title or "").strip()[:MAX_TITLE] or "Yeni sohbet",
            "agent": agent,
            "source": "chiron",
            "cwd": cwd,
            "session_id": None,
            "created": now,
            "updated": now,
            "messages": [],
        }
        with self._lock:
            self._chats[chat["id"]] = chat
            self._trim()
            self._save()
        return self.get(chat["id"])

    def send(self, chat_id: str, text: str, via: str = "pc") -> dict[str, Any]:
        """`via="telefon"`: mesaj telefondan (Komuta ekranı ya da sesli Chiron) — sonuç telefona
        bildirilir, ajan cevabını sesli okunacak gibi yazar."""
        text = (text or "").strip()
        if not text:
            raise SohbetError("Mesaj boş.")
        if len(text) > MAX_TEXT:
            raise SohbetError(f"Mesaj en fazla {MAX_TEXT} karakter olabilir.")
        with self._lock:
            chat = self._find(chat_id)
            self._sync(chat)
            if any(m.get("status") in LIVE for m in chat["messages"]):
                raise SohbetError("Ajan hâlâ önceki mesajında; bitince yaz ya da durdur.")
            task = text if chat["agent"] == "claude" else self._gemini_task(chat, text)
            try:
                job = self.jobs.submit(
                    task,
                    origin="sohbet_tel" if via == "telefon" else "sohbet",
                    cwd=chat.get("cwd"),
                    engine=chat["agent"],
                    session_id=chat.get("session_id") if chat["agent"] == "claude" else None,
                )
            except ValueError as error:
                raise SohbetError(str(error)) from error
            now = self.clock()
            if chat["title"] == "Yeni sohbet":
                chat["title"] = " ".join(text.split())[:MAX_TITLE]
            chat["messages"].append({"role": "ben", "text": text, "at": now, "via": via})
            chat["messages"].append(
                {"role": "ajan", "text": "", "at": now, "job_id": job.id, "status": "sirada", "steps": [], "last_step": ""}
            )
            del chat["messages"][:-MAX_MESSAGES]
            chat["updated"] = now
            self._save()
        return self.get(chat_id)

    def answer(self, chat_id: str, approved: bool, via: str = "pc") -> dict[str, Any]:
        """Onay bekleyen son mesaja cevap: aynı oturuma "onaylıyorum / onaylamıyorum" yazar."""
        with self._lock:
            chat = self._find(chat_id)
            self._sync(chat)
            last = chat["messages"][-1] if chat["messages"] else None
            if not last or last.get("status") != "onay":
                raise SohbetError("Onay bekleyen bir adım yok.")
        return self.send(chat_id, APPROVE_TEXT if approved else REJECT_TEXT, via)

    # ── Telefondan sesli iş (2026-10-29) ────────────────────────────────
    def phone_task(self, text: str, new_topic: bool = False, via: str = "telefon") -> dict[str, Any]:
        """Sesli Chiron'un verdiği iş (telefondaki ya da PC'deki): Komuta'daki son Claude sohbetine yazılır,
        yani konuşulan işin devamı olur. `new_topic` ya da hiç sohbet yoksa yeni sohbet açılır.
        Son sohbet meşgulse hata — Chiron "önceki iş sürüyor" der, yeni konu diye açtırabilir."""
        with self._lock:
            target = None
            if not new_topic:
                claude_chats = [c for c in self._chats.values() if c["agent"] == "claude"]
                target = max(claude_chats, key=lambda c: c["updated"], default=None)
            if target is not None:
                self._sync(target)
                live = next((m for m in reversed(target["messages"]) if m.get("status") in LIVE), None)
                if live is not None:
                    step = live.get("last_step") or "başlıyor"
                    raise SohbetError(f"'{target['title']}' sohbetinde önceki iş hâlâ sürüyor ({step}).")
            chat_id = target["id"] if target else self.create("claude")["id"]
        return self.send(chat_id, text, via=via)

    def work_context(self) -> str:
        """Sesli Chiron'un (PC ve telefon) sistem komutuna giren son iş: `phone_task`'ın yazacağı sohbet.
        2026-10-30, Yunus: "bir şey yaptırıyorum, her seferinde Dilcep dememe gerek kalmasın" — ses
        oturumu her açılışta sıfırdan başlıyor, hangi işte olunduğunu buradan bilir. Boş: süren iş yok."""
        with self._lock:
            claude_chats = [c for c in self._chats.values() if c["agent"] == "claude"]
            chat = max(claude_chats, key=lambda c: c["updated"], default=None)
            if chat is None or self.clock() - chat["updated"] > WORK_CONTEXT_DAYS * 86400:
                return ""
            if self._sync(chat):
                self._save()
            busy = any(m.get("status") in LIVE for m in chat["messages"])
            past = [m for m in chat["messages"] if m.get("text")][-WORK_CONTEXT_MESSAGES:]
            title, cwd, updated = chat["title"], chat.get("cwd"), chat["updated"]
        minutes = int((self.clock() - updated) // 60)
        ago = f"{minutes} dk önce" if minutes < 120 else f"{minutes // 60} saat önce"
        where = f", klasör {Path(cwd).name}" if cwd else ""
        lines = [
            "[SÜREN İŞ]",
            f"PC'deki son iş: \"{title}\"{where} — {'şu an sürüyor' if busy else 'son mesaj ' + ago}.",
        ]
        for m in past:
            who = "Kullanıcı" if m["role"] == "ben" else "Sonuç"
            lines.append(f"- {who}: {' '.join(m['text'].split())[:WORK_CONTEXT_CHARS]}")
        lines.append(
            "Kullanıcı proje adını söylemeden iş verirse (\"şunu da ekle\", \"alt barı değiştir\", \"devam et\") bu işin "
            "devamıdır: proje sormadan, new_topic VERMEDEN gönder. new_topic yalnız kullanıcı açıkça başka bir proje "
            "ya da ilgisiz bir iş söylerse. Bu bilgiyi kendiliğinden okuma."
        )
        return "\n".join(lines)

    def answer_job(self, job_id: str, approved: bool) -> dict[str, Any]:
        """Telefondaki onay cevabı iş kimliğiyle gelir: o işin sohbetini bulup aynı oturumu sürdürür."""
        with self._lock:
            chat = next(
                (c for c in self._chats.values() if any(m.get("job_id") == job_id for m in c["messages"])),
                None,
            )
            if chat is None:
                raise SohbetError("Bu iş bir sohbete ait değil.")
        return self.answer(chat["id"], approved, via="telefon")

    def stop(self, chat_id: str) -> dict[str, Any]:
        with self._lock:
            chat = self._find(chat_id)
            live = [m for m in chat["messages"] if m.get("status") in LIVE and m.get("job_id")]
        for msg in live:
            self.jobs.cancel(msg["job_id"])
        return self.get(chat_id)

    def delete(self, chat_id: str) -> None:
        with self._lock:
            chat = self._find(chat_id)
            if any(m.get("status") in LIVE for m in chat["messages"]):
                raise SohbetError("Ajan çalışırken silinmez; önce durdur.")
            del self._chats[chat_id]
            self._save()

    def _trim(self) -> None:
        idle = sorted(
            (c for c in self._chats.values() if not any(m.get("status") in LIVE for m in c["messages"])),
            key=lambda c: c["updated"],
        )
        for chat in idle[: max(0, len(self._chats) - MAX_CHATS)]:
            self._chats.pop(chat["id"], None)

    @staticmethod
    def _gemini_task(chat: dict[str, Any], text: str) -> str:
        """Gemini oturum sürdürmüyor: son mesajlar bağlam olarak görevin başına."""
        past = [m for m in chat["messages"] if m.get("text") and m.get("status") not in LIVE][-GEMINI_CONTEXT:]
        if not past:
            return text
        lines = [f"{'Yunus' if m['role'] == 'ben' else 'Sen'}: {m['text'][:CONTEXT_CHARS]}" for m in past]
        return "Önceki konuşma (bağlam):\n" + "\n".join(lines) + f"\n\nYunus'un yeni mesajı:\n{text}"

    # ── Terminal oturumları ─────────────────────────────────────────────
    def terminal_sessions(self) -> list[dict[str, Any]]:
        """PC'deki son etkileşimli Claude Code oturumları (en yeni önce). Chiron'un kendi açtığı
        `claude -p` oturumları (entrypoint sdk-cli) ve alt ajan kayıtları listelenmez."""
        horizon = self.clock() - TERMINAL_DAYS * 86400
        files: list[tuple[float, Path]] = []
        try:
            for project in self.projects_dir.iterdir():
                if not project.is_dir():
                    continue
                for path in project.glob("*.jsonl"):
                    try:
                        mtime = path.stat().st_mtime
                    except OSError:
                        continue
                    if mtime >= horizon:
                        files.append((mtime, path))
        except FileNotFoundError:
            return []
        files.sort(reverse=True)
        with self._lock:
            taken = {c.get("session_id") for c in self._chats.values() if c.get("source") == "terminal"}
        sessions: list[dict[str, Any]] = []
        for mtime, path in files[: TERMINAL_LIMIT * 4]:
            info = _read_session(path)
            if not info or info["entrypoint"] != "cli":
                continue
            sid = path.stem
            sessions.append({
                "session_id": sid,
                "title": info["title"] or info["last_prompt"][:MAX_TITLE] or sid[:8],
                "last_prompt": info["last_prompt"][:160],
                "cwd": info["cwd"],
                "updated": mtime,
                "open": self._is_open(sid, mtime),
                "taken": sid in taken,
            })
            if len(sessions) >= TERMINAL_LIMIT:
                break
        return sessions

    def _is_open(self, session_id: str, mtime: float) -> bool:
        if self.clock() - mtime < OPEN_SECONDS:
            return True
        try:
            return bool(self._session_active and self._session_active(session_id))
        except Exception:
            return False

    def takeover(self, session_id: str, force: bool = False) -> dict[str, Any]:
        """Terminal oturumunu sohbete alır. Sohbet zaten varsa onu döndürür."""
        if not re.fullmatch(r"[0-9a-fA-F-]{8,64}", session_id or ""):
            raise SohbetError("Geçersiz oturum kimliği.")
        with self._lock:
            for chat in self._chats.values():
                if chat.get("session_id") == session_id:
                    return self.get(chat["id"])
        found = next((s for s in self.terminal_sessions() if s["session_id"] == session_id), None)
        if not found:
            raise SohbetError("Oturum bulunamadı (son iki haftada PC'de açılmış etkileşimli oturumlar listelenir).")
        if found["open"] and not force:
            raise SohbetError("Bu oturum PC'de açık görünüyor; önce terminalde kapat. İki yerden yazılırsa kayıt bozulur.")
        if not found["cwd"] or not Path(found["cwd"]).is_dir():
            raise SohbetError("Oturumun klasörü artık yok; sürdürülemez.")
        now = self.clock()
        chat = {
            "id": secrets.token_hex(4),
            "title": found["title"][:MAX_TITLE],
            "agent": "claude",
            "source": "terminal",
            "cwd": found["cwd"],
            "session_id": session_id,
            "created": now,
            "updated": now,
            "messages": [{
                "role": "sistem",
                "text": f"PC'deki terminal oturumu devralındı: {found['title']}. Önceki konuşma bağlamda; "
                "buradan yazdıkların aynı oturumu sürdürür.",
                "at": now,
            }],
        }
        with self._lock:
            self._chats[chat["id"]] = chat
            self._trim()
            self._save()
        return self.get(chat["id"])


def _read_session(path: Path) -> dict[str, Any] | None:
    """Kaydın başından giriş noktası ve klasörü, sonundan başlık ve son mesajı okur
    (kayıtlar onlarca MB olabiliyor; tamamı okunmaz)."""
    info = {"entrypoint": "", "cwd": "", "title": "", "last_prompt": ""}
    try:
        with open(path, "rb") as fh:
            for i, raw in enumerate(fh):
                if i >= HEAD_LINES or (info["entrypoint"] and info["cwd"]):
                    break
                rec = _json(raw)
                if rec:
                    info["entrypoint"] = info["entrypoint"] or str(rec.get("entrypoint") or "")
                    info["cwd"] = info["cwd"] or str(rec.get("cwd") or "")
            size = fh.seek(0, os.SEEK_END)
            fh.seek(max(0, size - TAIL_BYTES))
            tail = fh.read().splitlines()
    except OSError:
        return None
    for raw in reversed(tail):
        if info["title"] and info["last_prompt"]:
            break
        rec = _json(raw)
        if not rec:
            continue
        if not info["title"] and rec.get("type") in ("custom-title", "ai-title"):
            info["title"] = str(rec.get("customTitle") or rec.get("aiTitle") or "")
        if not info["last_prompt"] and rec.get("type") == "last-prompt" and rec.get("lastPrompt"):
            info["last_prompt"] = " ".join(str(rec["lastPrompt"]).split())
    return info


def _json(raw: bytes) -> dict[str, Any] | None:
    try:
        rec = json.loads(raw)
    except ValueError:
        return None
    return rec if isinstance(rec, dict) else None


def _office_active(session_id: str) -> bool:
    from backend.core.ofis import office

    return office.session_active(session_id)


sohbet = Sohbet(session_active=_office_active)
