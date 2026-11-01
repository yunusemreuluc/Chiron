"""Tepsi konuşma göstergesi — gerçek saydam (per-pixel alpha) pencerede beş stil (2026-11-01).

Yunus taslak sayfasından (artifact DG2Z8UCzQVK7mzUzNT3W3r) 07, 08, 10, 12 ve 15'i seçti: "sırayla
deneyebilir miyiz". Bu modül beşini de çizer; hangisinin kullanılacağı `tray_indicator` ayarında
(app_config). Deneme: `python -m core.tray_indicator --demo` beşini sırayla, simüle konuşmayla oynatır.

Neden Win32 katmanlı pencere (UpdateLayeredWindow): 3D çekirdeği WebView2 penceresine koyma denemesinde
gerçek saydamlık alınamadı (pywebview `transparent` beyaz zemin, renk anahtarı WebView2'ye uygulanmadı) —
sonuç köşeleri kesik koyu bir daireydi, Yunus "çok kötü" dedi. Burada her kare numpy ile önceden çarpılmış
(premultiplied) BGRA olarak hazırlanıp doğrudan Windows'a veriliyor: kenarlar, ışıma ve gölge gerçekten
saydam. Pencere tıklamayı geçirir (WS_EX_TRANSPARENT), odak almaz, görev çubuğunda yoktur.

Işık modeli: çoğu stil "ışık biriktirme" — her parlak öğe renk*yoğunluk olarak toplanır, alfa da yoğunluk
kadar artar. Koyu zemin olmadan da (açık duvar kâğıdında da) parlak görünmesinin sebebi bu. Kayan kart
(08) ise bir yüzey; PIL ile normal bileşim.

İş parçacığı: pencere, mesaj döngüsü ve çizim TEK iş parçacığında (Win32 penceresi onu oluşturan iş
parçacığına aittir). Dışarıdan yalnız `SpeakingOverlay`'in kilitli durumu okunur.
"""

from __future__ import annotations

import ctypes
import logging
import math
import random
import time
from ctypes import wintypes
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger("chiron")

STYLES = ("parcacik", "kart", "imlec", "osiloskop", "cekirdek")
STYLE_NAMES = {
    "parcacik": "07 Parçacık bulutu",
    "kart": "08 Kayan kart",
    "imlec": "10 İmleç arkadaşı",
    "osiloskop": "12 Osiloskop",
    "cekirdek": "15 2D çekirdek",
}
DEFAULT_STYLE = "parcacik"  # Yunus 2026-11-01: "7 iyi o olsun"; 15 de seçenek
FPS = 40
MARGIN = 22  # mantıksal px — sağ üst köşeden

def _hex(h: str) -> np.ndarray:
    return np.array([int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)], np.float32)


# Durum renkleri — ana çekirdeğin paletiyle aynı (frontend/three/coreColors.ts: bodyLight + vurgu).
# Dinliyor = ICE, düşünüyor = DEEP_VIOLET, konuşuyor = PLASMA_TEAL. Mavi ve morda vurgu `rim` değil `corona`:
# rim neredeyse beyaz, ışık toplanınca ikisi de beyaza kaçıp ayırt edilmiyordu (ölçüldü, renk örneği).
PHASE_COLORS = {
    "dinliyor": (_hex("#7fb2ff"), _hex("#bcd6ff")),
    "dusunuyor": (_hex("#9c6ef0"), _hex("#c3a2ff")),
    "konusuyor": (_hex("#4fd6a8"), _hex("#dffff4")),
}
PHASE_COLORS["bitti"] = PHASE_COLORS["konusuyor"]  # konuşma sonrası kalış: son renkte söner
PHASES = tuple(PHASE_COLORS)

FONTS = Path(r"C:\Windows\Fonts")


# ── Win32 ────────────────────────────────────────────────────────────────────
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

WS_POPUP = 0x80000000
WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOPMOST = 0x80000, 0x20, 0x8
WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x80, 0x8000000
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
ULW_ALPHA, AC_SRC_ALPHA = 0x2, 0x1
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
PM_REMOVE = 0x1

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
# 64 bit tanıtıcılar: argüman tipleri verilmezse ctypes onları C int'e sıkıştırmaya çalışıp taşıyor.
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p),
                                   wintypes.HANDLE, wintypes.DWORD]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = [wintypes.HWND]
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.c_void_p, ctypes.c_void_p, wintypes.HDC,
                                       ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                wintypes.UINT]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.PeekMessageW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


_wndproc_ref = WNDPROC(lambda h, m, w, l: user32.DefWindowProcW(h, m, w, l))
_CLASS = "ChironTrayIndicator"
_class_registered = False


def dpi_scale() -> float:
    try:
        return user32.GetDpiForSystem() / 96.0
    except Exception:
        return 1.0


def work_area() -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
    return rect.left, rect.top, rect.right, rect.bottom


def cursor_pos() -> tuple[int, int]:
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


class LayeredWindow:
    """Tıklama geçiren, odak almayan, her zaman üstte, görev çubuğunda olmayan per-pixel alpha penceresi."""

    def __init__(self) -> None:
        global _class_registered
        hinst = kernel32.GetModuleHandleW(None)
        if not _class_registered:
            wc = WNDCLASSEXW()
            wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
            wc.lpfnWndProc = _wndproc_ref
            wc.hInstance = hinst
            wc.lpszClassName = _CLASS
            user32.RegisterClassExW(ctypes.byref(wc))
            _class_registered = True
        ex = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        self.hwnd = user32.CreateWindowExW(ex, _CLASS, "Chiron", WS_POPUP, 0, 0, 1, 1, None, None, hinst, None)
        self._screen_dc = user32.GetDC(None)
        self._mem_dc = gdi32.CreateCompatibleDC(self._screen_dc)
        self._bitmap = None
        self._bits = None
        self._size = (0, 0)
        self.visible = False

    def _ensure_bitmap(self, w: int, h: int) -> None:
        if self._size == (w, h):
            return
        if self._bitmap:
            gdi32.DeleteObject(self._bitmap)
        header = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=w, biHeight=-h, biPlanes=1,
                                  biBitCount=32, biCompression=0)
        bits = ctypes.c_void_p()
        self._bitmap = gdi32.CreateDIBSection(self._screen_dc, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
        gdi32.SelectObject(self._mem_dc, self._bitmap)
        self._bits = bits
        self._size = (w, h)

    def present(self, bgra: np.ndarray, x: int, y: int) -> None:
        h, w = bgra.shape[:2]
        self._ensure_bitmap(w, h)
        ctypes.memmove(self._bits, np.ascontiguousarray(bgra).ctypes.data, w * h * 4)
        dst, size, src = wintypes.POINT(int(x), int(y)), wintypes.SIZE(w, h), wintypes.POINT(0, 0)
        blend = BLENDFUNCTION(0, 0, 255, AC_SRC_ALPHA)
        user32.UpdateLayeredWindow(self.hwnd, self._screen_dc, ctypes.byref(dst), ctypes.byref(size),
                                   self._mem_dc, ctypes.byref(src), 0, ctypes.byref(blend), ULW_ALPHA)
        if not self.visible:
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
            self.visible = True

    def hide(self) -> None:
        if self.visible:
            user32.ShowWindow(self.hwnd, SW_HIDE)
            self.visible = False

    def pump(self) -> None:
        msg = wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def destroy(self) -> None:
        self.hide()
        if self._bitmap:
            gdi32.DeleteObject(self._bitmap)
        gdi32.DeleteDC(self._mem_dc)
        user32.ReleaseDC(None, self._screen_dc)
        user32.DestroyWindow(self.hwnd)


# ── Işık tamponu ─────────────────────────────────────────────────────────────
class Light:
    """Önceden çarpılmış renk + alfa biriktirici. `add` ışık ekler; `bgra` Windows'un beklediği biçim."""

    _grids: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = {}

    def __init__(self, w: int, h: int) -> None:
        self.w, self.h = w, h
        self.c = np.zeros((h, w, 3), np.float32)
        self.a = np.zeros((h, w), np.float32)
        # Koordinat ızgarası boyut başına bir kez (her karede yeniden kurmak gereksizdi); salt okunur kullanılıyor.
        if (w, h) not in Light._grids:
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            Light._grids[(w, h)] = (yy, xx)
        self.yy, self.xx = Light._grids[(w, h)]

    def add(self, mask: np.ndarray, color: np.ndarray, gain: float = 1.0) -> None:
        m = mask * gain
        self.c += m[..., None] * color
        self.a += m

    def radial(self, cx: float, cy: float, r: float, color: np.ndarray, gain: float) -> None:
        if r <= 0 or gain <= 0:
            return
        d2 = ((self.xx - cx) ** 2 + (self.yy - cy) ** 2) / (r * r)
        self.add(np.exp(-d2 * 2.2), color, gain)

    def bgra(self) -> np.ndarray:
        a = np.clip(self.a, 0, 1)
        c = np.minimum(np.clip(self.c, 0, None), a[..., None])  # önceden çarpılmış: renk ≤ alfa
        out = np.empty((self.h, self.w, 4), np.uint8)
        out[..., 0] = (c[..., 2] * 255).astype(np.uint8)
        out[..., 1] = (c[..., 1] * 255).astype(np.uint8)
        out[..., 2] = (c[..., 0] * 255).astype(np.uint8)
        out[..., 3] = (a * 255).astype(np.uint8)
        return out


def _mask(w: int, h: int, draw_fn: Callable[[ImageDraw.ImageDraw, float], None], ss: int = 2) -> np.ndarray:
    """Çizgi/daire maskesi: 2x çizilip küçültülür (PIL çizgileri kenar yumuşatmasız)."""
    img = Image.new("L", (w * ss, h * ss), 0)
    draw_fn(ImageDraw.Draw(img), ss)
    return np.asarray(img.resize((w, h), Image.BOX), np.float32) / 255.0


def _blur(mask: np.ndarray, radius: float) -> np.ndarray:
    img = Image.fromarray((np.clip(mask, 0, 1) * 255).astype(np.uint8), "L")
    return np.asarray(img.filter(ImageFilter.GaussianBlur(radius)), np.float32) / 255.0


def _rgba_to_bgra_premul(img: Image.Image) -> np.ndarray:
    arr = np.asarray(img, np.float32) / 255.0
    a = arr[..., 3:4]
    out = np.empty(arr.shape, np.uint8)
    out[..., 0] = (arr[..., 2] * a[..., 0] * 255).astype(np.uint8)
    out[..., 1] = (arr[..., 1] * a[..., 0] * 255).astype(np.uint8)
    out[..., 2] = (arr[..., 0] * a[..., 0] * 255).astype(np.uint8)
    out[..., 3] = (a[..., 0] * 255).astype(np.uint8)
    return out


# ── Stiller ──────────────────────────────────────────────────────────────────
# Her stil: `frame(t, vis, amp, caption, col, hi) -> (bgra, x, y)`; vis 0 iken çağrılmaz. col = ana renk,
# hi = parlak vurgu (duruma göre değişir, bkz. PHASE_COLORS).
class Style:
    def __init__(self, scale: float) -> None:
        self.s = scale

    def px(self, v: float) -> int:
        return max(1, int(round(v * self.s)))

    def corner(self, w: int, h: int) -> tuple[int, int]:
        left, top, right, bottom = work_area()
        return right - w - self.px(MARGIN), top + self.px(MARGIN)


class Parcacik(Style):
    """07 — zeminsiz ışık parçacıkları; ses yükselince dağılır, susunca toplanıp söner."""

    def __init__(self, scale: float) -> None:
        super().__init__(scale)
        self.n = self.px(150)
        rng = random.Random(7)
        self.parts = [(rng.random() * 6.283, 0.25 + rng.random() * 0.75, 0.35 + rng.random(), rng.random())
                      for _ in range(80)]
        self.stamps = {}

    def _stamp(self, r: int) -> np.ndarray:
        if r not in self.stamps:
            g = np.mgrid[-2 * r:2 * r + 1, -2 * r:2 * r + 1].astype(np.float32)
            self.stamps[r] = np.exp(-(g[0] ** 2 + g[1] ** 2) / (r * r))
        return self.stamps[r]

    def frame(self, t, vis, amp, caption, col, hi):
        n = self.n
        light = Light(n, n)
        cx = cy = n / 2
        R = n * 0.34
        light.radial(cx, cy, R * (0.45 + amp * 0.25), hi, 0.55 * vis)
        light.radial(cx, cy, R * 1.1, col, 0.22 * vis)
        for a0, rr, sp, z in self.parts:
            an = a0 + t * sp * 0.7
            rad = R * rr * (0.55 + amp * 0.75)
            x = cx + math.cos(an) * rad
            y = cy + math.sin(an) * rad * 0.86
            r = max(1, int(self.s * (1.2 + z * 2.2)))
            st = self._stamp(r)
            x0, y0 = int(x) - 2 * r, int(y) - 2 * r
            x1, y1 = x0 + st.shape[1], y0 + st.shape[0]
            if x0 < 0 or y0 < 0 or x1 > n or y1 > n:
                continue
            col = hi if z > 0.6 else col
            light.c[y0:y1, x0:x1] += st[..., None] * col * (0.9 * vis)
            light.a[y0:y1, x0:x1] += st * (0.9 * vis)
        x, y = self.corner(n, n)
        return light.bgra(), x, y


class Osiloskop(Style):
    """12 — zeminsiz tek parlak ses çizgisi."""

    def frame(self, t, vis, amp, caption, col, hi):
        w, h = self.px(260), self.px(70)
        cy = h / 2

        def draw(d: ImageDraw.ImageDraw, ss: int) -> None:
            pts = []
            for i in range(0, w + 1, 2):
                k = i / w
                env = math.sin(math.pi * k)
                y = cy + env * h * 0.36 * amp * (math.sin(k * 26 + t * 14) * 0.7 + math.sin(k * 9 - t * 6) * 0.3)
                pts.append((i * ss, y * ss))
            d.line(pts, fill=255, width=max(2, int(1.8 * self.s * ss)), joint="curve")

        line = _mask(w, h, draw)
        light = Light(w, h)
        light.add(_blur(line, 5 * self.s), col, 1.6 * vis)
        light.add(line, hi, 1.0 * vis)
        x, y = self.corner(w, h)
        return light.bgra(), x, y + self.px(10)


class Cekirdek(Style):
    """15 — ana çekirdeğin 2D çizimi: dönen nokta küresi + tel ağ + ışıma, zeminsiz."""

    def __init__(self, scale: float) -> None:
        super().__init__(scale)
        self.n = self.px(150)
        N = 96
        self.pts = []
        for i in range(N):
            y = 1 - (i / (N - 1)) * 2
            r = math.sqrt(max(0.0, 1 - y * y))
            th = i * 2.399963
            self.pts.append((math.cos(th) * r, y, math.sin(th) * r))
        # Komşular dönmeden önce bir kez: dönüş mesafeyi değiştirmez.
        self.pairs = [(i, j) for i in range(N) for j in range(i + 1, N)
                      if math.dist(self.pts[i], self.pts[j]) < 0.42]

    def frame(self, t, vis, amp, caption, col, hi):
        n = self.n
        cx = cy = n / 2
        R = n * 0.27 * (1 + amp * 0.1)
        ry, rx = t * 0.55, 0.45 + math.sin(t * 0.3) * 0.15
        proj = []
        for x, y, z in self.pts:
            x1 = x * math.cos(ry) + z * math.sin(ry)
            z1 = -x * math.sin(ry) + z * math.cos(ry)
            y1 = y * math.cos(rx) - z1 * math.sin(rx)
            z2 = y * math.sin(rx) + z1 * math.cos(rx)
            proj.append((cx + x1 * R, cy + y1 * R, z2))

        def wires(d: ImageDraw.ImageDraw, ss: int) -> None:
            for i, j in self.pairs:
                p, q = proj[i], proj[j]
                depth = (p[2] + q[2] + 2) / 4
                d.line([(p[0] * ss, p[1] * ss), (q[0] * ss, q[1] * ss)], fill=int(60 + 120 * depth), width=ss)

        def dots(d: ImageDraw.ImageDraw, ss: int) -> None:
            for x, y, z in proj:
                depth = (z + 1) / 2
                r = (0.7 + depth * 1.5) * self.s * ss
                d.ellipse([x * ss - r, y * ss - r, x * ss + r, y * ss + r], fill=int(90 + 165 * depth))

        light = Light(n, n)
        light.radial(cx, cy, R * 1.9, col, 0.28 * vis)
        wire = _mask(n, n, wires)
        light.add(wire, col, 0.75 * vis)
        dot = _mask(n, n, dots)
        light.add(_blur(dot, 2.5 * self.s), col, 0.9 * vis)
        light.add(dot, hi, 0.95 * vis)
        light.radial(cx, cy, R * (0.35 + amp * 0.3), hi, 0.9 * vis)
        x, y = self.corner(n, n)
        return light.bgra(), x, y


class Imlec(Style):
    """10 — farenin yanında atan küçük ışık topu; pencere her karede imleçle taşınır."""

    def frame(self, t, vis, amp, caption, col, hi):
        n = self.px(64)
        light = Light(n, n)
        c = n / 2
        light.radial(c, c, n * 0.42, col, 0.55 * vis)
        light.radial(c, c, n * (0.13 + amp * 0.1), hi, 1.0 * vis)
        mx, my = cursor_pos()
        off = self.px(26)
        return light.bgra(), mx + off - n // 2 + self.px(10), my + off - n // 2 + self.px(10)


class Kart(Style):
    """08 — sağdan kayan cam kart: küçük çekirdek, CHIRON ve söylediği cümlenin son kısmı."""

    def __init__(self, scale: float) -> None:
        super().__init__(scale)
        self.w, self.h = self.px(360), self.px(118)
        self.pad = self.px(18)  # gölge payı
        self.title = self._font(["bahnschrift.ttf", "segoeuib.ttf"], 14)
        self.body = self._font(["segoeui.ttf"], 13.5)

    def _font(self, names: list[str], size: float) -> ImageFont.ImageFont:
        for name in names:
            try:
                return ImageFont.truetype(str(FONTS / name), self.px(size))
            except OSError:
                continue
        return ImageFont.load_default()

    def _wrap(self, draw: ImageDraw.ImageDraw, text: str, width: int) -> list[str]:
        lines, cur = [], ""
        for word in text.split():
            test = f"{cur} {word}".strip()
            if draw.textlength(test, font=self.body) > width and cur:
                lines.append(cur)
                cur = word
            else:
                cur = test
        if cur:
            lines.append(cur)
        return lines

    def frame(self, t, vis, amp, caption, col, hi):
        w, h, p = self.w, self.h, self.pad
        size = (w + 2 * p, h + 2 * p)
        shadow = Image.new("L", size, 0)
        ImageDraw.Draw(shadow).rounded_rectangle([p, p + self.px(4), p + w, p + h + self.px(4)], self.px(12), fill=150)
        shadow = shadow.filter(ImageFilter.GaussianBlur(self.px(9)))
        black = Image.new("L", size, 0)
        img = Image.merge("RGBA", (black, black, black, shadow))
        card = Image.new("RGBA", size, (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        d.rounded_rectangle([p, p, p + w, p + h], self.px(12), fill=(12, 17, 27, 236),
                            outline=(127, 178, 255, 95), width=max(1, self.px(1)))
        img = Image.alpha_composite(img, card)
        # küçük çekirdek ışığı (ışık modeliyle, sonra kartın üstüne)
        orb_n = self.px(44)
        light = Light(orb_n, orb_n)
        light.radial(orb_n / 2, orb_n / 2, orb_n * 0.45, col, 0.7)
        light.radial(orb_n / 2, orb_n / 2, orb_n * (0.14 + amp * 0.1), hi, 1.1)
        orb = light.bgra()[..., [2, 1, 0, 3]]
        a = orb[..., 3:4].astype(np.float32) / 255.0
        rgb = np.where(a > 0, orb[..., :3].astype(np.float32) / np.maximum(a, 1e-3), 0)
        orb_img = Image.fromarray(np.concatenate([np.clip(rgb, 0, 255), a * 255], -1).astype(np.uint8), "RGBA")
        img.alpha_composite(orb_img, (p + self.px(10), p + self.px(8)))
        d = ImageDraw.Draw(img)
        d.text((p + self.px(58), p + self.px(19)), "CHIRON", font=self.title, fill=(232, 238, 247, 255))
        text = caption or "…"
        lines = self._wrap(d, text, w - self.px(36))[-3:]
        for i, ln in enumerate(lines):
            d.text((p + self.px(18), p + self.px(52) + i * self.px(20)), ln, font=self.body, fill=(214, 226, 242, 220))
        # içeri kayma + saydamlık
        ease = 1 - (1 - vis) ** 3
        arr = _rgba_to_bgra_premul(img)
        arr = (arr.astype(np.float32) * min(1.0, vis * 1.4)).astype(np.uint8)
        left, top, right, bottom = work_area()
        x = right - int((w + self.px(MARGIN)) * ease) - p
        y = top + self.px(MARGIN) - p
        return arr, x, y


STYLE_CLASSES = {"parcacik": Parcacik, "kart": Kart, "imlec": Imlec, "osiloskop": Osiloskop, "cekirdek": Cekirdek}


def make_style(name: str, scale: float) -> Style:
    return STYLE_CLASSES.get(name, STYLE_CLASSES[DEFAULT_STYLE])(scale)


# ── Döngü ────────────────────────────────────────────────────────────────────
def run(state: Callable[[], tuple[bool, str, float, str]], style_name: Callable[[], str],
        stop: Callable[[], bool]) -> None:
    """Gösterge döngüsü. `state()` → (etkin mi, evre, ses seviyesi 0..1, altyazı).

    Evre: "dinliyor" (kullanıcı konuşuyor, seviye = mikrofon), "dusunuyor" (kullanıcı sustu / araç çalışıyor,
    henüz ses yok), "konusuyor" (seviye = Chiron'un sesi), "bitti" (konuşma sonrası kısa kalış) ya da "" (gizli).
    Renk evreye göre yumuşakça değişir; görünürlük yumuşak açılıp söner."""
    window = LayeredWindow()
    scale = dpi_scale()
    current = ""
    style: Style | None = None
    vis = amp = 0.0
    col, hi = (c.copy() for c in PHASE_COLORS["dinliyor"])
    start = time.perf_counter()
    last = start
    try:
        while not stop():
            now = time.perf_counter()
            dt = min(0.1, now - last)
            last = now
            window.pump()
            enabled, phase, level, caption = state()
            name = style_name()
            if name != current:
                style, current = make_style(name, scale), name
            shown = enabled and phase in PHASE_COLORS
            target = 1.0 if shown and phase != "bitti" else (0.55 if shown else 0.0)
            vis += (target - vis) * min(1.0, dt * (5.0 if target > vis else 1.6))
            if phase == "dusunuyor":
                want = 0.22 + 0.12 * math.sin((now - start) * 3.2)  # sakin, nefes alan bekleyiş
            elif phase in ("konusuyor", "dinliyor"):
                want = min(1.0, level * (2.2 if phase == "konusuyor" else 3.0))
            else:
                want = 0.0
            amp += (want - amp) * min(1.0, dt * (20.0 if want > amp else 7.0))
            if phase in PHASE_COLORS:
                tc, th = PHASE_COLORS[phase]
                k = min(1.0, dt * 4.0)
                col += (tc - col) * k
                hi += (th - hi) * k
            if vis < 0.01 or not enabled:
                window.hide()
                time.sleep(0.1)
                continue
            try:
                assert style is not None
                bgra, x, y = style.frame(now - start, vis, amp, caption, col, hi)
                window.present(bgra, x, y)
            except Exception:
                logger.exception("[CHIRON] tepsi göstergesi karesi çizilemedi")
                time.sleep(0.5)
            time.sleep(max(0.0, 1.0 / FPS - (time.perf_counter() - now)))
    finally:
        window.destroy()


# ── Deneme ───────────────────────────────────────────────────────────────────
DEMO_LINES = [
    "Araştırma bitti. VR pazarı küçülüyor ama akıllı gözlükler büyüyor. Göstereyim mi?",
    "Hallettim, dosyaları masaüstündeki klasöre taşıdım.",
    "Yarın saat onda Dilcep toplantın var, hatırlatayım mı?",
]
# Bir tur: sen konuşuyorsun → Chiron düşünüyor → konuşuyor → biraz kalıp sönüyor.
DEMO_TIMELINE = (("dinliyor", 2.6), ("dusunuyor", 1.6), ("konusuyor", 4.2), ("bitti", 2.6), ("", 1.2))


def _speech_level(tt: float) -> float:
    level = 0.18 + abs(math.sin(tt * 10.5)) * 0.25 + abs(math.sin(tt * 4.1 + 1.3)) * 0.15
    return level * 0.25 if math.sin(tt * 3.7) > 0.86 else level


def demo(styles: list[str]) -> None:
    """Her stili sırayla, bir tam konuşma turuyla gerçek ekranda oynatır (Chiron'u yeniden başlatmadan denemek için)."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    order = list(styles)
    turn = sum(d for _, d in DEMO_TIMELINE)
    t0 = time.perf_counter()

    def phase_at() -> tuple[int, str, float]:
        el = time.perf_counter() - t0
        idx, local = int(el // turn), el % turn
        for phase, dur in DEMO_TIMELINE:
            if local < dur:
                return idx, phase, local
            local -= dur
        return idx, "", 0.0

    def state():
        idx, phase, local = phase_at()
        line = DEMO_LINES[idx % len(DEMO_LINES)]
        if phase == "dinliyor":
            return True, phase, _speech_level(local * 0.8) * 0.6, ""
        if phase == "konusuyor":
            words = line.split()
            return True, phase, _speech_level(local), " ".join(words[: int(local / 0.27) + 1])
        return True, phase, 0.0, line if phase == "bitti" else ""

    def name():
        idx, _, _ = phase_at()
        style = order[min(idx, len(order) - 1)]
        if name.last != style:
            # Düz ASCII: Windows konsolu (cp1254) ▶ ve → basamıyor, deneme ilk satırda çöküyordu.
            print(f"> {STYLE_NAMES.get(style, style)}  (dinliyor > dusunuyor > konusuyor > kalip soner)", flush=True)
            name.last = style
        return style

    name.last = ""
    run(state, name, lambda: time.perf_counter() - t0 > turn * len(order))


if __name__ == "__main__":
    import sys

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    picked = [a for a in args if a in STYLES] or ["parcacik", "kart", "imlec", "osiloskop", "cekirdek"]
    if "--demo" in sys.argv:
        demo(picked)
