"""Gözetim oturum kontrolü (2026-11-05) — "ne yapıyorsun?" sohbeti, Sonlandır, Geri al.

Yunus: "projeye ne yaptığını sormak için sohbet alanı; sonlandır butonu, basınca yapılanları
silme veya sonra devam etme seçenekleri".

Sor: oturumun kaydından (transcript) kısa bir özet çıkarılır ve AYRI bir `claude -p` sorgusuna
verilir — çalışan oturuma mesaj gitmez, onu bölmez, kaydına yazmaz. Yan sorgu araçsızdır
(`--tools ""`), kalıcı oturum açmaz ve kullanıcı ayarlarını yüklemez (`--setting-sources ""`):
hook'lar çalışmaz, Gözetim'de hayalet oturum belirmez.

Sonlandır: oturumun claude.exe'si hook'un üst sürecinden (ofis-olay.py "ppid") bulunur, ağacıyla
kapatılır. Kayıt diskte kalır → "Komuta'da sürdür" sonra kaldığı yerden devam ettirir.

Geri al: Claude Code'un kendi dosya yedekleri (~/.claude/file-history/<oturum>/<h>@v1, h =
sha256(mutlak yol)[:16]) oturumun dokunmadan önceki halidir. v1 yoksa ve dosyayı oturum
oluşturduysa ("type": "create") dosya silinir; ikisi de yoksa dokunulmaz. Uygulamadan önce
dosyaların o anki hali %LOCALAPPDATA%/chiron/geri-alinan/ altına kopyalanır (geri almanın geri alması).
Shell ile yapılan değişiklikler (git, sed, npm) izlenmediği için geri alınmaz — arayüz bunu söyler.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from backend.core.claude_jobs import find_claude_exe

logger = logging.getLogger("chiron.oturum_kontrol")

CLAUDE_HOME = Path(os.path.expanduser("~")) / ".claude"
FILE_HISTORY = CLAUDE_HOME / "file-history"
UNDO_ROOT = Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))) / "chiron" / "geri-alinan"
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
DIGEST_CHARS = 40_000
ASK_MODEL = "sonnet"
ASK_TIMEOUT_S = 150

ASK_SYSTEM = (
    "Sen Chiron'sun. Yunus, bilgisayarında çalışan bir Claude Code oturumunu izliyor ve sana o "
    "oturumun ne yaptığını soruyor. Sana oturum kaydının sonundan bir özet veriliyor: Yunus'un "
    "oturuma verdiği görevler, oturumun yazdıkları ve çağırdığı araçlar. Yalnız bu özete dayan; "
    "özette olmayanı uydurma, bilmiyorsan 'kayıtta görünmüyor' de. Türkçe, kısa ve doğrudan cevap "
    "ver; dosya adlarını ve somut adımları say. Araç kullanamazsın."
)


# ── Kayıt okuma ──────────────────────────────────────────────────────────────
def _lines(path: str | Path, tail_bytes: int | None = None) -> list[dict[str, Any]]:
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if tail_bytes and size > tail_bytes:
                f.seek(size - tail_bytes)
                f.readline()  # yarım satır
            data = f.read()
    except OSError:
        return []
    out = []
    for raw in data.split(b"\n"):
        if not raw.strip():
            continue
        try:
            out.append(json.loads(raw))
        except (ValueError, UnicodeDecodeError):
            continue
    return out


def _tool_line(name: str, tin: dict[str, Any]) -> str:
    if name in WRITE_TOOLS or name == "Read":
        return f"{name} {tin.get('file_path') or tin.get('notebook_path') or ''}"
    if name in ("Bash", "PowerShell"):
        desc = tin.get("description") or ""
        cmd = str(tin.get("command") or "")[:160]
        return f"{name}: {desc} — {cmd}" if desc else f"{name}: {cmd}"
    if name in ("Agent", "Task"):
        return f"Alt ajan ({tin.get('subagent_type') or 'general'}): {tin.get('description') or ''}"
    if name in ("Grep", "Glob"):
        return f"{name} {tin.get('pattern') or ''}"
    if name in ("WebFetch", "WebSearch"):
        return f"{name} {tin.get('url') or tin.get('query') or ''}"
    return name


def digest(path: str | None, limit: int = DIGEST_CHARS) -> str:
    """Kaydın sonundan okunur özet: görevler, cevaplar, araç çağrıları (araç çıktıları değil)."""
    if not path:
        return ""
    parts: list[str] = []
    for rec in _lines(path, tail_bytes=6 * 1024 * 1024):
        if rec.get("isSidechain") or rec.get("isMeta"):
            continue
        t = rec.get("type")
        content = (rec.get("message") or {}).get("content")
        if t == "user":
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = "\n".join(c.get("text", "") for c in content
                                 if isinstance(c, dict) and c.get("type") == "text")
            else:
                text = ""
            text = text.strip()
            if text and not text.startswith("<"):  # komut/hatırlatma sarmalları değil
                parts.append(f"\n[YUNUS] {text[:3000]}")
        elif t == "assistant" and isinstance(content, list):
            for c in content:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "text" and c.get("text"):
                    parts.append(f"[OTURUM] {c['text'][:2500]}")
                elif c.get("type") == "tool_use":
                    parts.append(f"  · {_tool_line(c.get('name', ''), c.get('input') or {})}")
    text = "\n".join(parts)
    if len(text) > limit:
        text = "…(öncesi kesildi)\n" + text[-limit:]
    return text


def ask(transcript_path: str | None, project: str, question: str,
        history: list[dict[str, str]] | None = None) -> str:
    """Oturuma dokunmadan, kaydının özetiyle ayrı bir Claude'a sorar."""
    exe = find_claude_exe()
    if not exe:
        raise RuntimeError("claude.exe bulunamadı.")
    body = digest(transcript_path)
    if not body:
        raise RuntimeError("Bu oturumun kaydı okunamadı.")
    convo = ""
    for h in (history or [])[-6:]:
        q, a = str(h.get("q", ""))[:1000], str(h.get("a", ""))[:2000]
        if q and a:
            convo += f"\nYunus: {q}\nSen: {a}\n"
    prompt = (
        f"Proje: {project}\n\n=== OTURUM KAYDI (son kısım) ===\n{body}\n=== KAYIT SONU ===\n"
        + (f"\nÖnceki sorular:{convo}\n" if convo else "")
        + f"\nYunus'un sorusu: {question}"
    )
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)
    proc = subprocess.run(
        [exe, "-p", "--model", ASK_MODEL, "--tools", "", "--no-session-persistence",
         "--setting-sources", "", "--system-prompt", ASK_SYSTEM],
        input=prompt.encode("utf-8"),
        capture_output=True,
        timeout=ASK_TIMEOUT_S,
        env=env,
        cwd=str(Path.home()),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    out = proc.stdout.decode("utf-8", "replace").strip()
    if proc.returncode != 0 or not out:
        err = proc.stderr.decode("utf-8", "replace").strip() or out
        raise RuntimeError(f"Cevap alınamadı: {err[:300]}")
    return out


# ── Süreç ────────────────────────────────────────────────────────────────────
# İnceleme (2026-11-05): "süreç bulunamadı" ASLA "kapalı" sayılmaz — bulunamayan ama yaşayan bir
# oturumun dosyalarını geri almak, oturum üstüne yazmaya devam ederken dosyaları bozar. Karar
# api/office.py'de: bulunamadıysa ve son 10 dakikada olayı varsa dosyalara dokunulmaz.
NOT_FOUND = "bulunamadi"
KILLED = "kapatildi"
FAILED = "hata"
_SESSION_ID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _is_claude_cli(p: Any) -> bool:
    """Claude Code CLI süreci mi. Claude masaüstü uygulaması (AnthropicClaude / WindowsApps altındaki
    Claude.exe ve Electron yardımcıları) DEĞİL — pid yanlış eşleşirse bütün uygulama kapanmasın."""
    try:
        name = (p.name() or "").lower()
        exe = (p.exe() or "").lower()
    except Exception:
        return False
    if "anthropicclaude" in exe or "\\windowsapps\\" in exe:
        return False
    if name == "claude.exe" or name == "claude":
        return True
    if name == "node.exe":
        try:
            return "claude-code" in " ".join(p.cmdline()).lower()
        except Exception:
            return False
    return False


def find_process(hook_ppid: int | None, hook_ts: float | None, session_id: str | None) -> Any | None:
    """Oturumun claude süreci. Hook'un üst süreci doğrudan claude.exe (arada kabuk yok); pid yeniden
    kullanılmış olmasın diye süreç, o pid'i yazan olaydan ÖNCE başlamış olmalı. Yedek yol:
    komut satırında `--resume <oturum>`."""
    try:
        import psutil
    except ImportError:
        return None
    if hook_ppid and hook_ts:
        try:
            p = psutil.Process(hook_ppid)
            if _is_claude_cli(p) and p.create_time() <= hook_ts + 1:
                return p
        except Exception:
            pass
    if session_id:
        for p in psutil.process_iter(["name"]):
            if not _is_claude_cli(p):
                continue
            try:
                cmd = p.cmdline()
            except Exception:
                continue
            if session_id in cmd:
                return p
    return None


def _protected() -> set[int]:
    try:
        import psutil

        me = psutil.Process(os.getpid())
        return {me.pid, *(p.pid for p in me.parents())}
    except Exception:
        return {os.getpid()}


def kill_tree(proc: Any) -> None:
    import psutil

    tree = proc.children(recursive=True)
    tree.reverse()
    victims = tree + [proc]
    # Chiron bu oturumun içinden başlatılmış olabilir (ya da onun atası olabilir): ağacın tamamına bak.
    if {v.pid for v in victims} & _protected():
        raise RuntimeError("Bu oturumun ağacında Chiron'un kendisi var — kapatılmadı.")
    for v in victims:
        try:
            v.terminate()
        except psutil.NoSuchProcess:
            pass
    _, still = psutil.wait_procs(victims, timeout=3)
    for v in still:
        try:
            v.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(still, timeout=2)


def stop(hook_ppid: int | None, hook_ts: float | None, session_id: str | None) -> tuple[str, str]:
    """Oturumun sürecini kapatır → (durum, açıklama). Durum: kapatildi | bulunamadi | hata.
    Chiron'un başlattığı bir işse iş kuyruğundan iptal edilir (durumu 'durdu' olsun, 'hata' değil)."""
    proc = find_process(hook_ppid, hook_ts, session_id)
    if proc is None:
        return NOT_FOUND, "Oturumun süreci bulunamadı."
    job_id = None
    try:
        job_id = proc.environ().get("CHIRON_CLAUDE_JOB")
    except Exception:
        pass
    if job_id:
        from backend.core import claude_jobs

        claude_jobs.jobs.cancel(job_id)
        try:
            proc.wait(timeout=8)
            return KILLED, "Chiron işi durduruldu."
        except Exception:
            pass  # iş kuyruğu kapatamadıysa aşağıda ağacıyla
    try:
        kill_tree(proc)
    except RuntimeError as e:
        return FAILED, str(e)
    except Exception as e:  # AccessDenied vb.
        return FAILED, f"Kapatılamadı: {e}"
    return KILLED, "Oturum kapatıldı."


def alive(hook_ppid: int | None, hook_ts: float | None, session_id: str | None) -> bool:
    return find_process(hook_ppid, hook_ts, session_id) is not None


# ── Geri alma ────────────────────────────────────────────────────────────────
def _hash(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]


def _transcripts(transcript_path: str) -> list[Path]:
    main = Path(transcript_path)
    subs = sorted((main.parent / main.stem / "subagents").glob("*.jsonl"))
    return [main, *subs]


def _touched(transcript_path: str) -> dict[str, dict[str, Any]]:
    """Oturumun (ve alt ajanlarının) yazma araçlarıyla dokunduğu dosyalar.
    {yol: {"created": İLK başarılı yazma yeni dosya mı}}. Ana kayıt ile alt ajan kayıtları zaman
    damgasına göre birleştirilir — alt ajanın oluşturduğu dosyayı ana döngü sonra yazdıysa "create" kaybolmasın."""
    uses: dict[str, str] = {}  # tool_use_id → yol
    results: list[tuple[str, int, str, bool]] = []  # (zaman, sıra, tool_use_id, create mi)
    seq = 0
    for t in _transcripts(transcript_path):
        for rec in _lines(t):
            content = (rec.get("message") or {}).get("content")
            if rec.get("type") == "assistant" and isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") in WRITE_TOOLS:
                        tin = c.get("input") or {}
                        p = tin.get("file_path") or tin.get("notebook_path")
                        if p and os.path.isabs(p):
                            uses[c.get("id", "")] = os.path.normpath(p)
            elif rec.get("type") == "user" and isinstance(content, list):
                res = rec.get("toolUseResult")
                created = isinstance(res, dict) and res.get("type") == "create"
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "tool_result" and not c.get("is_error"):
                        seq += 1
                        results.append((str(rec.get("timestamp") or ""), seq, c.get("tool_use_id", ""), created))
    files: dict[str, dict[str, Any]] = {}
    for _, _, tid, created in sorted(results):
        p = uses.get(tid)
        if p and p not in files:
            files[p] = {"created": created}
    return files


def plan(session_id: str | None, transcript_path: str | None) -> dict[str, Any]:
    """Geri almada ne olacak — hiçbir şeye dokunmaz."""
    if not session_id or not transcript_path:
        return {"items": [], "ok": False, "why": "Oturum kaydı yok."}
    if not _SESSION_ID.fullmatch(session_id) or not _under(transcript_path, CLAUDE_HOME / "projects"):
        return {"items": [], "ok": False, "why": "Oturum kaydı beklenen yerde değil."}
    hist = FILE_HISTORY / session_id
    items = []
    for path, info in _touched(transcript_path).items():
        exists = os.path.exists(path)
        backup = hist / f"{_hash(path)}@v1"
        if not backup.exists():
            backup = None
        if backup is not None:
            try:
                same = exists and Path(path).read_bytes() == backup.read_bytes()
            except OSError:
                same = False
            action = "ayni" if same else "geri"
        elif info["created"]:
            action = "sil" if exists else "ayni"
        else:
            action = "atla"  # yedek yok, oturum oluşturmamış — körlemesine dokunmayız
        items.append({"path": path, "action": action, "backup": str(backup) if backup else None})
    return {"items": items, "ok": True, "why": ""}


def _under(path: str, root: Path) -> bool:
    try:
        return Path(path).resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


_apply_lock = threading.Lock()


def apply(session_id: str, transcript_path: str) -> dict[str, Any]:
    # Telefondan ve ekrandan aynı anda gelen iki istek birbirinin kopyalarını ezmesin.
    with _apply_lock:
        return _apply(session_id, transcript_path)


def _apply(session_id: str, transcript_path: str) -> dict[str, Any]:
    p = plan(session_id, transcript_path)
    if not p["ok"]:
        return {"geri": 0, "sil": 0, "hata": 1, "skipped": 0, "undo_dir": "", "errors": [p["why"]]}
    todo = [i for i in p["items"] if i["action"] in ("geri", "sil")]
    stamp = time.strftime("%Y%m%d-%H%M%S")
    undo = UNDO_ROOT / f"{stamp}-{time.time_ns() % 10**6:06d}-{session_id[:8]}"
    manifest = []
    done = {"geri": 0, "sil": 0, "hata": 0}
    errors: list[str] = []
    for n, item in enumerate(todo):
        path = item["path"]
        try:
            if os.path.exists(path):
                undo.mkdir(parents=True, exist_ok=True)
                keep = undo / f"{n:03d}-{os.path.basename(path)}"
                shutil.copy2(path, keep)
                manifest.append({"path": path, "saved": keep.name, "action": item["action"]})
            if item["action"] == "geri":
                os.makedirs(os.path.dirname(path), exist_ok=True)
                shutil.copyfile(item["backup"], path)
            else:
                os.remove(path)
            done[item["action"]] += 1
        except OSError as e:
            done["hata"] += 1
            errors.append(f"{os.path.basename(path)}: {e}")
    if manifest:
        (undo / "manifest.json").write_text(
            json.dumps({"session_id": session_id, "ts": time.time(), "files": manifest},
                       ensure_ascii=False, indent=1), encoding="utf-8")
    logger.info("Oturum geri alındı: %s geri=%s sil=%s hata=%s", session_id, done["geri"], done["sil"], done["hata"])
    return {**done, "skipped": sum(1 for i in p["items"] if i["action"] == "atla"),
            "undo_dir": str(undo) if manifest else "", "errors": errors[:5]}

