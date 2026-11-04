"""Ajan Ofisi uçları — salt-okunur (Faz A).

Durum `backend/core/ofis.py`'de kuruluyor; burası yalnızca okur. Canlı güncelleme
WebSocket'teki `office_update` olayıyla gider, ayrıntı (bir ajanın tam akışı,
bir masanın geçmişi) buradan istenir. Uzak istemci için RemoteAccessMiddleware
kapısı geçerli (bütün /api/ yolları PIN'li).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from backend.core import gozetim
from backend.core.ofis import office

router = APIRouter(prefix="/api/office", tags=["office"])


class EndRunaway(BaseModel):
    create_time: float


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


@router.get("/workers/{worker_id:path}")
async def worker(worker_id: str) -> dict:
    detail = office.worker_detail(worker_id)
    return _ok(detail) if detail is not None else _missing("Ajan")


@router.get("/desks/{desk_id}")
async def desk(desk_id: str) -> dict:
    detail = office.desk_detail(desk_id)
    return _ok(detail) if detail is not None else _missing("Masa")
