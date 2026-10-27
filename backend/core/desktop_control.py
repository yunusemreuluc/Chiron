"""Telefondan gelen doğrudan masaüstü komutları (Chiron mobil, 2026-09-15).

Neden modelden geçmiyor: "PC'yi kilitle" gibi bir komutun Gemini'ye sorulup
aracın seçilmesini beklemek hem yavaş hem gereksiz — telefondaki Chiron zaten
niyeti anladı ve `send_desktop_command` aracını çağırdı. Buradaki her eylem
BEYAZ LİSTEDE; serbest komut çalıştırma yok (o iş `shell_run`'ın, onun da iki
adımlı onayı var).

Kapatma/yeniden başlatma bilerek YOK: telefondan tetiklenen bir kapatma,
kaydedilmemiş işi kaybettirebilir ve PC'ye bir daha uzaktan ulaşılamaz. O iş
PC'deki Chiron'un `control_power` aracında, onay akışıyla duruyor.
"""

from __future__ import annotations

import ctypes
import logging
import threading

logger = logging.getLogger("chiron.backend")

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002

# Uyku, HTTP cevabı telefona ulaşmadan PC'yi uyutursa telefon "hata" görür.
SLEEP_DELAY_SECONDS = 3.0

ACTIONS = ("lock", "sleep", "media_play_pause", "media_next", "media_previous", "clipboard")


def _press_media_key(vk: int) -> None:
    user32 = ctypes.windll.user32
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def _sleep_later() -> None:
    def run() -> None:
        # SetSuspendState(hibernate=False, force=True, wakeupEventsDisabled=False)
        ctypes.windll.powrprof.SetSuspendState(False, True, False)

    threading.Timer(SLEEP_DELAY_SECONDS, run).start()


def execute(action: str, text: str = "") -> tuple[bool, str]:
    """Eylemi çalıştırır. (başarılı mı, telefona dönecek kısa açıklama)."""
    try:
        if action == "lock":
            if not ctypes.windll.user32.LockWorkStation():
                return False, "PC kilitlenemedi."
            return True, "PC kilitlendi."
        if action == "sleep":
            _sleep_later()
            return True, (
                f"PC {int(SLEEP_DELAY_SECONDS)} saniye içinde uykuya geçiyor. "
                "Uyurken telefondan ulaşılamaz."
            )
        if action == "media_play_pause":
            _press_media_key(VK_MEDIA_PLAY_PAUSE)
            return True, "PC'de oynat/duraklat gönderildi."
        if action == "media_next":
            _press_media_key(VK_MEDIA_NEXT_TRACK)
            return True, "PC'de sonraki parçaya geçildi."
        if action == "media_previous":
            _press_media_key(VK_MEDIA_PREV_TRACK)
            return True, "PC'de önceki parçaya dönüldü."
        if action == "clipboard":
            if not text:
                return False, "Panoya aktarılacak metin boş."
            import pyperclip

            pyperclip.copy(text)
            return True, "Metin PC panosuna kopyalandı."
    except Exception as exc:
        logger.exception("Masaüstü komutu başarısız: %s", action)
        return False, f"Komut çalışmadı: {exc}"
    return False, f"Bilinmeyen komut: {action}"
