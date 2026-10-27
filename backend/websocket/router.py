from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core import commands
from backend.models.events import WSEvent
from backend.websocket.manager import manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    # Kimlik doğrulaması ara katmanda yapıldı (backend/core/remote_auth.py);
    # buraya ulaşan uzak bağlantı zaten geçerli oturum taşıyor.
    remote = bool(websocket.scope.get("state", {}).get("remote", False))
    await manager.connect(websocket, remote=remote)
    # Kalıcı bayraklar (susturma, duraklatma, uzak mod) yalnızca DEĞİŞTİKLERİ an
    # yayınlanıyor. Sonradan bağlanan istemci — ör. telefondan uzak mod açıldıktan
    # sonra açılan PC penceresi — onları hiç öğrenmiyordu ve Chiron'un neden
    # sustuğunu göstermiyordu (2026-09-15, görsel testte yakalandı).
    status = commands.read_provider("assistant_status")
    if status:
        try:
            await websocket.send_json(WSEvent(event="assistant_status", data=status).model_dump())
        except Exception:
            manager.disconnect(websocket)
            return
    try:
        while True:
            # ileride istemciden gelen mesajlar henüz işlenmiyor — bağlantı
            # canlı tutuluyor. Gerçek olay akışı ileride main.py'ye bağlanacak.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
