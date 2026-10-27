from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket

from backend.core.remote_auth import REMOTE_EVENTS
from backend.models.events import WSEvent

logger = logging.getLogger("chiron.backend")


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        # Uzak (telefon) bağlantılar — yalnızca REMOTE_EVENTS alıyorlar. Ayrı bir
        # küme, çünkü `has_clients` pahalı yerel olayları (webcam karesi, mikrofon
        # seviyesi) üretmeden önce soruluyor ve telefon onları hiç almıyor.
        self._remote: set[WebSocket] = set()
        # Backend'in asyncio döngüsü. Ses döngüsü AYRI BİR THREAD'de çalışıyor
        # (bkz. desktop.py) — oradan doğrudan `await broadcast(...)` çağrılamaz;
        # olay bu döngüye devredilmek zorunda. Bkz. broadcast_threadsafe.
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def has_clients(self) -> bool:
        """Dinleyen bir arayüz var mı?

        Pahalı olayları (ör. webcam karesinin base64'e çevrilmesi — saniyede 8
        kez ~130 KB metin) üretmeden önce sorulur: pencere kapalıyken o işi
        yapmak saf israf."""
        return len(self._connections) > len(self._remote)

    def broadcast_threadsafe(self, event: WSEvent) -> None:
        """Herhangi bir thread'den güvenle çağrılabilir, asla bloklamaz.

        Backend henüz ayağa kalkmadıysa olay sessizce düşer — ses döngüsünün
        arayüz yüzünden gecikmesi ya da patlaması kabul edilemez.
        """
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(self.broadcast(event), loop)
        except Exception:
            logger.debug("Olay yayınlanamadı: %s", event.event, exc_info=True)

    async def connect(self, websocket: WebSocket, remote: bool = False) -> None:
        await websocket.accept()
        self._connections.append(websocket)
        if remote:
            self._remote.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._connections:
            self._connections.remove(websocket)
        self._remote.discard(websocket)

    async def close_remote(self) -> int:
        """Bütün uzak (telefon) bağlantıları kapatır.

        PIN değişince HTTP oturumları imza yüzünden düşüyor ama zaten AÇIK bir
        WebSocket el sıkışmasından sonra çereze bir daha bakmıyor — kaybolan
        telefon yeni konuşmaları almaya devam ederdi (Astra incelemesi,
        2026-09-15). Telefon yeniden bağlanmaya çalışınca kapıda PIN'e düşer.
        """
        closed = 0
        for connection in list(self._remote):
            try:
                await connection.close(code=1008)
            except Exception:
                pass
            self.disconnect(connection)
            closed += 1
        return closed

    async def broadcast(self, event: WSEvent) -> None:
        stale: list[WebSocket] = []
        remote_allowed = event.event in REMOTE_EVENTS
        # Liste kopyası: `await` sırasında bağlanan/kopan istemci döngüyü bozmasın.
        for connection in list(self._connections):
            if connection in self._remote and not remote_allowed:
                continue
            try:
                await connection.send_json(event.model_dump())
            except Exception:
                stale.append(connection)
        for connection in stale:
            self.disconnect(connection)


manager = ConnectionManager()
