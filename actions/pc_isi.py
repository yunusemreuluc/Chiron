"""PC'de iş — sesli Chiron'un Komuta'ya iş vermesi (2026-10-29).

Kullanıcı: "telefonda iş verince yapmıyordu; aynı şey PC'de de öyle değil mi" — evet, PC'deki sesli Chiron'un
iş verme aracı hiç yoktu ("Dilcep'te şunu yap" deyince yapacak aracı yoktu). Telefondaki `delegate_to_claude`'un
PC karşılığı: iş Komuta'daki son Claude sohbetine yazılır (aynı oturum sürer), ekranda Komuta'da görünür.

Backend'e HTTP ile gidiyor, `backend.core.sohbet`'i import ETMİYOR: ses döngüsü backend'siz de çalışabiliyor
ve import ikinci bir iş kuyruğu kurar — o da diskteki süren işleri "yarıda kaldı" diye işaretlerdi.
"""

from __future__ import annotations

import requests

from actions.tool_result import fail, ok
from backend.core.config import PORT
from core.tool_registry import register_tool

KOMUTA_URL = f"http://127.0.0.1:{PORT}/api/remote/komuta"
MAX_TASK_CHARS = 4000


@register_tool("delegate_to_pc")
def delegate_to_pc(task: str = "", new_topic: bool = False) -> dict:
    task = (task or "").strip()
    if not task:
        return fail("Yapılacak iş boş.")
    if len(task) > MAX_TASK_CHARS:
        return fail(f"İş en fazla {MAX_TASK_CHARS} karakter olabilir.")
    try:
        response = requests.post(KOMUTA_URL, json={"text": task, "new_topic": bool(new_topic)}, timeout=15)
        data = response.json()
    except Exception as error:  # backend kapalı, port meşgul…
        return fail(f"İş verilemedi: Chiron'un arka ucuna ulaşılamadı ({error.__class__.__name__}).")
    if not data.get("success"):
        return fail(
            (data.get("message") or "İş alınmadı.")
            + " Önceki iş sürüyorsa kullanıcıya söyle; ilgisiz yeni bir işse new_topic=true ile tekrar dene."
        )
    info = data.get("data") or {}
    return ok("İş başladı; Komuta ekranında adım adım görünüyor.", chat=info.get("title"), job_id=info.get("job_id"))
