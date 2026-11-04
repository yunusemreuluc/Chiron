"""Onay uçları — Claude Code izin sorusuna Chiron'dan cevap (backend/core/onay.py).

`/istek` ve `/bekle` yalnız yerel hook içindir (uzak istemci PIN'siz giremez; telefon kararı `/karar` ile verir).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend.core.onay import broker
from backend.core.remote_auth import is_remote_scope

router = APIRouter(prefix="/api/onay", tags=["onay"])


class Decision(BaseModel):
    behavior: str = Field(pattern="^(izin|red|terminal)$")
    message: str = Field(default="", max_length=2000)
    always: bool = False
    by: str = Field(default="ekran", max_length=20)


def _ok(data: dict | list) -> dict:
    return {"success": True, "message": "", "data": data}


def _err(msg: str) -> dict:
    return {"success": False, "message": msg, "data": {}}


@router.post("/istek")
async def add_request(request: Request) -> dict:
    # İstek yalnız bu makinedeki hook'tan gelir; uzaktan sahte izin sorusu açılamasın.
    if is_remote_scope(request.scope):
        return _err("Yalnız yerel.")
    payload = await request.json()
    try:
        return _ok(broker.add(payload if isinstance(payload, dict) else {}))
    except ValueError as error:
        return _err(str(error))


@router.get("/{rid}/bekle")
async def wait(rid: str, request: Request, s: float = 25.0) -> dict:
    if is_remote_scope(request.scope):
        return _err("Yalnız yerel.")
    return _ok(await asyncio.to_thread(broker.wait, rid, s))


@router.post("/{rid}/vazgec")
async def cancel(rid: str, request: Request) -> dict:
    if is_remote_scope(request.scope):
        return _err("Yalnız yerel.")
    broker.cancel(rid)
    return _ok({})


@router.post("/{rid}/karar")
async def decide(rid: str, body: Decision) -> dict:
    ok, why = broker.decide(rid, body.behavior, body.message, body.always, body.by)
    return {"success": ok, "message": why or "Karar iletildi.", "data": {}}


@router.get("/haber")
async def news(request: Request) -> dict:
    """Ses döngüsü için yeni gelen onaylar (bir kez). Yalnız yerel: haber kuyruğunu telefon boşaltmasın."""
    if is_remote_scope(request.scope):
        return _err("Yalnız yerel.")
    return _ok({"items": broker.pop_news()})


@router.get("")
async def pending() -> dict:
    return _ok({"items": broker.pending()})
