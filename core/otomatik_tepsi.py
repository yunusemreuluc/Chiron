"""Konuşunca ya da ekranda gösterirken pencere tepsiye insin (2026-11-07).

Yunus: "bir şey soracağımda ya da bana göstereceğinde tepsiye al moduna geçsin otomatik." Pencere baktığı işin önünü
kapatmasın; köşedeki kabarcık (core/tray_indicator.py) konuşmayı zaten gösteriyor.

Tuzaklar:
* Mikrofon sürekli açık: TV ya da oda gürültüsü de yazıya dökülür. Tek kelime tetiklemez, en az iki kelime ister.
* Pencereyi kullanıcı kendi açtıysa ya da araştırma panosu öndeyse konuşunca hemen kaçmamalı: `hold_for`. Süreli,
  çünkü pano fareyle kapatılınca buraya haber gelmiyor; bayrak olsa sonsuza dek takılırdı.
* Ekranda gösterme bekletmeyi dinlemez (`force`): pencere hedefin önündeyse halka işe yaramaz.

Kapatmak: `app_config` `auto_tray` = false.
"""

from __future__ import annotations

import logging
import re
import threading
import time

logger = logging.getLogger("chiron")

HOLD_AFTER_OPEN = 30.0     # kullanıcı pencereyi kendi açtı
HOLD_AFTER_BOARD = 120.0   # araştırma panosu ya da Chiron'un öne getirdiği pencere
MIN_WORDS = 2
RESEND_SECONDS = 3.0       # yazıya dökme parça parça gelir, her parçada komut gitmesin

_lock = threading.Lock()
_hold_until = 0.0
_last_sent = 0.0


def enabled() -> bool:
    try:
        from app_config import get_app_config_value

        value = get_app_config_value("auto_tray", True)
    except Exception:
        return True
    return value is not False and str(value).strip().lower() not in ("false", "0", "hayir", "kapali")


def hold_for(seconds: float, now: float | None = None) -> None:
    """Bu kadar süre konuşma pencereyi tepsiye indirmesin."""
    global _hold_until
    now = time.monotonic() if now is None else now
    with _lock:
        _hold_until = max(_hold_until, now + seconds)


def real_speech(text: str) -> bool:
    """Gürültü etiketi ya da tek kelime sayılmaz: "<noise>", "hmm", "ıı"."""
    cleaned = re.sub(r"<[^>]*>|\[[^\]]*\]", " ", str(text or ""))
    return len([w for w in cleaned.split() if sum(ch.isalpha() for ch in w) >= 2]) >= MIN_WORDS


def go_to_tray(force: bool = False, now: float | None = None) -> bool:
    """Komutu gönderdiyse True. Tepsideyken de zararsız: `TrayController.minimize` hemen döner."""
    global _last_sent
    if not enabled():
        return False
    now = time.monotonic() if now is None else now
    with _lock:
        if not force and now < _hold_until:
            return False
        if not force and now - _last_sent < RESEND_SECONDS:
            return False
        _last_sent = now
    try:
        from backend.core import commands

        return bool(commands.dispatch("tray", {}))
    except Exception:
        logger.debug("[CHIRON] otomatik tepsi gönderilemedi", exc_info=True)
        return False


def on_user_speech(text: str, now: float | None = None) -> bool:
    """main.py: giriş yazıya dökmesi her geldiğinde, o turun birikmiş metniyle."""
    return go_to_tray(now=now) if real_speech(text) else False


def before_showing(settle: float = 0.25) -> None:
    """Ekran rehberi hedefi aramadan önce: pencere çekilsin, hedefin önünde kalmasın, ekran görüntüsüne girmesin."""
    if go_to_tray(force=True):
        time.sleep(settle)
