"""Canlı yükleme durumu — hangi değişiklik çalışan sürece uygulandı, hangisi yeniden başlatma istiyor.

Mantık `backend/core/canli_yukleme.py`'de. Yalnız okuma; açma/kapama yok (izleyici hep açık).
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.core.canli_yukleme import reloader

router = APIRouter(prefix="/api/canli", tags=["canli"])


@router.get("")
async def live_status() -> dict:
    return {"success": True, "message": "", "data": reloader.status()}
