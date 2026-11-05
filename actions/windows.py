"""Pencere yönetimi (2026-11-04, kendini geliştirme K-015).

"Chrome'a geç", "pencereyi küçült", "tam ekran yap", "Spotify'ı kapat", "bunu sola yasla", "masaüstünü göster",
"hangi pencereler açık?" — Chiron uygulama açabiliyordu (`open_app`) ama açık pencerelere dokunamıyordu; sesle
çalışırken en sık klavyeye/fareye dönülen an buydu.

Yol: saf ctypes + user32/dwmapi, yeni bağımlılık yok. Liste Alt+Tab'a yakın: görünür, başlıklı, sahipsiz
(ya da WS_EX_APPWINDOW), WS_EX_TOOLWINDOW olmayan ve DWM tarafından gizlenmemiş (DWMWA_CLOAKED — askıdaki
mağaza uygulamaları) pencereler. EnumWindows üstten alta z-sırasıyla döner, ilk eşleşme en son kullanılandır.

Dürüstlük: her eylemden sonra pencerenin durumu GERİ OKUNUR (IsIconic / IsZoomed / ön plan / IsWindow).
Kapatma WM_CLOSE gönderir — uygulama "kaydedilsin mi?" diye sorabilir; pencere kapanmazsa "kapattım" denmez.
Kaynak: devblogs.microsoft.com/oldnewthing/20071008-00/?p=24863 (Alt+Tab kuralları) ·
learn.microsoft.com/windows/win32/gdi/positioning-objects-on-a-multiple-display-setup (rcWork)
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass

from actions.tool_result import fail, ok
from core.tool_registry import register_tool

logger = logging.getLogger("chiron.windows")

ACTIONS = ("list", "focus", "minimize", "maximize", "restore", "close", "left", "right", "show_desktop")
_NEEDS_TARGET = ("focus", "minimize", "maximize", "restore", "close", "left", "right")
# Sesle söylenen genel adlar → süreç adları.
ALIASES = {
    "tarayıcı": ("chrome", "msedge", "firefox", "brave", "opera"),
    "tarayici": ("chrome", "msedge", "firefox", "brave", "opera"),
    "edge": ("msedge",),
    "terminal": ("windowsterminal", "cmd", "powershell", "pwsh"),
    "dosya gezgini": ("explorer",),
    "gezgin": ("explorer",),
    "not defteri": ("notepad",),
    "vs code": ("code",),
    "vscode": ("code",),
}
_SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


@dataclass(frozen=True)
class Window:
    hwnd: int
    title: str
    process: str  # uzantısız, küçük harf: "chrome"
    pid: int


def _fold(text: str) -> str:
    return (text or "").replace("İ", "i").replace("I", "ı").lower().replace("̇", "").strip()


def pick(windows: list[Window], hint: str) -> list[Window]:
    """`hint` ile eşleşen pencereler, z-sırası korunarak. Süreç adı tam eşleşmesi başlık eşleşmesinden önce gelir."""
    h = _fold(hint)
    if not h:
        return []
    names = ALIASES.get(h, (h.replace(" ", ""),))
    by_process = [w for w in windows if w.process in names]
    by_title = [w for w in windows if w not in by_process and (h in _fold(w.title) or h in w.process)]
    return by_process + by_title


# --- Win32 (Windows dışında modül yüklenir ama eylemler hata döner) ---------------------------------------
if sys.platform == "win32":
    _u32 = ctypes.WinDLL("user32", use_last_error=True)
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _dwm = ctypes.WinDLL("dwmapi")
    _ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _u32.EnumWindows.argtypes = [_ENUMPROC, wintypes.LPARAM]
    for _name, _args, _res in (
        ("IsWindowVisible", [wintypes.HWND], wintypes.BOOL),
        ("IsWindow", [wintypes.HWND], wintypes.BOOL),
        ("IsIconic", [wintypes.HWND], wintypes.BOOL),
        ("IsZoomed", [wintypes.HWND], wintypes.BOOL),
        ("GetWindowTextLengthW", [wintypes.HWND], ctypes.c_int),
        ("GetWindowTextW", [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
        ("GetClassNameW", [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
        ("GetWindow", [wintypes.HWND, wintypes.UINT], wintypes.HWND),
        ("GetWindowLongW", [wintypes.HWND, ctypes.c_int], wintypes.LONG),
        ("GetWindowThreadProcessId", [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
        ("GetForegroundWindow", [], wintypes.HWND),
        ("ShowWindowAsync", [wintypes.HWND, ctypes.c_int], wintypes.BOOL),
        ("PostMessageW", [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], wintypes.BOOL),
        ("MonitorFromWindow", [wintypes.HWND, wintypes.DWORD], wintypes.HMONITOR),
        ("SetWindowPos", [wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4 + [wintypes.UINT], wintypes.BOOL),
        ("GetMonitorInfoW", [wintypes.HMONITOR, ctypes.c_void_p], wintypes.BOOL),
    ):
        getattr(_u32, _name).argtypes = _args
        getattr(_u32, _name).restype = _res
    # 64 bit'te tanıtıcılar int'e kırpılmasın diye her imza açık.
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
    _k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def _process_name(pid: int) -> str:
    handle = _k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520)
        size = wintypes.DWORD(len(buf))
        if not _k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return os.path.splitext(os.path.basename(buf.value))[0].lower()
    finally:
        _k32.CloseHandle(handle)


def _switchable(hwnd) -> bool:
    if not _u32.IsWindowVisible(hwnd) or _u32.GetWindowTextLengthW(hwnd) == 0:
        return False
    ex = _u32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
    if ex & 0x80:  # WS_EX_TOOLWINDOW
        return False
    if _u32.GetWindow(hwnd, 4) and not ex & 0x40000:  # GW_OWNER, WS_EX_APPWINDOW
        return False
    cls = ctypes.create_unicode_buffer(64)
    _u32.GetClassNameW(hwnd, cls, 64)
    if cls.value in _SHELL_CLASSES:
        return False
    cloaked = ctypes.c_int(0)
    _dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))  # DWMWA_CLOAKED
    return not cloaked.value


def list_windows() -> list[Window]:
    """Alt+Tab'daki gibi kullanıcı pencereleri, en son kullanılan önce. Chiron'un kendi pencereleri hariç."""
    found: list[Window] = []
    own = os.getpid()

    def visit(hwnd, _lparam):
        try:
            if _switchable(hwnd):
                pid = wintypes.DWORD()
                _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value != own:
                    buf = ctypes.create_unicode_buffer(_u32.GetWindowTextLengthW(hwnd) + 1)
                    _u32.GetWindowTextW(hwnd, buf, len(buf))
                    found.append(Window(int(hwnd), buf.value, _process_name(pid.value), pid.value))
        except Exception:  # tek pencere listeyi bozmasın
            logger.debug("Pencere okunamadı", exc_info=True)
        return True

    _u32.EnumWindows(_ENUMPROC(visit), 0)
    return found


def is_minimized(hwnd: int) -> bool:
    return bool(_u32.IsIconic(hwnd))


def foreground() -> int:
    return int(_u32.GetForegroundWindow() or 0)


def _wait(check, timeout: float = 1.5) -> bool:
    end = time.monotonic() + timeout
    while True:
        if check():
            return True
        if time.monotonic() >= end:
            return False
        time.sleep(0.1)


def apply(action: str, win: Window) -> bool:
    """Eylemi uygular ve sonucu pencereden geri okuyarak doğrular."""
    hwnd = win.hwnd
    if action == "minimize":
        _u32.ShowWindowAsync(hwnd, 6)  # SW_MINIMIZE
        return _wait(lambda: _u32.IsIconic(hwnd))
    if action == "maximize":
        _u32.ShowWindowAsync(hwnd, 3)  # SW_MAXIMIZE
        return _wait(lambda: _u32.IsZoomed(hwnd))
    if action == "restore":
        _u32.ShowWindowAsync(hwnd, 9)  # SW_RESTORE
        return _wait(lambda: not _u32.IsIconic(hwnd) and not _u32.IsZoomed(hwnd))
    if action == "focus":
        if _u32.IsIconic(hwnd):
            _u32.ShowWindowAsync(hwnd, 9)
        from actions.screen_control import _force_foreground  # ağır modül, yalnız gerekince
        _force_foreground(hwnd)
        return _wait(lambda: _u32.GetForegroundWindow() == hwnd)
    if action == "close":
        _u32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE — uygulama kaydetmeyi sorabilir
        return _wait(lambda: not _u32.IsWindow(hwnd), timeout=2.0)
    if action in ("left", "right"):
        if _u32.IsIconic(hwnd) or _u32.IsZoomed(hwnd):
            _u32.ShowWindowAsync(hwnd, 9)
            _wait(lambda: not _u32.IsIconic(hwnd) and not _u32.IsZoomed(hwnd))
        info = _MONITORINFO(cbSize=ctypes.sizeof(_MONITORINFO))
        if not _u32.GetMonitorInfoW(_u32.MonitorFromWindow(hwnd, 2), ctypes.byref(info)):
            return False
        work = info.rcWork  # görev çubuğu hariç; sol üst (0,0) olmayabilir
        half = (work.right - work.left) // 2
        x = work.left if action == "left" else work.left + half
        return bool(_u32.SetWindowPos(hwnd, None, x, work.top, half, work.bottom - work.top, 0x0004))  # NOZORDER
    raise ValueError(f"Bilinmeyen eylem: {action}")


def minimize_all(windows: list[Window]) -> int:
    """"Masaüstünü göster": hepsine tek seferde küçült der, sonra bir kez bekler. Küçülen pencere sayısı."""
    targets = [w.hwnd for w in windows if not is_minimized(w.hwnd)]
    for hwnd in targets:
        _u32.ShowWindowAsync(hwnd, 6)
    _wait(lambda: all(is_minimized(h) for h in targets))
    return sum(1 for h in targets if is_minimized(h))


_DONE = {
    "focus": "öne getirdim", "minimize": "küçülttüm", "maximize": "tam ekran yaptım", "restore": "eski boyutuna aldım",
    "close": "kapattım", "left": "ekranın sol yarısına yasladım", "right": "ekranın sağ yarısına yasladım",
}
_FAILED = {
    "focus": "öne getirmeye çalıştım ama odak oraya geçmedi; Windows engellemiş olabilir",
    "close": "kapatma isteği gönderdim ama pencere hâlâ açık; kaydetmek isteyip istemediğini soruyor olabilir",
}


def _names(windows: list[Window], limit: int = 8) -> str:
    seen: list[str] = []
    for w in windows:
        if w.process and w.process not in seen:
            seen.append(w.process)
    return ", ".join(seen[:limit]) or "yok"


@register_tool("manage_window")
def manage_window(action: str = "list", app: str = "") -> dict:
    action = (action or "list").strip().lower()
    if action not in ACTIONS:
        return fail(f"Bilinmeyen eylem: {action}. Geçerli: {', '.join(ACTIONS)}.")
    if sys.platform != "win32":
        return fail("Pencere yönetimi yalnız Windows'ta çalışıyor.")
    try:
        windows = list_windows()
        if action == "list":
            return ok(f"Açık {len(windows)} pencere var: {_names(windows, 12)}.",
                      windows=[{"app": w.process, "title": w.title} for w in windows])
        if action == "show_desktop":
            done = minimize_all(windows)
            return ok(f"Masaüstünü gösterdim, {done} pencereyi küçülttüm.", count=done)
        if app and app.strip():
            matches = pick(windows, app)
            if not matches:
                return fail(f"'{app}' adında açık bir pencere bulamadım. Açık olanlar: {_names(windows)}.")
        else:
            fg = foreground()
            matches = [w for w in windows if w.hwnd == fg]
            if not matches:
                return fail("Hangi pencereyi kastettiğini bilemedim; uygulamanın adını söyler misin?")
        target = matches[0]
        if apply(action, target):
            return ok(f"{target.process or target.title} penceresini {_DONE[action]}.",
                      app=target.process, title=target.title)
        reason = _FAILED.get(action, "bunu yapmaya çalıştım ama pencere değişmedi")
        return fail(f"{target.process or target.title}: {reason}.", app=target.process)
    except OSError as error:
        logger.warning("Pencere eylemi başarısız: %s", error)
        return fail(f"Pencereye ulaşamadım: {error}")
