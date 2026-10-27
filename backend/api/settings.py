"""Ayarlar — uygulamanın tüm kullanıcı ayarları tek yerde.

Kullanıcı isteğiyle (2026-07-29) eski penceredeki tüm ayarlar 3D arayüze taşındı:
API anahtarı, ses (voice), SFX aç/kapa + seviye, masaüstü kısayolu, açılışta
başlat, tepsiye al.

Kaynak tek: config/api_keys.json (app_config.py). Tkinter sürümü bazı ayarları
yalnızca bellekte tutuyordu (SFX durumu gibi) — burada hepsi diske yazılıyor,
uygulama kapanınca kaybolmasın.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app_config import load_app_config, save_app_config
from backend.core import commands

logger = logging.getLogger("chiron.backend")

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Gemini Live'ın hazır sesleri.
VOICES = ["Charon", "Puck", "Aoede", "Kore", "Fenrir", "Leda", "Orus", "Zephyr", "Sadaltager"]


def _mask(value: str) -> str:
    """API anahtarını arayüze göstermek için maskeler — panelde anahtarın
    GİRİLİ OLDUĞU görünmeli ama değeri sızmamalı."""
    value = str(value or "")
    if not value:
        return ""
    return f"{value[:4]}…{value[-4:]}" if len(value) > 12 else "…"


@router.get("")
@router.get("/")
async def read_settings() -> dict:
    config = load_app_config()
    from make_shortcut import desktop_shortcut_path, startup_shortcut_path

    return {
        "success": True,
        "message": "ayarlar",
        "data": {
            "voice": str(config.get("voice") or "Charon"),
            "voices": VOICES,
            "hasApiKey": bool(str(config.get("gemini_api_key") or "").strip()),
            "apiKeyMasked": _mask(config.get("gemini_api_key", "")),
            "sfxEnabled": bool(config.get("sfx_enabled", True)),
            "sfxVolume": float(config.get("sfx_volume", 0.2)),
            "micDevice": str(config.get("mic_device") or ""),
            "speakerDevice": str(config.get("speaker_device") or ""),
            "startupEnabled": startup_shortcut_path().exists(),
            "shortcutExists": desktop_shortcut_path("desktop").exists(),
        },
    }


class SettingsUpdate(BaseModel):
    voice: str | None = None
    geminiApiKey: str | None = None
    sfxEnabled: bool | None = None
    sfxVolume: float | None = None
    micDevice: str | None = None
    speakerDevice: str | None = None


@router.post("")
@router.post("/")
async def update_settings(update: SettingsUpdate) -> dict:
    changes: dict[str, object] = {}

    if update.voice is not None:
        if update.voice not in VOICES:
            return {"success": False, "message": f"Bilinmeyen ses: {update.voice}", "data": {}}
        changes["voice"] = update.voice
    if update.geminiApiKey is not None and update.geminiApiKey.strip():
        changes["gemini_api_key"] = update.geminiApiKey.strip()
    if update.sfxEnabled is not None:
        changes["sfx_enabled"] = update.sfxEnabled
    if update.sfxVolume is not None:
        changes["sfx_volume"] = max(0.0, min(1.0, update.sfxVolume))
    if update.micDevice is not None:
        changes["mic_device"] = update.micDevice.strip()
    if update.speakerDevice is not None:
        changes["speaker_device"] = update.speakerDevice.strip()

    if not changes:
        return {"success": False, "message": "değişiklik yok", "data": {}}

    save_app_config(changes)

    # Ses değişimi anında geçerli olmalı: ChironLive oturumu sessizce yeniden
    # kurar (bkz. main.py _on_voice_change) — yoksa yeni ses ancak uygulama
    # yeniden başlatılınca duyulurdu.
    if "voice" in changes:
        commands.dispatch("voice", {"voice": changes["voice"]})
    # Mikrofon/hoparlör cihazı bir sonraki oturumda geçerli olur (akış zaten açık).

    return {"success": True, "message": "kaydedildi", "data": {"changed": list(changes)}}


@router.post("/shortcut")
async def create_shortcut() -> dict:
    """Masaüstüne 3D uygulamanın kısayolunu koyar."""
    try:
        from make_shortcut import create_desktop_shortcut

        path = create_desktop_shortcut("desktop")
    except Exception as exc:
        logger.exception("Masaüstü kısayolu oluşturulamadı")
        return {"success": False, "message": f"Kısayol oluşturulamadı: {exc}", "data": {}}
    return {"success": True, "message": "Masaüstüne eklendi", "data": {"path": str(path)}}


class ToggleUpdate(BaseModel):
    enabled: bool


@router.post("/startup")
async def set_startup(update: ToggleUpdate) -> dict:
    """Windows açılışında otomatik başlat (Başlangıç klasörü kısayolu)."""
    try:
        from make_shortcut import create_startup_shortcut, remove_startup_shortcut

        if update.enabled:
            create_startup_shortcut("desktop")
        else:
            remove_startup_shortcut()
    except Exception as exc:
        logger.exception("Başlangıç kısayolu güncellenemedi")
        return {"success": False, "message": f"Güncellenemedi: {exc}", "data": {}}

    return {
        "success": True,
        "message": "Açılışta başlatma açık" if update.enabled else "Açılışta başlatma kapalı",
        "data": {"enabled": update.enabled},
    }


@router.post("/tray")
async def minimize_to_tray() -> dict:
    """Pencereyi gizleyip sistem tepsisine indirir (bkz. desktop.py)."""
    if not commands.dispatch("tray", {}):
        return {"success": False, "message": "Tepsi bu pencerede kullanılamıyor.", "data": {}}
    return {"success": True, "message": "Tepsiye alındı", "data": {}}
