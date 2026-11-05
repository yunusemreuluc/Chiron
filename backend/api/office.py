"""Ajan Ofisi uçları — salt-okunur (Faz A).

Durum `backend/core/ofis.py`'de kuruluyor; burası yalnızca okur. Canlı güncelleme
WebSocket'teki `office_update` olayıyla gider, ayrıntı (bir ajanın tam akışı,
bir masanın geçmişi) buradan istenir. Uzak istemci için RemoteAccessMiddleware
kapısı geçerli (bütün /api/ yolları PIN'li).
"""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter
from typing import Literal

from pydantic import BaseModel, Field

from backend.core import gozetim, oturum_kontrol
from backend.core.ofis import LEFT, office

router = APIRouter(prefix="/api/office", tags=["office"])


class EndRunaway(BaseModel):
    create_time: float


class AskSession(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=12)


class EndSession(BaseModel):
    mode: Literal["devam", "sil"]


def _ok(data: dict) -> dict:
    return {"success": True, "message": "", "data": data}


def _missing(what: str) -> dict:
    return {"success": False, "message": f"{what} bulunamadı.", "data": {}}


@router.get("/state")
async def state() -> dict:
    return _ok(office.snapshot())


@router.get("/gozetim")
async def gozetim_view() -> dict:
    """Gözetim sekmesi: canlı oturumlar + token/maliyet + kaçak süreçler (backend/core/gozetim.py)."""
    return _ok(await asyncio.to_thread(gozetim.view))


@router.get("/gozetim/yorunge")
async def gozetim_orbit() -> dict:
    """3D yörüngenin ekleri (bağlam halkası, arka plan işleri, dev sunucular, kaçak süreç, onay) — hafif."""
    return _ok(await asyncio.to_thread(gozetim.orbit_view))


@router.get("/gozetim/son-cevap/{worker_id:path}")
async def gozetim_last_reply(worker_id: str) -> dict:
    w = office.workers.get(worker_id)
    if w is None or w.kind != "chief":
        return _missing("Oturum")
    text = await asyncio.to_thread(gozetim.last_reply, w.transcript_path)
    return _ok({"text": text})


@router.post("/gozetim/kacak/{pid}/sonlandir")
async def gozetim_end_runaway(pid: int, body: EndRunaway) -> dict:
    ok, why = await asyncio.to_thread(gozetim.runaways.end, pid, body.create_time)
    return {"success": ok, "message": why or "Süreç ağacıyla sonlandırıldı.", "data": {}}


def _chief(worker_id: str):
    w = office.workers.get(worker_id)
    return w if w is not None and w.kind == "chief" else None


@router.post("/gozetim/sor/{worker_id:path}")
async def gozetim_ask(worker_id: str, body: AskSession) -> dict:
    """Oturuma dokunmadan "ne yapıyorsun?" — kaydın özetiyle ayrı bir yan sorgu (oturum_kontrol.ask)."""
    w = _chief(worker_id)
    if w is None:
        return _missing("Oturum")
    project = gozetim._project(w)
    try:
        answer = await asyncio.to_thread(
            oturum_kontrol.ask, w.transcript_path, project, body.question.strip(), body.history)
    except Exception as e:  # zaman aşımı, claude yok, kayıt yok
        return {"success": False, "message": str(e) or "Cevap alınamadı.", "data": {}}
    return _ok({"answer": answer})


QUIET_S = 10 * 60


@router.get("/gozetim/geri-al/{worker_id:path}")
async def gozetim_revert_plan(worker_id: str) -> dict:
    """Sonlandır → "yapılanları sil" seçilmeden önce: hangi dosya eski haline döner, hangisi silinir."""
    w = _chief(worker_id)
    if w is None:
        return _missing("Oturum")
    p = await asyncio.to_thread(oturum_kontrol.plan, w.session_id, w.transcript_path)
    alive = await asyncio.to_thread(oturum_kontrol.alive, w.hook_ppid, w.hook_ppid_ts, w.session_id)
    return _ok({**p, "alive": alive})


@router.post("/gozetim/sonlandir/{worker_id:path}")
async def gozetim_end_session(worker_id: str, body: EndSession) -> dict:
    """Oturumu kapatır. devam: değişiklikler kalır, kayıt Komuta'da sürdürülebilir.
    sil: kapattıktan sonra dosyalar oturum öncesine döner (şimdiki halleri geri-alinan/'a kopyalanır)."""
    w = _chief(worker_id)
    if w is None:
        return _missing("Oturum")
    already_left = w.status == LEFT
    recent = time.time() - (w.last_ts or w.started) < QUIET_S
    state, why = await asyncio.to_thread(oturum_kontrol.stop, w.hook_ppid, w.hook_ppid_ts, w.session_id)
    if state == oturum_kontrol.FAILED:
        return {"success": False, "message": why, "data": {}}
    if state == oturum_kontrol.NOT_FOUND and recent and not already_left:
        # Bulunamamak kapalı olmak demek değil: oturum yaşıyor ve yazıyor olabilir.
        return {"success": False, "data": {},
                "message": "Oturumun süreci bulunamadı ama son 10 dakikada çalışmış — açık olabilir. "
                           "Hiçbir şeye dokunulmadı; terminalden kapatıp yeniden dene."}
    # Öldürülen süreç SessionEnd hook'u gönderemez — Gözetim onu 6 saat canlı sanmasın.
    if w.session_id and not already_left:
        office.apply({"event": "SessionEnd", "session_id": w.session_id, "source": "chiron-sonlandir"})
    if body.mode == "devam":
        return {"success": True, "message": why, "data": {"stopped": True}}
    if await asyncio.to_thread(oturum_kontrol.alive, w.hook_ppid, w.hook_ppid_ts, w.session_id):
        return {"success": False, "message": "Oturum kapanmadı, dosyalara dokunulmadı.", "data": {}}
    if not w.session_id or not w.transcript_path:
        return {"success": False, "message": "Kaydı olmayan oturum geri alınamaz.", "data": {}}
    res = await asyncio.to_thread(oturum_kontrol.apply, w.session_id, w.transcript_path)
    return {"success": res["hata"] == 0, "message": "; ".join(res["errors"]), "data": {"stopped": True, **res}}


@router.get("/workers/{worker_id:path}")
async def worker(worker_id: str) -> dict:
    detail = office.worker_detail(worker_id)
    return _ok(detail) if detail is not None else _missing("Ajan")


@router.get("/desks/{desk_id}")
async def desk(desk_id: str) -> dict:
    detail = office.desk_detail(desk_id)
    return _ok(detail) if detail is not None else _missing("Masa")
