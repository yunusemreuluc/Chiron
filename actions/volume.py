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

Uygulama başına ses (2026-11-04, K-012): "Spotify'ı kıs, YouTube kalsın". Aynı aygıttan
`IAudioSessionManager2` → oturum listesi → her oturumun `IAudioSessionControl2.GetProcessId`'si ile süreç
adı ve `ISimpleAudioVolume`'u. Oturum sesi ana sesin ORANIDIR (Ses Karıştırıcısı'ndaki kaydırıcı).
Yuvalar (audiopolicy.h bildirim sırası): QueryInterface=0 · IAudioSessionManager2.GetSessionEnumerator=5 ·
IAudioSessionEnumerator.GetCount=3, GetSession=4 · IAudioSessionControl2.GetProcessId=14 ·
ISimpleAudioVolume.SetMasterVolume=3, GetMasterVolume=4, SetMute=5, GetMute=6.
Kaynak: learn.microsoft.com/windows/win32/api/audiopolicy/nn-audiopolicy-iaudiosessionmanager2
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
_IID_IAudioSessionManager2 = "{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}"
_IID_IAudioSessionControl2 = "{BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D}"
_IID_ISimpleAudioVolume = "{87CE5498-68D6-44E5-9215-6DA47EF883D8}"
_CLSCTX_ALL = 0x17
_E_RENDER, _E_CONSOLE = 0, 0
_COINIT_MULTITHREADED = 0x0
_RPC_E_CHANGED_MODE = -2147417850  # 0x80010106: iş parçacığı zaten başka kipte açılmış, kullanılabilir
_HRESULT_NOT_FOUND = -2147023728  # 0x80070490: çıkış aygıtı yok

_RELEASE = 2
_GET_DEFAULT_ENDPOINT = 4
_ACTIVATE = 3
_SET_SCALAR, _GET_SCALAR, _SET_MUTE, _GET_MUTE = 7, 9, 14, 15
_QUERY_INTERFACE = 0
_GET_SESSION_ENUMERATOR = 5
_ENUM_COUNT, _ENUM_GET = 3, 4
_GET_PROCESS_ID = 14
_APP_SET, _APP_GET, _APP_SET_MUTE, _APP_GET_MUTE = 3, 4, 5, 6


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

    _IID = _IID_IAudioEndpointVolume

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
                         byref(_guid(self._IID)), _CLSCTX_ALL, None, byref(volume)),
                   "Ses denetimi")
            self._objects.append(volume)
            self._volume = volume
            self._ready()
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def _ready(self) -> None:
        """Alt sınıf kancası: etkinleştirilen arayüzden ek nesne alır (hepsi `_objects`'e)."""

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


class _AppSession:
    """Tek bir uygulama ses oturumu (`ISimpleAudioVolume`) — `_Endpoint` ile aynı okuma/yazma yüzü."""

    def __init__(self, volume: c_void_p, name: str):
        self._volume, self.name = volume, name

    def level(self) -> int:
        value = c_float()
        _check(_call(self._volume, _APP_GET, (POINTER(c_float),), byref(value)), "Uygulama sesi okuma")
        return round(value.value * 100)

    def set_level(self, percent: int) -> None:
        _check(_call(self._volume, _APP_SET, (c_float, c_void_p), c_float(percent / 100), None),
               "Uygulama sesi ayarlama")

    def muted(self) -> bool:
        value = c_int()
        _check(_call(self._volume, _APP_GET_MUTE, (POINTER(c_int),), byref(value)), "Uygulama sessiz durumu")
        return bool(value.value)

    def set_muted(self, muted: bool) -> None:
        _check(_call(self._volume, _APP_SET_MUTE, (c_int, c_void_p), int(muted), None), "Uygulamayı sessize alma")


def _process_name(pid: int) -> str | None:
    try:
        import psutil

        name = psutil.Process(pid).name()
    except Exception:  # süreç kapanmış / erişim yok — o oturum atlanır
        return None
    return name[:-4] if name.lower().endswith(".exe") else name


class _AppSessions(_Endpoint):
    """Varsayılan çıkış aygıtında ses oturumu olan uygulamalar; `.sessions` → `_AppSession` listesi."""

    _IID = _IID_IAudioSessionManager2

    def _ready(self) -> None:
        self.sessions: list[_AppSession] = []
        enum = c_void_p()
        _check(_call(self._volume, _GET_SESSION_ENUMERATOR, (POINTER(c_void_p),), byref(enum)), "Oturum listesi")
        self._objects.append(enum)
        count = c_int()
        _check(_call(enum, _ENUM_COUNT, (POINTER(c_int),), byref(count)), "Oturum sayısı")
        iid_control2, iid_simple = _guid(_IID_IAudioSessionControl2), _guid(_IID_ISimpleAudioVolume)
        qi_args = (POINTER(_GUID), POINTER(c_void_p))
        for index in range(count.value):
            control = c_void_p()
            if _call(enum, _ENUM_GET, (c_int, POINTER(c_void_p)), index, byref(control)) < 0:
                continue
            self._objects.append(control)
            control2 = c_void_p()
            if _call(control, _QUERY_INTERFACE, qi_args, byref(iid_control2), byref(control2)) < 0:
                continue
            self._objects.append(control2)
            pid = c_uint()
            # Çok süreçli oturumda GetProcessId S_FALSE (1) döner ama pid yine geçerlidir.
            if _call(control2, _GET_PROCESS_ID, (POINTER(c_uint),), byref(pid)) < 0 or not pid.value:
                continue  # pid 0: Sistem sesleri — kullanıcı onu uygulama adıyla istemez
            name = _process_name(pid.value)
            if not name:
                continue
            simple = c_void_p()
            if _call(control, _QUERY_INTERFACE, qi_args, byref(iid_simple), byref(simple)) < 0:
                continue
            self._objects.append(simple)
            self.sessions.append(_AppSession(simple, name))


def _norm(text: str) -> str:
    """"Spotify'ı" → "spotify", "Microsoft Edge" → "microsoftedge"; Türkçe I/İ casefold'da bozulmasın."""
    for apostrophe in ("'", "’"):
        text = text.split(apostrophe)[0]
    text = text.replace("İ", "i").replace("I", "ı").casefold().replace("ı", "i")
    text = text[:-4] if text.endswith(".exe") else text
    return "".join(ch for ch in text if ch.isalnum())


def match_app(query: str, names: list[str]) -> list[str]:
    """Söylenen ada uyan süreç adları (tekrarsız, sırayla). Önce tam eşleşme, yoksa içerme."""
    wanted = _norm(query)
    if not wanted:
        return []
    unique = list(dict.fromkeys(names))
    exact = [n for n in unique if _norm(n) == wanted]
    if exact:
        return exact
    return [n for n in unique if wanted in _norm(n) or (len(_norm(n)) >= 3 and _norm(n) in wanted)]


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


def describe(level: int, muted: bool, app: str | None = None) -> str:
    subject = f"{app} sesi" if app else "Ses"
    return f"{subject} yüzde {level}, sessizde." if muted else f"{subject} yüzde {level}."


def _app_volume(app: str, action: str, level: int | None, step: int | None) -> dict:
    with _AppSessions() as manager:
        names = list(dict.fromkeys(s.name for s in manager.sessions))
        found = match_app(app, names)
        if not found:
            playing = ", ".join(names) or "hiçbiri"
            return fail(f"{app} şu an ses çıkaran uygulamalar arasında yok. Ses çıkaranlar: {playing}.", apps=names)
        if len(found) > 1:
            return fail(f"'{app}' birden çok uygulamaya uyuyor: {', '.join(found)}. Hangisi?", apps=found)
        sessions = [s for s in manager.sessions if s.name == found[0]]
        # Tarayıcının birden çok oturumu olur — hepsine aynı ayar; "şu anki" en yükseği.
        target_level, target_mute = plan(action, max(s.level() for s in sessions), level, step)
        for session in sessions:
            if target_level is not None:
                session.set_level(target_level)
            if target_mute is not None:
                session.set_muted(target_mute)
        now = max(s.level() for s in sessions)
        muted = all(s.muted() for s in sessions)
    label = found[0][:1].upper() + found[0][1:]
    return ok(describe(now, muted, label), level=now, muted=muted, app=found[0])


@register_tool("set_volume")
def set_volume(action: str = "get", level: int | None = None, step: int | None = None,
               app: str | None = None) -> dict:
    action = (action or "get").strip().lower()
    try:
        if app and app.strip():
            return _app_volume(app.strip(), action, level, step)
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
