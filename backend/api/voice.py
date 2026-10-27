from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.core import commands

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
    text: str


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
    if not text:
        return {"success": False, "message": "boş metin", "data": {}}
    remote = bool(getattr(request.state, "remote", False))
    commands.dispatch("remote_mode", {"value": remote, "quiet_if_unchanged": True})
    if not commands.dispatch("text", {"text": text}):
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


@router.post("/reset")
async def reset_session() -> dict:
    """Sohbet bağlamını sıfırlar — yeni, boş bağlamlı bir Gemini Live oturumu."""
    if not commands.dispatch("reset", {}):
        return {"success": False, "message": "Sesli asistan çalışmıyor.", "data": {}}
    return {"success": True, "message": "oturum sıfırlanıyor", "data": {}}
