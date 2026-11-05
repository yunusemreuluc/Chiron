from __future__ import annotations

import asyncio
import base64
import binascii

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend.core import commands
from backend.core.sohbet import SohbetError, sohbet

router = APIRouter(prefix="/api/voice", tags=["voice"])


@router.get("/status")
async def voice_status() -> dict:
    """Sesli asistan bu sürece bağlı mı ve komut alacak durumda mı?

    İki ayrı şey: `connected` — ses döngüsü bu süreçte çalışıyor; `ready` —
    Gemini Live oturumu gerçekten kuruldu. Oturum kurulmadan gönderilen komut
    kaybolur, bu yüzden arayüz yazma kutusunu `ready` olana kadar kilitliyor.
    """
    connected = commands.is_connected()
    ready = connected and commands.is_ready()
    return {
        "success": True,
        "message": "sesli asistan bağlı" if connected else "sesli asistan çalışmıyor",
        "data": {"connected": connected, "ready": ready, "commands": commands.known_commands()},
    }


class TextCommand(BaseModel):
    text: str = ""
    # Görseller (2026-11-04): data URL / base64. Gemini Live'a aynı turda inline_data olarak gider.
    images: list[str] = Field(default_factory=list, max_length=4)


@router.post("/text")
async def send_text(command: TextCommand, request: Request) -> dict:
    """Arayüzdeki yazı kutusundan gelen metin.

    ÖNEMLİ: Bu yol mikrofon olmadan da Chiron'la konuşmayı mümkün kılıyor —
    oturum `response_modalities=["AUDIO"]` olduğu için cevap SESLİ gelir.

    Uzak mod (2026-09-15): metin telefondan geliyorsa cevap boş evde PC
    hoparlöründen yüksek sesle ÇALMAMALI — uzak mod komuttan ÖNCE açılıyor.
    PC'nin kendi penceresinden yazılıyorsa kullanıcı masada demektir, uzak mod
    kapanıyor.
    """
    text = command.text.strip()
    if not text and not command.images:
        return {"success": False, "message": "boş metin", "data": {}}
    images = []
    for raw in command.images:
        body = raw.split(",", 1)[1] if raw.startswith("data:") else raw
        try:
            data = base64.b64decode(body, validate=True)
            path, mime = await asyncio.to_thread(sohbet.save_voice_image, data)
        except (binascii.Error, ValueError):
            return {"success": False, "message": "Görsel okunamadı.", "data": {}}
        except SohbetError as error:
            return {"success": False, "message": str(error), "data": {}}
        images.append({"path": str(path), "name": path.name, "mime": mime})
    remote = bool(getattr(request.state, "remote", False))
    commands.dispatch("remote_mode", {"value": remote, "quiet_if_unchanged": True})
    if not commands.dispatch("text", {"text": text, "images": images}):
        return {"success": False, "message": "Sesli asistan çalışmıyor.", "data": {}}
    return {"success": True, "message": "gönderildi", "data": {}}


class ToggleCommand(BaseModel):
    value: bool


@router.post("/mute")
async def set_mute(command: ToggleCommand) -> dict:
    if not commands.dispatch("mute", {"value": command.value}):
        return {"success": False, "message": "Sesli asistan çalışmıyor.", "data": {}}
    return {"success": True, "message": "güncellendi", "data": {"muted": command.value}}


@router.post("/pause")
async def set_pause(command: ToggleCommand) -> dict:
    if not commands.dispatch("pause", {"value": command.value}):
        return {"success": False, "message": "Sesli asistan çalışmıyor.", "data": {}}
    return {"success": True, "message": "güncellendi", "data": {"paused": command.value}}


@router.post("/humanoid")
async def set_humanoid(command: ToggleCommand) -> dict:
    """İnsan görünümü (H tuşu). Şıklatma aynı bayrağı backend içinden çeviriyor."""
    if not commands.dispatch("humanoid", {"value": command.value}):
        return {"success": False, "message": "Sesli asistan çalışmıyor.", "data": {}}
    return {"success": True, "message": "güncellendi", "data": {"humanoid": command.value}}


@router.post("/reset")
async def reset_session() -> dict:
    """Sohbet bağlamını sıfırlar — yeni, boş bağlamlı bir Gemini Live oturumu."""
    if not commands.dispatch("reset", {}):
        return {"success": False, "message": "Sesli asistan çalışmıyor.", "data": {}}
    return {"success": True, "message": "oturum sıfırlanıyor", "data": {}}
