"""Ajan Ofisi uçları — salt-okunur (Faz A).

Durum `backend/core/ofis.py`'de kuruluyor; burası yalnızca okur. Canlı güncelleme
WebSocket'teki `office_update` olayıyla gider, ayrıntı (bir ajanın tam akışı,
bir masanın geçmişi) buradan istenir. Uzak istemci için RemoteAccessMiddleware
kapısı geçerli (bütün /api/ yolları PIN'li).
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.core.ofis import office

router = APIRouter(prefix="/api/office", tags=["office"])


def _ok(data: dict) -> dict:
    return {"success": True, "message": "", "data": data}


def _missing(what: str) -> dict:
    return {"success": False, "message": f"{what} bulunamadı.", "data": {}}


@router.get("/state")
async def state() -> dict:
    return _ok(office.snapshot())


@router.get("/workers/{worker_id:path}")
async def worker(worker_id: str) -> dict:
    detail = office.worker_detail(worker_id)
    return _ok(detail) if detail is not None else _missing("Ajan")


@router.get("/desks/{desk_id}")
async def desk(desk_id: str) -> dict:
    detail = office.desk_detail(desk_id)
    return _ok(detail) if detail is not None else _missing("Masa")
