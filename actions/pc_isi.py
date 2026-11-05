"""PC'de iş — sesli Chiron'un Komuta'ya iş vermesi (2026-10-29).

Kullanıcı: "telefonda iş verince yapmıyordu; aynı şey PC'de de öyle değil mi" — evet, PC'deki sesli Chiron'un
iş verme aracı hiç yoktu ("Dilcep'te şunu yap" deyince yapacak aracı yoktu). Telefondaki `delegate_to_claude`'un
PC karşılığı: iş Komuta'daki son Claude sohbetine yazılır (aynı oturum sürer), ekranda Komuta'da görünür.

Bitince sesli haber: iş kimliği `_pending`'e girer, main.py `_watch_pc_jobs` 10 sn'de bir `finished_announcements()`
ile bakar ve sonucu proaktif sistem mesajı olarak Gemini'ye verir.

Backend'e HTTP ile gidiyor, `backend.core.sohbet`'i import ETMİYOR: ses döngüsü backend'siz de çalışabiliyor
ve import ikinci bir iş kuyruğu kurar — o da diskteki süren işleri "yarıda kaldı" diye işaretlerdi.
"""

from __future__ import annotations

import threading
import time

import requests

from actions.tool_result import fail, ok
from backend.core.config import PORT
from core.tool_registry import register_tool

KOMUTA_URL = f"http://127.0.0.1:{PORT}/api/remote/komuta"
STATUS_URL = f"http://127.0.0.1:{PORT}/api/remote/komuta/durum"
JOB_URL =f"http://127.0.0.1:{PORT}/api/remote/claude/{{job_id}}"
MAX_TASK_CHARS = 4000
SUMMARY_CHARS = 600
FINISHED = ("done", "needs_approval", "failed", "timeout", "interrupted", "cancelled")

# Sesle verilmiş, sonucu henüz söylenmemiş işler (2026-10-29, "PC'de de bitince sesli haber versin").
# Yalnız bu süreçte, bellekte: Chiron yeniden başlarsa söylenmemiş sonuç Komuta'da kalır.
_pending: set[str] = set()
_lock = threading.Lock()

# Sohbet kutusuna son eklenen görseller (main._on_text_command): bu süre içinde verilen PC işine eklenir.
IMAGE_TTL = 10 * 60
_images: list[str] = []
_images_at = 0.0


def remember_images(names: list[str]) -> None:
    global _images, _images_at
    with _lock:
        _images = list(names)[:4]
        _images_at = time.time()


def _take_images() -> list[str]:
    """Son görselleri bir kez verir (ikinci iş aynı görseli yeniden taşımaz)."""
    global _images
    with _lock:
        names = _images if time.time() - _images_at <= IMAGE_TTL else []
        _images = []
    return names


def finished_announcements() -> list[str]:
    """Biten işler için Gemini'ye verilecek sistem mesajları; söylenenler listeden düşer.
    Ağ çağrısı yapar — ses döngüsünde `asyncio.to_thread` ile çağrılır (main.py _watch_pc_jobs)."""
    with _lock:
        ids = list(_pending)
    messages = []
    for job_id in ids:
        try:
            job = (requests.get(JOB_URL.format(job_id=job_id), timeout=5).json() or {}).get("data") or {}
        except Exception:
            continue  # backend geçici yok: sonraki turda
        status = job.get("status")
        if status not in FINISHED:
            if not job:
                with _lock:
                    _pending.discard(job_id)  # iş kaydı yok (silinmiş/kırpılmış): sonsuza dek sorma
            continue
        with _lock:
            _pending.discard(job_id)
        if status == "cancelled":
            continue  # kullanıcı durdurdu; haber gereksiz
        summary = " ".join(str(job.get("summary") or job.get("error") or "").split())[:SUMMARY_CHARS]
        if status == "done":
            hint = "İş bitti. Kendi yaptığın iş gibi birinci ağızdan, kısa ve sade söyle ('Hallettim, ...')."
        elif status == "needs_approval":
            hint = (f"İş geri alınamayan bir adımda durdu: {job.get('approval') or 'onay gerekiyor'}. Ne yapacağını söyle ve "
                    "onayı Komuta ekranından vermesini iste.")
        else:
            hint = "İş tamamlanamadı. Ne olduğunu tek cümlede söyle."
        messages.append(f"[SİSTEM] PC işi sonucu (kullanıcının sözü değil). {hint} Claude'dan söz etme. Özet: {summary}")
    return messages


@register_tool("check_pc_job")
def check_pc_job() -> dict:
    """"İş ne durumda?" (2026-10-30): [SÜREN İŞ] yalnız oturum açılırken giriyor, iş sürerken sorulunca canlı
    durum buradan. Salt okuma; işi durdurmaz, değiştirmez."""
    try:
        data = requests.get(STATUS_URL, timeout=5).json() or {}
    except Exception as error:
        return fail(f"İş durumu alınamadı: Chiron'un arka ucuna ulaşılamadı ({error.__class__.__name__}).")
    text = str((data.get("data") or {}).get("metin") or "")
    if not text:
        return ok("Süren ya da son üç günde verilmiş bir PC işi yok.", busy=False)
    return ok(text + " Bunu kısa ve kendi işin gibi söyle; adım ayrıntısını yalnız sorulursa oku.")


@register_tool("delegate_to_pc")
def delegate_to_pc(task: str = "", new_topic: bool = False) -> dict:
    task = (task or "").strip()
    if not task:
        return fail("Yapılacak iş boş.")
    if len(task) > MAX_TASK_CHARS:
        return fail(f"İş en fazla {MAX_TASK_CHARS} karakter olabilir.")
    try:
        body: dict = {"text": task, "new_topic": bool(new_topic)}
        images = _take_images()
        if images:
            body["images"] = images
        response = requests.post(KOMUTA_URL, json=body, timeout=15)
        data = response.json()
    except Exception as error:  # backend kapalı, port meşgul…
        return fail(f"İş verilemedi: Chiron'un arka ucuna ulaşılamadı ({error.__class__.__name__}).")
    if not data.get("success"):
        return fail(
            (data.get("message") or "İş alınmadı.")
            + " Önceki iş sürüyorsa kullanıcıya söyle; ilgisiz yeni bir işse new_topic=true ile tekrar dene."
        )
    info = data.get("data") or {}
    if info.get("job_id"):
        with _lock:
            _pending.add(str(info["job_id"]))
    return ok("İş başladı; Komuta ekranında adım adım görünüyor.", chat=info.get("title"), job_id=info.get("job_id"))
