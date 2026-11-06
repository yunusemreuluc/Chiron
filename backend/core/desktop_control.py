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
import subprocess
import threading

logger = logging.getLogger("chiron.backend")

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002

# Uyku, HTTP cevabı telefona ulaşmadan PC'yi uyutursa telefon "hata" görür.
SLEEP_DELAY_SECONDS = 3.0

ACTIONS = ("lock", "sleep", "media_play_pause", "media_next", "media_previous", "clipboard")

# Komut -> (geri okunan yolun eylemi, yedek medya tuşu, tuşun adı). Aç/kapa eylemi duruma göre seçilir.
_MEDIA = {
    "media_play_pause": ("", VK_MEDIA_PLAY_PAUSE, "oynat/duraklat"),
    "media_next": ("next", VK_MEDIA_NEXT_TRACK, "sonraki parça"),
    "media_previous": ("previous", VK_MEDIA_PREV_TRACK, "önceki parça"),
}


def _press_media_key(vk: int) -> None:
    user32 = ctypes.windll.user32
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def _media_command(action: str) -> tuple[bool, str]:
    """Medya komutunu durumu geri okuyan yoldan (`control_media`) yürütür; telefona gerçekten olanı söyler.

    Kör tuş yalnız Windows'un medya oturumlarını göremediğimiz durumda kalır (VLC gibi oturum açmayan oynatıcılar
    tuşu yine de dinler). O zaman da sonuç bilinmez, cevap da bunu açıkça söyler.
    """
    from actions import medya_kontrol as medya

    verb, key, label = _MEDIA[action]
    try:
        sessions = medya.read_sessions()
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        logger.warning("Medya durumu okunamadı, tuşa düşülüyor: %s", error)
        _press_media_key(key)
        return True, f"PC'ye {label} tuşunu gönderdim ama medya durumunu okuyamadım, sonucu doğrulayamadım."
    if not sessions:
        _press_media_key(key)
        return True, f"PC'de açık medya görünmüyor; {label} tuşunu yine de gönderdim, bir şey değişti mi bilmiyorum."
    if not verb:
        verb = "pause" if any(s["status"] == "Playing" for s in sessions) else "play"
    result = medya.control_media(verb)
    return result["success"], f"PC'de — {result['message']}"


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
        if action in _MEDIA:
            return _media_command(action)
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
