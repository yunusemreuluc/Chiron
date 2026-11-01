"""Araştırma panosu — arayüz açılınca son panoyu buradan yükler (canlı olaylar WebSocket'ten gelir).

Diskten okur, ses döngüsüne bağlı değil: Chiron yeniden başlasa da son pano gösterilebilir.
"""

from __future__ import annotations

from fastapi import APIRouter

from actions.arastirma_panosu import last_board

router = APIRouter(prefix="/api/research", tags=["research"])


@router.get("/last")
async def get_last_board() -> dict:
    board = last_board()
    if not board:
        return {"success": False, "message": "Henüz araştırma yok."}
    return {"success": True, "message": "", "data": board}
