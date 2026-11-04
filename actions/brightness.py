"""Ekran parlaklığı (2026-11-04, kendini geliştirme K-013).

"Parlaklığı kıs", "ekranı yüzde kırk yap", "parlaklık kaç?" — PC'deki Chiron sesi ayarlayabiliyordu
(`set_volume`) ama ekranı karartamıyordu; gece ya da sunumda en sık el ile yapılan ayar buydu.

Yol: WMI `root/WMI` — okuma `WmiMonitorBrightness.CurrentBrightness`, yazma
`WmiMonitorBrightnessMethods.WmiSetBrightness(Timeout, Brightness)`. Yeni bağımlılık yok: PowerShell'in
`Get-CimInstance`/`Invoke-CimMethod`'u pencere açmadan çağrılıyor. Yönetici izni gerekmiyor (Yunus'un
dizüstünde denendi). Yalnız yazılımla parlaklığı ayarlanabilen panellerde var (dizüstü, bazı hepsi-bir-arada);
harici monitörde sınıf boş döner → dürüst "ayarlanamıyor" cümlesi. Harici monitör DDC/CI ister (ayrı iş).

Panel bazı yüzdeleri desteklemez ve yeni değeri birkaç yüz ms sonra bildirir; o yüzden yazıp GERİ OKUYORUZ —
kullanıcıya söylenen yüzde istenen değil, panelin şu an bildirdiği değer.
Kaynak: learn.microsoft.com/windows/win32/wmicoreprov/wmisetbrightness-method-in-class-wmimonitorbrightnessmethods
"""

from __future__ import annotations

import logging
import subprocess
import time

from actions.tool_result import fail, ok
from core.tool_registry import register_tool

logger = logging.getLogger("chiron.brightness")

ACTIONS = ("get", "set", "up", "down")
DEFAULT_STEP = 10
# Sıfır bazı panellerde ekranı tamamen karartır; sesle geri açmak isteyen kullanıcı ekranı göremez.
MIN_LEVEL = 5
_NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW: pythonw altında konsol yanıp sönmesin
_TIMEOUT = 15

_READ = (
    "$b = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness -ErrorAction Stop "
    "| Select-Object -First 1; if ($b) { $b.CurrentBrightness }"
)
_WRITE = (
    "Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods -ErrorAction Stop "
    "| Select-Object -First 1 | Invoke-CimMethod -MethodName WmiSetBrightness "
    "-Arguments @{{Timeout=[uint32]1; Brightness=[byte]{level}}} -ErrorAction Stop | Out-Null"
)


class Unsupported(Exception):
    """Bu ekranın parlaklığı yazılımla ayarlanamıyor (harici monitör ya da sürücü desteği yok)."""


def _powershell(script: str) -> str:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=_TIMEOUT, creationflags=_NO_WINDOW,
    )
    if result.returncode != 0:
        error = (result.stderr or "").strip()
        # "Not supported" / "Desteklenmiyor": WMI sınıfı bu panelde yok.
        if "support" in error.lower() or "desteklen" in error.lower():
            raise Unsupported(error)
        raise OSError(error.splitlines()[0] if error else f"powershell çıkış kodu {result.returncode}")
    return result.stdout.strip()


def read_level() -> int:
    out = _powershell(_READ)
    if not out:
        raise Unsupported("WmiMonitorBrightness boş")
    return int(out.splitlines()[0])


def write_level(level: int) -> None:
    _powershell(_WRITE.format(level=int(level)))


def plan(action: str, current: int, level: int | None, step: int | None) -> int | None:
    """Eylemi hedef yüzdeye çevirir; `get` için None. Hedef [MIN_LEVEL, 100] aralığına kırpılır."""
    step = DEFAULT_STEP if not step else max(1, min(100, abs(int(step))))
    if action == "get":
        return None
    if action == "set":
        if level is None:
            raise ValueError("Parlaklığın hangi yüzdeye ayarlanacağı söylenmedi.")
        target = int(level)
    elif action == "up":
        target = current + step
    elif action == "down":
        target = current - step
    else:
        raise ValueError(f"Bilinmeyen eylem: {action}. Geçerli: {', '.join(ACTIONS)}.")
    return max(MIN_LEVEL, min(100, target))


def _settle(target: int, attempts: int = 5, wait: float = 0.15) -> int:
    """Panel yeni değeri gecikmeli bildirir; hedefe ulaşana ya da denemeler bitene kadar okur."""
    now = read_level()
    for _ in range(attempts - 1):
        if now == target:
            break
        time.sleep(wait)
        now = read_level()
    return now


def describe(level: int, floored: bool = False) -> str:
    text = f"Ekran parlaklığı yüzde {level}."
    if floored:
        text += f" Ekran tamamen kararmasın diye yüzde {MIN_LEVEL}'in altına inmiyorum."
    return text


@register_tool("set_brightness")
def set_brightness(action: str = "get", level: int | None = None, step: int | None = None) -> dict:
    action = (action or "get").strip().lower()
    try:
        current = read_level()
        target = plan(action, current, level, step)
        if target is None:
            return ok(describe(current), level=current)
        if target != current:
            write_level(target)
        now = _settle(target)
        asked_below = (action == "set" and level is not None and int(level) < MIN_LEVEL) or (
            action == "down" and target == MIN_LEVEL and current == MIN_LEVEL)
    except ValueError as error:
        return fail(str(error))
    except Unsupported:
        return fail("Bu ekranın parlaklığı yazılımla ayarlanamıyor; harici monitörse kendi düğmelerinden ayarlanmalı.")
    except (OSError, subprocess.TimeoutExpired) as error:
        logger.warning("Parlaklık ayarı başarısız: %s", error)
        return fail(f"Parlaklık ayarlanamadı: {error}")
    return ok(describe(now, floored=asked_below), level=now)
