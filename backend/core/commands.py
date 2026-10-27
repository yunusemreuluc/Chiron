"""Arayüzden ses döngüsüne giden komut yolu.

YÖN ÖNEMLİ: backend/websocket olayları ses döngüsünden ARAYÜZE akar; burası ters
yön — kullanıcının arayüzde yaptığı şeyin (yazı göndermek, mikrofonu susturmak,
sohbeti sıfırlamak) ChironLive'a ulaşması.

Neden basit bir sözlük yeterli: 2026-07-29'dan beri ses döngüsü ve backend AYNI
SÜREÇTE çalışıyor (bkz. desktop.py). Süreçler arası bir kuyruk/soket gerekmiyor —
core/web_ui.py başlarken kendi işleyicilerini buraya kaydediyor.

Ses döngüsü çalışmıyorsa (ör. arayüz tek başına, sadece 3D sahne için açıldıysa)
kayıt hiç yapılmaz ve dispatch False döner — endpoint bunu kullanıcıya dürüst bir
"asistan bağlı değil" mesajına çevirir, sessizce yutmaz.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger("chiron.backend")

Handler = Callable[[dict[str, Any]], None]

_handlers: dict[str, Handler] = {}
# Ses döngüsünün "komut alabilecek durumda mıyım" cevabı. Bağlı olmak (süreçte
# çalışmak) ile hazır olmak (canlı Gemini oturumu) AYNI ŞEY DEĞİL: oturum
# kurulmadan gönderilen komut sessizce kayboluyor.
_readiness: Callable[[], bool] | None = None

# ── Salt okunur veri sağlayıcılar (2026-07-30) ───────────────────────────────
# Komutlar tek yönlü ve SONUÇ TAŞIMIYOR (yukarıdaki nota bakın) — bu bilinçli.
# Ama arayüzün bazı şeyleri SORMASI gerekiyor: "şu an hangi izlemeler aktif?"
# gibi. Bunun için ayrı bir kayıt: ses döngüsü kendi durumunu okuyan bir
# fonksiyon bırakıyor, API onu senkron çağırıp cevabı HTTP ile döndürüyor.
#
# Neden komutları çift yönlü yapmak yerine ayrı bir kanal: komutlar EYLEM
# (thread'e atılıp beklemeden dönülüyor), sağlayıcılar SORGU (anında dönmeli).
# İkisini tek mekanizmaya sıkıştırmak, eylemlerin de sonuç beklemesi gerektiği
# yanılsamasını yaratırdı. `register_readiness` de zaten aynı desenin
# tek amaçlı bir örneğiydi.
_providers: dict[str, Callable[[], Any]] = {}


def register(name: str, handler: Handler) -> None:
    _handlers[name] = handler


def register_readiness(probe: Callable[[], bool]) -> None:
    global _readiness
    _readiness = probe


def register_provider(name: str, provider: Callable[[], Any]) -> None:
    _providers[name] = provider


def read_provider(name: str) -> Any | None:
    """Sağlayıcıyı çağırır. Kayıtlı değilse ya da hata verirse None döner —
    arayüzün bir paneli yüzünden backend'in 500 dönmesi, kullanıcıya asistanın
    tamamen koptuğu izlenimini verirdi."""
    provider = _providers.get(name)
    if provider is None:
        return None
    try:
        return provider()
    except Exception:
        logger.exception("Veri sağlayıcı hata verdi: %s", name)
        return None


def clear() -> None:
    global _readiness
    _handlers.clear()
    _providers.clear()
    _readiness = None


def is_connected() -> bool:
    """Ses döngüsü bu sürece bağlı mı?"""
    return bool(_handlers)


def is_ready() -> bool:
    """Ses döngüsü komut kabul edebilir durumda mı (canlı oturum var mı)?"""
    if _readiness is None:
        return False
    try:
        return bool(_readiness())
    except Exception:
        return False


def known_commands() -> list[str]:
    return sorted(_handlers)


def dispatch(name: str, payload: dict[str, Any] | None = None) -> bool:
    """Komutu ses döngüsüne iletir. İşleyici yoksa False döner.

    İşleyicinin kendi hatası komutu 'başarısız' yapmaz ama loglanır: arayüzün
    bir düğmesi yüzünden backend'in 500 dönmesi, kullanıcıya asistanın tamamen
    koptuğu izlenimini verirdi.
    """
    handler = _handlers.get(name)
    if handler is None:
        return False
    try:
        handler(payload or {})
    except Exception:
        logger.exception("Komut işleyicisi hata verdi: %s", name)
    return True
