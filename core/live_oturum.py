"""Gemini Live oturumunu ayakta tutmak, normal kapanışı tanımak ve kopunca konuşmayı sürdürmek.

Mikrofon kapalıyken istemci hiç ses göndermiyor; sunucu da tam 120 saniye sonra
"1008 Session closed due to client inactivity" ile oturumu kapatıyor. Bu arıza değil
ama her iki dakikada bir iki ERROR ve 60 satırlık iz yazıyor (2026-11-06'da 118 kayıt),
mikrofonu yeniden açıyor ve canlı oturumun belleğini sıfırlıyordu: yeni oturuma yalnız
diskteki son konuşma notu taşınıyor.

Üç katman:
- `keep_session_alive`: uzun süre hiçbir ses gitmediyse kısa bir SIFIR ses parçası
  gönderir. Mikrofondan tek bayt okumaz; susturulmuş mikrofon susturulmuş kalır.
- `is_expected_close`: sessizlik sunucuyu yine de ikna etmezse (belgeli bir garanti
  değil), bu kapanış hata sayılmaz, sessizce yeniden bağlanılır.
- `SessionResume`: kopan oturumun yerine açılan bağlantı sunucunun verdiği anahtarla
  aynı konuşmayı sürdürür.
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

# Bu kadar konuşma olmadıysa eski konuşma geri getirilmez; yeni oturum eskisi gibi başlar.
RESUME_MAX_AGE_SECONDS = 2 * 60 * 60.0
# Devam edilen bağlantı bu süreden kısa yaşayıp sunucudan hiçbir şey almadıysa başarısız sayılır.
RESUME_PROOF_SECONDS = 30.0
# Bu kadar başarısızlıktan sonra anahtar bırakılır. run() 3 denemeyi kullanıcıya göstermeden
# yapıyor; yeni oturum dördüncüde açıldığı için geçersiz anahtar hata ekranına varmaz.
RESUME_MAX_FAILURES = 3


class SessionResume:
    """Sunucunun verdiği devam anahtarını tutar: kopmada konuşma belleği sıfırlanmasın.

    Saatlik kopmada yeni oturum modelin belleğini sıfırlıyor, yalnız diskteki son konuşma
    notu taşınıyordu. Anahtarla bağlanınca model konuşmanın kendisini hatırlar.

    Sessizce eski davranışa düşer: anahtar sunucuca reddedilirse Chiron'un açılmaması,
    konuşmayı unutmasından çok daha kötüdür.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._handle: str | None = None
        self._updated_at = 0.0
        self._attempted_at: float | None = None
        self._alive = False
        self._failures = 0
        self._fresh = False

    def seen(self, update: object | None = None) -> None:
        """Sunucudan mesaj geldi: bağlantı çalışıyor; güncelleme varsa anahtarı tazele.

        `resumable=False` anı (araç çağrısı, model konuşuyor) son iyi anahtarı silmez.
        """
        self._alive = True
        self._failures = 0
        handle = getattr(update, "new_handle", None)
        if handle and getattr(update, "resumable", False):
            self._handle = handle
            self._updated_at = self._clock()

    def start_fresh(self) -> None:
        """Kullanıcı sohbeti sıfırladı ya da ses değişti: bir sonraki oturum boş başlasın.

        Anahtar hemen silinmez, çünkü iptal edilen alım görevi araya bir güncelleme sokabilir.
        """
        self._fresh = True

    def next_handle(self) -> str | None:
        """Bu bağlantıda kullanılacak anahtar; yoksa None (yeni oturum)."""
        now = self._clock()
        if self._attempted_at is not None and not self._alive:
            if now - self._attempted_at < RESUME_PROOF_SECONDS:
                self._failures += 1
            else:
                self._failures = 0
        self._attempted_at = None

        if self._handle is not None:
            if self._failures >= RESUME_MAX_FAILURES:
                logger.warning("[CHIRON] Devam anahtarı çalışmadı, yeni oturum açılıyor.")
                self._handle = None
            elif self._fresh or now - self._updated_at > RESUME_MAX_AGE_SECONDS:
                self._handle = None
        self._fresh = False
        if self._handle is None:
            self._failures = 0
            return None

        self._attempted_at = now
        self._alive = False
        logger.info("[CHIRON] 🧵 Konuşma kaldığı yerden sürdürülüyor.")
        return self._handle


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

    İlk başarılı gönderim bağlantı başına bir kez günlüğe yazılır: düzeltmenin gerçekten
    devrede olduğu yalnız buradan görülür. Bu satırın ardından oturum yine iki dakikada
    düşüyorsa sessizlik sunucunun sayacını sıfırlamıyor demektir.
    """
    announced = False
    while True:
        await asyncio.sleep(tick)
        if blocked() or clock() - last_sent() < KEEPALIVE_SECONDS:
            continue
        try:
            await send(SILENCE_CHUNK)
        except Exception:
            logger.debug("[CHIRON] Sessizlik gönderilemedi", exc_info=True)
        else:
            if not announced:
                announced = True
                logger.info("[CHIRON] 🤫 Ses gitmiyor: oturum sessizlikle ayakta tutuluyor.")
