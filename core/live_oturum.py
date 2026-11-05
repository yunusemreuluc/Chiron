"""Gemini Live oturumunu mikrofon sustuyken ayakta tutmak ve normal kapanışı tanımak.

Mikrofon kapalıyken istemci hiç ses göndermiyor; sunucu da tam 120 saniye sonra
"1008 Session closed due to client inactivity" ile oturumu kapatıyor. Bu arıza değil
ama her iki dakikada bir iki ERROR ve 60 satırlık iz yazıyor (2026-11-06'da 118 kayıt),
mikrofonu yeniden açıyor ve canlı oturumun belleğini sıfırlıyordu: yeni oturuma yalnız
diskteki son konuşma notu taşınıyor.

İki katman:
- `keep_session_alive`: uzun süre hiçbir ses gitmediyse kısa bir SIFIR ses parçası
  gönderir. Mikrofondan tek bayt okumaz; susturulmuş mikrofon susturulmuş kalır.
- `is_expected_close`: sessizlik sunucuyu yine de ikna etmezse (belgeli bir garanti
  değil), bu kapanış hata sayılmaz, sessizce yeniden bağlanılır.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

logger = logging.getLogger("chiron")

# Sunucu 120 sn'de kesiyor. 20 sn: iki kez üst üste kaçsa da pay kalıyor.
KEEPALIVE_SECONDS = 20.0
CHECK_SECONDS = 1.0
# 40 ms, 16 kHz, 16-bit mono. Saatte ~7 sn ses eder; ücret açısından ihmal edilebilir.
SILENCE_CHUNK = bytes(16000 * 2 * 40 // 1000)

# Sunucunun olağan oturum sonu mesajları. Kota, geçersiz anahtar ve hizmet kesintisi
# burada DEĞİL: onlar kullanıcıya görünmesi gereken gerçek arızalar.
_EXPECTED_CLOSE_MARKERS = (
    "client inactivity",
    "session duration limit",
)


def is_expected_close(exc: BaseException) -> bool:
    """Sunucu oturumu olağan sebeple mi kapattı?

    Grupta TÜM alt hatalar beklenen olmalı: TaskGroup'ta yanındaki gerçek bir arıza
    (ör. mikrofon) "normal kapanış" diye saklanmasın.
    """
    if isinstance(exc, BaseExceptionGroup):
        return bool(exc.exceptions) and all(is_expected_close(sub) for sub in exc.exceptions)
    message = str(exc).lower()
    return any(marker in message for marker in _EXPECTED_CLOSE_MARKERS)


async def keep_session_alive(
    send: Callable[[bytes], Awaitable[None]],
    last_sent: Callable[[], float],
    blocked: Callable[[], bool],
    *,
    clock: Callable[[], float] = time.monotonic,
    tick: float = CHECK_SECONDS,
) -> None:
    """Son sesin üstünden `KEEPALIVE_SECONDS` geçtiyse sessizlik gönderir; iptale kadar sürer.

    Sayaç mikrofon döngüsünden bağımsız: mikrofon okuması takılsa da oturum kapanmaz.
    `send` zamanı kendisi günceller, böylece başarısız gönderim "gitti" sayılmaz. Gönderim
    hatası yutulur: oturum ölmüşse gerçek sebebi alım görevi bildirir.
    """
    while True:
        await asyncio.sleep(tick)
        if blocked() or clock() - last_sent() < KEEPALIVE_SECONDS:
            continue
        try:
            await send(SILENCE_CHUNK)
        except Exception:
            logger.debug("[CHIRON] Sessizlik gönderilemedi", exc_info=True)
