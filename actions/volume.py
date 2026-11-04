"""PC'nin ses seviyesi (2026-11-04, kendini geliştirme K-011).

"Sesi kıs", "sesi yüzde otuz yap", "sessize al", "ses kaç?" — PC'deki Chiron'un bunu yapan aracı yoktu;
`play_media` çalıyor ama sesi ayarlayamıyordu.

Yol: Windows Core Audio — varsayılan çıkış aygıtının `IAudioEndpointVolume` arayüzü. Yeni bağımlılık
eklememek için pycaw/comtypes yerine ham ctypes ile COM vtable'ı çağrılıyor. Medya tuşu (VK_VOLUME_UP)
yerine bu yol seçildi çünkü (1) mutlak seviye verilebiliyor ("yüzde otuz"), (2) sonuç geri okunuyor —
kullanıcıya söylenen yüzde tahmin değil, aygıttan okunan değer.

Vtable sırası endpointvolume.h / mmdeviceapi.h'deki bildirim sırasıdır (IUnknown'un 3 yuvası önce):
IMMDeviceEnumerator.GetDefaultAudioEndpoint=4 · IMMDevice.Activate=3 ·
IAudioEndpointVolume.SetMasterVolumeLevelScalar=7, GetMasterVolumeLevelScalar=9, SetMute=14, GetMute=15.
Kaynak: learn.microsoft.com/windows/win32/api/endpointvolume/nn-endpointvolume-iaudioendpointvolume
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import POINTER, byref, c_float, c_int, c_long, c_uint, c_void_p

from actions.tool_result import fail, ok
from core.tool_registry import register_tool

logger = logging.getLogger("chiron.volume")

ACTIONS = ("get", "set", "up", "down", "mute", "unmute")
DEFAULT_STEP = 10

_CLSID_MMDeviceEnumerator = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
_IID_IMMDeviceEnumerator = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"
_IID_IAudioEndpointVolume = "{5CDF2C82-841E-4546-9722-0CF74078229A}"
_CLSCTX_ALL = 0x17
_E_RENDER, _E_CONSOLE = 0, 0
_COINIT_MULTITHREADED = 0x0
_RPC_E_CHANGED_MODE = -2147417850  # 0x80010106: iş parçacığı zaten başka kipte açılmış, kullanılabilir
_HRESULT_NOT_FOUND = -2147023728  # 0x80070490: çıkış aygıtı yok

_RELEASE = 2
_GET_DEFAULT_ENDPOINT = 4
_ACTIVATE = 3
_SET_SCALAR, _GET_SCALAR, _SET_MUTE, _GET_MUTE = 7, 9, 14, 15


class _GUID(ctypes.Structure):
    _fields_ = [("d1", c_uint), ("d2", ctypes.c_ushort), ("d3", ctypes.c_ushort), ("d4", ctypes.c_ubyte * 8)]


def _guid(text: str) -> _GUID:
    guid = _GUID()
    hr = ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(text), byref(guid))
    if hr != 0:
        raise OSError(f"GUID çözülemedi: {text}")
    return guid


def _call(obj: c_void_p, index: int, argtypes: tuple, *args) -> int:
    """`obj`'nin vtable'ındaki `index`. yöntemi çağırır, HRESULT döner."""
    vtable = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
    proto = ctypes.WINFUNCTYPE(c_long, c_void_p, *argtypes)
    return proto(vtable[index])(obj, *args)


def _check(hr: int, what: str) -> None:
    if hr < 0:
        raise OSError(f"{what} başarısız (0x{hr & 0xFFFFFFFF:08X})", hr)


class _Endpoint:
    """Varsayılan çıkış aygıtının ses denetimi. `with` ile kullan — COM nesnelerini bırakır."""

    def __enter__(self) -> "_Endpoint":
        ole32 = ctypes.windll.ole32
        hr = ole32.CoInitializeEx(None, _COINIT_MULTITHREADED)
        self._uninit = hr >= 0  # S_OK/S_FALSE → CoUninitialize borcu; RPC_E_CHANGED_MODE → borç yok
        if hr < 0 and hr != _RPC_E_CHANGED_MODE:
            _check(hr, "CoInitializeEx")
        self._objects: list[c_void_p] = []
        try:
            enum = c_void_p()
            _check(ole32.CoCreateInstance(byref(_guid(_CLSID_MMDeviceEnumerator)), None, _CLSCTX_ALL,
                                          byref(_guid(_IID_IMMDeviceEnumerator)), byref(enum)),
                   "Ses aygıtı listesi")
            self._objects.append(enum)
            device = c_void_p()
            _check(_call(enum, _GET_DEFAULT_ENDPOINT, (c_int, c_int, POINTER(c_void_p)),
                         _E_RENDER, _E_CONSOLE, byref(device)), "Varsayılan hoparlör")
            self._objects.append(device)
            volume = c_void_p()
            _check(_call(device, _ACTIVATE, (POINTER(_GUID), c_uint, c_void_p, POINTER(c_void_p)),
                         byref(_guid(_IID_IAudioEndpointVolume)), _CLSCTX_ALL, None, byref(volume)),
                   "Ses denetimi")
            self._objects.append(volume)
            self._volume = volume
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_exc) -> None:
        for obj in reversed(self._objects):
            _call(obj, _RELEASE, ())
        self._objects.clear()
        if self._uninit:
            ctypes.windll.ole32.CoUninitialize()
            self._uninit = False

    def level(self) -> int:
        value = c_float()
        _check(_call(self._volume, _GET_SCALAR, (POINTER(c_float),), byref(value)), "Ses seviyesi okuma")
        return round(value.value * 100)

    def set_level(self, percent: int) -> None:
        _check(_call(self._volume, _SET_SCALAR, (c_float, c_void_p), c_float(percent / 100), None),
               "Ses seviyesi ayarlama")

    def muted(self) -> bool:
        value = c_int()
        _check(_call(self._volume, _GET_MUTE, (POINTER(c_int),), byref(value)), "Sessiz durumu okuma")
        return bool(value.value)

    def set_muted(self, muted: bool) -> None:
        _check(_call(self._volume, _SET_MUTE, (c_int, c_void_p), int(muted), None), "Sessize alma")


def plan(action: str, current: int, level: int | None, step: int | None) -> tuple[int | None, bool | None]:
    """Eylemi (hedef seviye, hedef sessiz durumu) çiftine çevirir; değişmeyecek olan None.

    Sesi yükseltmek/ayarlamak sessizliği de kaldırır — "sesi aç" diyen kullanıcı sessizde
    kalmış bir hoparlörün yüzdesinin değiştiğini duyamaz.
    """
    step = DEFAULT_STEP if not step else max(1, min(100, abs(int(step))))
    if action == "set":
        if level is None:
            raise ValueError("Hangi seviyeye ayarlanacağı söylenmedi.")
        target = max(0, min(100, int(level)))
        return target, (False if target > 0 else None)
    if action == "up":
        return min(100, current + step), False
    if action == "down":
        return max(0, current - step), None
    if action == "mute":
        return None, True
    if action == "unmute":
        return None, False
    if action == "get":
        return None, None
    raise ValueError(f"Bilinmeyen eylem: {action}. Geçerli: {', '.join(ACTIONS)}.")


def describe(level: int, muted: bool) -> str:
    return f"Ses yüzde {level}, sessizde." if muted else f"Ses yüzde {level}."


@register_tool("set_volume")
def set_volume(action: str = "get", level: int | None = None, step: int | None = None) -> dict:
    action = (action or "get").strip().lower()
    try:
        with _Endpoint() as endpoint:
            target_level, target_mute = plan(action, endpoint.level(), level, step)
            if target_level is not None:
                endpoint.set_level(target_level)
            if target_mute is not None:
                endpoint.set_muted(target_mute)
            # Söylenen değer aygıttan geri okunur — istenen değil, olan.
            now, muted = endpoint.level(), endpoint.muted()
    except ValueError as error:
        return fail(str(error))
    except OSError as error:
        code = error.args[1] if len(error.args) > 1 else None
        if code == _HRESULT_NOT_FOUND:
            return fail("PC'de etkin bir hoparlör ya da kulaklık bulunamadı.")
        logger.warning("Ses ayarı başarısız: %s", error)
        return fail(f"Ses ayarlanamadı: {error.args[0]}")
    return ok(describe(now, muted), level=now, muted=muted)
