"""Son konuşma — sesli oturumlar arası kısa hafıza (2026-10-30).

Yunus: "sohbeti hatırlasın; bir şey yaptırıyorum, her seferinde Dilcep dememe gerek kalmasın, sende nasıl
işliyorsa öyle olsun". Gemini Live oturumu her bağlanışta (uyandırma, yeniden bağlanma, Chiron'u yeniden
açma) boş başlıyor. Son konuşma satırları diske yazılır, yeni oturumun sistem komutuna eklenir.
memory.json'daki kalıcı gerçeklerden ve activity_log'daki günlük akıştan ayrı: yalnız son birkaç saat.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STORE = BASE_DIR / "memory" / "son_konusma.json"

MAX_LINES = 20
MAX_CHARS = 400
KEEP_HOURS = 12  # bundan eski konuşma "kaldığımız yer" sayılmaz


def _load() -> list[dict]:
    try:
        data = json.loads(STORE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def add(who: str, text: str) -> None:
    """Hata sessizce yutulur — hafıza konuşmayı asla kesmemeli."""
    text = " ".join((text or "").split())
    if not text:
        return
    try:
        lines = _load() + [{"at": time.time(), "who": who, "text": text[:MAX_CHARS]}]
        STORE.parent.mkdir(parents=True, exist_ok=True)
        STORE.write_text(json.dumps(lines[-MAX_LINES:], ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def recent(now: float | None = None) -> list[dict]:
    horizon = (now or time.time()) - KEEP_HOURS * 3600
    return [line for line in _load() if float(line.get("at") or 0) >= horizon]


def prompt_block(now: float | None = None) -> str:
    """Yeni oturumun sistem komutuna giren blok; konuşma yoksa boş."""
    lines = recent(now)
    if not lines:
        return ""
    body = "\n".join(
        f"{time.strftime('%H:%M', time.localtime(float(line['at'])))} {line['who']}: {line['text']}" for line in lines
    )
    return (
        "[ÖNCEKİ KONUŞMA]\n"
        "Bu yeni bir oturum ama aynı asistansın ve son konuşmayı hatırlıyorsun (en eskisi üstte). Kullanıcı "
        "\"onu\", \"şunu da ekle\", \"devam et\", \"az önceki\" derse buradan anla; baştan sorma, konuyu yeniden "
        "açıklatma. Bu konuşmayı kendiliğinden özetleme ya da okuma.\n" + body
    )
