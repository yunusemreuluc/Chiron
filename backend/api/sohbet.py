"""Sohbet uçları — Chiron'dan ajanla süren konuşma (Komuta ekranı, 2026-10-27).

Mantık `backend/core/sohbet.py`'de. Uzak istemci için RemoteAccessMiddleware kapısı geçerli
(bütün /api/ yolları PIN'li).
"""

from __future__ import annotations

import asyncio
from typing import Callable

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from backend.core.sohbet import MAX_TEXT, MAX_TITLE, SohbetError, sohbet

router = APIRouter(prefix="/api/sohbet", tags=["sohbet"])


def _ok(data: dict, message: str = "") -> dict:
    return {"success": True, "message": message, "data": data}


async def _run(response: Response, action: Callable[[], dict], message: str = "") -> dict:
    try:
        chat = await asyncio.to_thread(action)
    except SohbetError as error:
        response.status_code = 409
        return {"success": False, "message": str(error), "data": {}}
    return _ok({"chat": chat}, message)


class ChatCreate(BaseModel):
    agent: str = Field(default="claude", max_length=16)
    title: str = Field(default="", max_length=MAX_TITLE)
    cwd: str | None = Field(default=None, max_length=400)


class ChatMessage(BaseModel):
    text: str = Field(max_length=MAX_TEXT)


class ChatAnswer(BaseModel):
    approved: bool


class Takeover(BaseModel):
    session_id: str = Field(max_length=64)
    force: bool = False


@router.get("")
async def list_chats() -> dict:
    return _ok({"chats": await asyncio.to_thread(sohbet.list)})


@router.get("/terminal")
async def list_terminal_sessions() -> dict:
    """PC'deki son etkileşimli Claude Code oturumları — devralınabilecekler."""
    return _ok({"sessions": await asyncio.to_thread(sohbet.terminal_sessions)})


@router.post("/devral")
async def take_over(body: Takeover, response: Response) -> dict:
    return await _run(response, lambda: sohbet.takeover(body.session_id, body.force), "Oturum devralındı.")


@router.post("")
async def create_chat(body: ChatCreate, response: Response) -> dict:
    return await _run(response, lambda: sohbet.create(body.agent, body.title, body.cwd), "Sohbet açıldı.")


@router.get("/{chat_id}")
async def get_chat(chat_id: str, response: Response) -> dict:
    return await _run(response, lambda: sohbet.get(chat_id))


def _via(request: Request) -> str:
    # Uzak istemci = telefon (PIN oturumu). Sonucu telefona bildirilecek mi, buna bakılıyor.
    return "telefon" if getattr(request.state, "remote", False) else "pc"


@router.post("/{chat_id}/mesaj")
async def send_message(chat_id: str, body: ChatMessage, request: Request, response: Response) -> dict:
    via = _via(request)
    return await _run(response, lambda: sohbet.send(chat_id, body.text, via))


@router.post("/{chat_id}/onay")
async def answer(chat_id: str, body: ChatAnswer, request: Request, response: Response) -> dict:
    via = _via(request)
    return await _run(response, lambda: sohbet.answer(chat_id, body.approved, via))


@router.post("/{chat_id}/durdur")
async def stop(chat_id: str, response: Response) -> dict:
    return await _run(response, lambda: sohbet.stop(chat_id), "Durduruluyor.")


@router.delete("/{chat_id}")
async def delete_chat(chat_id: str, response: Response) -> dict:
    def action() -> dict:
        sohbet.delete(chat_id)
        return {"id": chat_id}

    return await _run(response, action, "Sohbet silindi.")
