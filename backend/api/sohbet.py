"""Sohbet uçları — Chiron'dan ajanla süren konuşma (Komuta ekranı, 2026-10-27).

Mantık `backend/core/sohbet.py`'de. Uzak istemci için RemoteAccessMiddleware kapısı geçerli
(bütün /api/ yolları PIN'li).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
from typing import Callable

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from backend.core.sohbet import MAX_IMAGE_BYTES, MAX_IMAGES, MAX_TEXT, MAX_TITLE, SohbetError, sohbet

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
    text: str = Field(default="", max_length=MAX_TEXT)
    images: list[str] = Field(default_factory=list, max_length=MAX_IMAGES)


class ImageUpload(BaseModel):
    data: str = Field(max_length=MAX_IMAGE_BYTES * 4 // 3 + 64)  # base64 (data: öneki olabilir)


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
    return await _run(response, lambda: sohbet.send(chat_id, body.text, via, body.images))


@router.post("/{chat_id}/ek")
async def upload_image(chat_id: str, body: ImageUpload, response: Response) -> dict:
    raw = body.data.split(",", 1)[1] if body.data.startswith("data:") else body.data
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        response.status_code = 400
        return {"success": False, "message": "Görsel okunamadı.", "data": {}}
    try:
        saved = await asyncio.to_thread(sohbet.save_image, chat_id, data)
    except SohbetError as error:
        response.status_code = 409
        return {"success": False, "message": str(error), "data": {}}
    return _ok(saved, "Görsel eklendi.")


@router.get("/{chat_id}/ek/{name}")
async def get_image(chat_id: str, name: str):
    try:
        path = sohbet.image_path(chat_id, name)
    except SohbetError as error:
        return JSONResponse({"success": False, "message": str(error), "data": {}}, status_code=404)
    return FileResponse(path, headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})


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
