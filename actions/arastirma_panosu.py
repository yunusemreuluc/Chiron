"""Araştırma panosu — "şunu araştır" → arka planda kaynaklı araştırma → ekranda kart ızgarası (2026-11-01).

Neden: Yunus Instagram'da huwprosser'ın "ROSE" asistanını gördü (asistan araştırmayı arka planda yapıyor, ekranda
"RESEARCH // ACTIVE" kartı, bitince "göster" deyince metin/grafik/rakam/video kartlarından oluşan bir pano açılıyor):
"biz de yapabilir miyiz". İşin özü gösteriş değil, araştırmanın düz metin değil BLOK (yapılandırılmış veri) olarak
dönmesi; arayüz blokları çiziyor.

Akış:
    research_board(topic)  → iş parçacığı başlar, araç hemen döner ("başladım")
        Claude CLI (-p, yalnız WebSearch/WebFetch) → stream-json olaylarından canlı ilerleme (arama/okuma sayısı)
        son mesaj = blok JSON'u → temizlenir → yt-dlp ile gerçek YouTube videoları eklenir → diske yazılır
        her adımda `research_update` olayı (arayüzdeki ilerleme kartı)
    bitince main.py `_watch_research` sesli haber verir ("hazır, göstereyim mi?")
    show_research_board()  → `research_show` olayı + pencere tepsideyse öne gelir

Motor neden Gemini değil Claude: 2026-11-01'de denendi — Gemini'nin Google arama bağlaması bu hesapta 429 (kota),
bağlamayı kabul eden tek model (2.5-flash-lite) aramayı hiç yapmadı (0 kaynak) ve kaynaksız "35,9 milyon" uydurdu.
Kaynaksız rakamla pano kurmak arayüzde dürüstlük kuralına aykırı (Bilinen-Tuzaklar § Arayüzde dürüstlük).
Claude CLI WebSearch ile aynı soru 9 sn, ~$0.02, kaynaklı cevap verdi.

Görsel kart yok: araştırma metninden gelen görsel adresleri doğrulanamıyor; görsel yerine gerçek YouTube videoları
(yt-dlp arama, küçük resimleri YouTube'un kendi sunucusundan) kullanılıyor.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from actions.tool_result import fail, ok
from core.tool_registry import register_tool

logger = logging.getLogger("chiron")

BOARD_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Chiron" / "arastirma"
LAST_FILE = BOARD_DIR / "son.json"

MODEL = "sonnet"  # araştırma + JSON yazımı; mimari karar değil, pahalı modele gerek yok
TIMEOUT_SECONDS = 420
MAX_TOPIC_CHARS = 300

# Temizlik sınırları — model çıktısı arayüze girmeden önce kırpılır (çıktı web içeriğinden besleniyor).
MAX_BLOCKS = 14
MAX_CHART_ITEMS = 8
MAX_SOURCES = 40
MAX_VIDEO_QUERIES = 3
VIDEOS_PER_QUERY = 1
TEXT_LIMITS = {"title": 90, "body": 700, "value": 24, "label": 110, "note": 220, "unit": 20}
BLOCK_TYPES = ("text", "stat", "chart")
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

PROMPT = """Bir masaüstü asistanının araştırma panosu için araştırma yapıyorsun. Konu: {topic}
{focus}
WebSearch ile birden fazla arama yap, gerektiğinde WebFetch ile kaynağı oku. Güncel ve rakamlı bilgiye öncelik ver.
Bulamadığın rakamı UYDURMA: kaynağı olmayan sayı yazma; tahminse "tahmin" de.

Son mesajın YALNIZCA tek bir JSON nesnesi olsun (açıklama, markdown, ``` yok). Tüm metinler Türkçe. Şema:
{{
  "title": "panonun kısa başlığı (ör. VR'ın Durumu)",
  "summary": "sesli okunacak 2 cümlelik özet",
  "blocks": [
    {{"type": "text", "title": "...", "body": "2-4 cümle", "source": 1}},
    {{"type": "stat", "value": "≈20 milyon", "label": "neyin rakamı", "note": "kısa bağlam", "source": 2}},
    {{"type": "chart", "title": "...", "unit": "milyon", "items": [{{"label": "2023", "value": 7.5}}], "note": "...", "source": 3}}
  ],
  "video_queries": ["YouTube'da aranacak 1-3 İngilizce sorgu"],
  "sources": [{{"title": "kaynak adı", "url": "https://..."}}]
}}
Kurallar: 8-12 blok; en az 2 "stat" ve en az 1 "chart" (yalnız gerçekten karşılaştırılabilir sayılar varsa).
"source" sources listesindeki 1'den başlayan sıra numarası. chart value'ları düz sayı (metin değil)."""

_lock = threading.Lock()
_running: dict[str, Any] | None = None  # {id, topic, proc}
# Sesle başlatılmış, sonucu henüz söylenmemiş araştırmalar — main.py `_watch_research` alır.
_announcements: list[str] = []


# ── Yayın ────────────────────────────────────────────────────────────────────
def _emit(event: str, data: dict[str, Any]) -> None:
    """Arayüze olay — ses döngüsü ile backend aynı süreçte (bkz. core/web_ui.py). Asla patlamaz."""
    try:
        from backend.models.events import WSEvent
        from backend.websocket.manager import manager

        manager.broadcast_threadsafe(WSEvent(event=event, data=data))  # type: ignore[arg-type]
    except Exception:
        logger.debug("[ARAŞTIRMA] olay yayınlanamadı: %s", event, exc_info=True)


def _write_board(board: dict[str, Any]) -> None:
    BOARD_DIR.mkdir(parents=True, exist_ok=True)
    tmp = LAST_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(board, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, LAST_FILE)


def last_board() -> dict[str, Any] | None:
    """Son pano (bitmiş ya da hata) — arayüz yeniden açılınca buradan yükler."""
    try:
        data = json.loads(LAST_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def pop_announcements() -> list[str]:
    with _lock:
        items = list(_announcements)
        _announcements.clear()
    return items


# ── Model çıktısını temizleme ────────────────────────────────────────────────
def _text(value: Any, key: str) -> str:
    text = " ".join(str(value or "").split())
    limit = TEXT_LIMITS[key]
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _source_ref(value: Any, count: int) -> int | None:
    try:
        index = int(value)
    except (TypeError, ValueError):
        return None
    return index if 1 <= index <= count else None


def _clean_block(raw: Any, source_count: int) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or raw.get("type") not in BLOCK_TYPES:
        return None
    kind = raw["type"]
    block: dict[str, Any] = {"type": kind, "source": _source_ref(raw.get("source"), source_count)}
    if kind == "text":
        block.update(title=_text(raw.get("title"), "title"), body=_text(raw.get("body"), "body"))
        return block if block["body"] else None
    if kind == "stat":
        block.update(value=_text(raw.get("value"), "value"), label=_text(raw.get("label"), "label"),
                     note=_text(raw.get("note"), "note"))
        return block if block["value"] and block["label"] else None
    items = []
    for item in (raw.get("items") or [])[:MAX_CHART_ITEMS]:
        if not isinstance(item, dict):
            continue
        try:
            number = float(item.get("value"))
        except (TypeError, ValueError):
            continue
        if number != number or number < 0:  # NaN / eksi: çubuk grafikte anlamsız
            continue
        items.append({"label": _text(item.get("label"), "label"), "value": number})
    if len(items) < 2:
        return None  # tek çubuklu grafik rakam kartıdır, grafik değil
    block.update(title=_text(raw.get("title"), "title"), unit=_text(raw.get("unit"), "unit"),
                 note=_text(raw.get("note"), "note"), items=items)
    return block


def _parse_result(text: str) -> dict[str, Any]:
    """Son mesajdaki JSON nesnesi. Model bazen ``` ile sarar ya da önüne cümle ekler — ilk { ile son } arası."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Araştırma sonucu JSON değil.")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("Araştırma sonucu JSON nesnesi değil.")
    return data


def clean_board(data: dict[str, Any]) -> dict[str, Any]:
    sources = []
    for item in (data.get("sources") or [])[:MAX_SOURCES]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url.startswith(("https://", "http://")):
            url = ""
        sources.append({"title": _text(item.get("title") or url, "label"), "url": url})
    blocks = [b for b in (_clean_block(raw, len(sources)) for raw in (data.get("blocks") or [])) if b][:MAX_BLOCKS]
    queries = [_text(q, "label") for q in (data.get("video_queries") or []) if str(q or "").strip()]
    return {
        "title": _text(data.get("title"), "title"),
        "summary": _text(data.get("summary"), "body"),
        "blocks": blocks,
        "sources": sources,
        "video_queries": queries[:MAX_VIDEO_QUERIES],
    }


# ── Videolar ─────────────────────────────────────────────────────────────────
def _find_videos(queries: list[str]) -> list[dict[str, Any]]:
    """yt-dlp arama — yalnız liste (extract_flat), video indirilmez. Ölçüldü: 3 sonuç 1.6 sn."""
    try:
        import yt_dlp  # ağır modül: yalnız burada (bkz. video_analysis.py HAS_YTDLP notu)
    except ImportError:
        return []
    videos: list[dict[str, Any]] = []
    seen: set[str] = set()
    options = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True}
    for query in queries:
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                result = ydl.extract_info(f"ytsearch{VIDEOS_PER_QUERY + 1}:{query}", download=False) or {}
        except Exception:
            logger.debug("[ARAŞTIRMA] video araması başarısız: %s", query, exc_info=True)
            continue
        added = 0
        for entry in result.get("entries") or []:
            video_id = str((entry or {}).get("id") or "")
            if not VIDEO_ID.match(video_id) or video_id in seen or added >= VIDEOS_PER_QUERY:
                continue
            seen.add(video_id)
            added += 1
            duration = entry.get("duration")
            videos.append({
                "type": "video",
                "video_id": video_id,
                "title": _text(entry.get("title"), "label"),
                "channel": _text(entry.get("channel") or entry.get("uploader"), "title"),
                "duration": int(duration) if isinstance(duration, (int, float)) else None,
                "source": None,
            })
    return videos


# ── Claude motoru ────────────────────────────────────────────────────────────
def _claude_exe() -> str | None:
    from backend.core.claude_jobs import find_claude_exe

    return find_claude_exe()


def _run_claude(board_id: str, topic: str, focus: str, progress: dict[str, Any], prompt: str | None = None,
                emit: bool = True) -> str:
    """`prompt` + `emit=False`: aynı motor panosuz (actions/ogrenme.py); ilerleme kartı açılmaz."""
    exe = _claude_exe()
    if not exe:
        raise RuntimeError("Claude bulunamadı, araştırma yapılamıyor.")
    prompt = prompt or PROMPT.format(topic=topic, focus=f"Özellikle: {focus}" if focus else "")
    args = [
        exe, "-p", "--model", MODEL,
        # Yalnız web: dosya/kabuk aracı yok — çıktı web içeriğinden besleniyor, araç kapısı dar tutulur.
        "--tools", "WebSearch,WebFetch", "--allowedTools", "WebSearch,WebFetch",
        # Kullanıcı ayarları (global hook'lar, bellek enjeksiyonu) bu iş için gereksiz; MCP sunucuları da.
        "--setting-sources", "project", "--strict-mcp-config",
        "--output-format", "stream-json", "--verbose",
    ]
    workdir = tempfile.mkdtemp(prefix="chiron-arastirma-")
    proc = subprocess.Popen(
        args, cwd=workdir, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    with _lock:
        if _running and _running["id"] == board_id:
            _running["proc"] = proc
    timer = threading.Timer(TIMEOUT_SECONDS, _kill, args=(proc,))
    timer.start()
    result_text, error = "", ""
    try:
        assert proc.stdin and proc.stdout
        proc.stdin.write(prompt)
        proc.stdin.close()
        for line in proc.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            kind = event.get("type")
            if kind == "assistant":
                for part in (event.get("message") or {}).get("content") or []:
                    if part.get("type") == "tool_use":
                        name = part.get("name")
                        tool_input = part.get("input") or {}
                        if name == "WebSearch":
                            progress["searches"] += 1
                            progress["step"] = _text(f"Arıyor: {tool_input.get('query') or ''}", "label")
                        else:
                            progress["reads"] += 1
                            site = urlparse(str(tool_input.get("url") or "")).netloc.removeprefix("www.")
                            progress["step"] = _text(f"Okuyor: {site}", "label")
                        if emit:
                            _emit_progress(board_id, topic, progress)
            elif kind == "result":
                result_text = str(event.get("result") or "")
                if event.get("is_error") or event.get("subtype") != "success":
                    error = result_text or str(event.get("subtype") or "hata")
        proc.wait(timeout=30)
    finally:
        timer.cancel()
        # Boş çalışma klasörü her araştırmada Temp'te birikiyordu (2026-11-01 performans taraması: 2 adet).
        shutil.rmtree(workdir, ignore_errors=True)
    if progress.get("cancelled"):
        raise RuntimeError("Araştırma durduruldu.")
    if error:
        raise RuntimeError(f"Araştırma tamamlanamadı: {error[:200]}")
    if not result_text:
        raise RuntimeError("Araştırma süre sınırına takıldı ya da sonuç vermedi.")
    return result_text


def _kill(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    # Ağaç: claude.exe kendi alt süreçlerini açabilir (bkz. hafıza: TaskStop alt süreçleri öldürmüyor).
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _emit_progress(board_id: str, topic: str, progress: dict[str, Any]) -> None:
    _emit("research_update", {
        "id": board_id, "topic": topic, "status": "running", "phase": progress["phase"],
        "searches": progress["searches"], "reads": progress["reads"], "step": progress.get("step", ""),
        "started_at": progress["started_at"],
    })


def _worker(board_id: str, topic: str, focus: str, progress: dict[str, Any]) -> None:
    global _running
    _emit_progress(board_id, topic, progress)
    try:
        raw = _run_claude(board_id, topic, focus, progress)
        progress.update(phase="building", step="")
        _emit_progress(board_id, topic, progress)
        board = clean_board(_parse_result(raw))
        if not board["blocks"]:
            raise RuntimeError("Araştırmadan gösterilecek blok çıkmadı.")
        board["blocks"] += _find_videos(board.pop("video_queries"))
        board.update(id=board_id, topic=topic, status="done", searches=progress["searches"],
                     reads=progress["reads"], started_at=progress["started_at"], finished_at=time.time())
        board["title"] = board["title"] or topic
        _write_board(board)
        _emit("research_update", board)
        message = (
            f"[SİSTEM] Arka plandaki araştırma bitti (kullanıcının sözü değil): \"{board['title']}\", "
            f"{len(board['blocks'])} blok, {len(board['sources'])} kaynak. Özet: {board['summary']} "
            "Bittiğini tek cümleyle söyle ve panoda göstermemi ister misin diye sor. Evet derse show_research_board çağır."
        )
    except Exception as exc:
        logger.warning("[ARAŞTIRMA] %s: %s", topic, exc)
        reason = str(exc) if isinstance(exc, (RuntimeError, ValueError)) else "beklenmeyen hata"
        _emit("research_update", {"id": board_id, "topic": topic, "status": "error", "error": reason,
                                  "started_at": progress["started_at"]})
        message = "" if progress.get("cancelled") else (
            f"[SİSTEM] Arka plandaki araştırma tamamlanamadı (kullanıcının sözü değil): {reason} Tek cümleyle söyle."
        )
    with _lock:
        _running = None
        if message:
            _announcements.append(message)


# ── Araçlar ──────────────────────────────────────────────────────────────────
@register_tool("research_board")
def research_board(topic: str = "", focus: str = "") -> dict:
    """Konuyu arka planda araştırır; bitince sesli haber gelir, sonuç panoda gösterilir."""
    global _running
    topic = " ".join(str(topic or "").split())[:MAX_TOPIC_CHARS]
    focus = " ".join(str(focus or "").split())[:MAX_TOPIC_CHARS]
    if not topic:
        return fail("Neyi araştırayım? Konu boş.")
    with _lock:
        if _running:
            return fail(f"Zaten bir araştırma sürüyor: {_running['topic']}. Bitince yenisini başlatırım.")
        board_id = uuid.uuid4().hex[:12]
        # `progress` paylaşılır: cancel_research bayrağı buraya yazar, iş parçacığı okur.
        progress: dict[str, Any] = {"phase": "searching", "searches": 0, "reads": 0, "started_at": time.time()}
        _running = {"id": board_id, "topic": topic, "proc": None, "progress": progress}
    threading.Thread(target=_worker, args=(board_id, topic, focus, progress), name="chiron-arastirma", daemon=True).start()
    return ok(
        f"Araştırma arka planda başladı: {topic}. Ekranda ilerleme kartı var; bitince haber vereceğim. "
        "Kullanıcıya kısa söyle, beklemesine gerek yok."
    )


@register_tool("show_research_board")
def show_research_board(show: bool = True) -> dict:
    """Son araştırma panosunu açar (pencere tepsideyse öne getirir) ya da kapatır."""
    if not show:
        _emit("research_show", {"open": False})
        return ok("Pano kapatıldı.")
    board = last_board()
    with _lock:
        running = _running["topic"] if _running else ""
    if not board and not running:
        return fail("Henüz bir araştırma yok. Önce bir konu araştırayım mı?")
    try:
        from backend.core import commands

        commands.dispatch("show_window", {})
    except Exception:
        logger.debug("[ARAŞTIRMA] pencere öne getirilemedi", exc_info=True)
    _emit("research_show", {"open": True})
    if running:
        return ok(f"Araştırma hâlâ sürüyor ({running}); panoda ilerlemesi görünüyor.")
    return ok(f"Pano ekranda: {board.get('title')}. Kısaca neler olduğunu söyle, kartları okuma.")


@register_tool("cancel_research")
def cancel_research() -> dict:
    with _lock:
        running = _running
        if running:
            running["progress"]["cancelled"] = True
    if not running:
        return fail("Süren bir araştırma yok.")
    proc = running.get("proc")
    if proc is not None:
        _kill(proc)
    return ok(f"Araştırma durduruldu: {running['topic']}.")
