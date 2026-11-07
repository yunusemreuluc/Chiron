"""Ekran rehberi — kabarcık hedefe uçar, parçacıkları halka olur (2026-11-07).

Yunus Instagram'daki bir Windows ekran asistanını gösterdi ("nerede", "daire içine al", "bu ne"); dört
taslaktan D · Kabarcık'ı seçti, canlandırmayı izleyip "bu çok iyi olmuş, bundan devam" dedi.
Taslak: artifact SFsxEpKGxEERiBPnq2mfXj. Ayrıntı: Notes/Araclar/Ekran-Rehberi.md.

Köşedeki 07 Parçacık bulutuyla (core/tray_indicator.py) aynı model: aynı açı/yarıçap/hız/derinlik dağılımı, aynı
ışık biriktirme. Pencere de aynı (`LayeredWindow`): tıklama geçirir, odak almaz. Tek fark: pencere yalnız
kabarcığın o an kapladığı alan kadar. Tüm ekranı her karede çizmek 4K'da saniyede yüzlerce MB eder; kabarcık
köşedeyken çizilen alan 300 px kare.

İki parça:
* `BubbleMotion`: saf hareket mantığı, Win32'ye dokunmaz, test edilir (zamanı dışarıdan alır).
* `EkranRehberi`: kendi iş parçacığında pencere, tuş yoklama ve çizim. Yalnız bir işaret varken yaşar, boşta hiç
  iş parçacığı ya da pencere yok.

Koordinatlar FİZİKSEL piksel. Ölçüm 2026-11-07: ekran %125, DPI farkında olmayan süreç 1536x864 görüyor, gerçek
1920x1080. Her yerde aynı birim olsun diye iş parçacığı PER_MONITOR_AWARE_V2'ye alınıyor (`dpi_aware_thread`).
"""

from __future__ import annotations

import ctypes
import logging
import math
import threading
import time
from collections import deque
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from core.tray_indicator import MARGIN, PHASE_COLORS, LayeredWindow, dpi_scale, user32, work_area

logger = logging.getLogger("chiron")

Rect = tuple[int, int, int, int]  # x, y, genişlik, yükseklik

FPS = 40
PARTICLES = 80
CLOUD_RADIUS = 50       # 07 Parçacık'taki R (150 * 0.34), mantıksal px
NEAR_RADIUS = 0.42      # hedefin yanındayken bulutun oranı
TAIL_SECONDS = 0.2      # kuyruk: arkadaki parçacıklar aynı yolu bu kadar geç izler
MIX_PER_SECOND = 2.0    # bulut <-> halka geçiş hızı
SPRING = 6.5            # uçuş yayı (kritik sönümlü): ~1 sn'de varır
HOLD_POINT = 15.0       # "nerede": kullanıcı tıklamazsa bu kadar sonra köşeye döner
HOLD_CIRCLE = 60.0      # "daire içine al": "kaldır" denene kadar, ama sonsuza dek değil
VK_ESCAPE, VK_LBUTTON = 0x1B, 0x01
FONTS = Path(r"C:\Windows\Fonts")


def smooth(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


@dataclass(frozen=True)
class Mark:
    rect: Rect
    label: str = ""
    kicker: str = ""
    hold: float = HOLD_POINT
    # Hedefe tıklanınca çağrılır (rehber iş parçacığından): öğretirken sıradaki adıma geçmek için.
    on_click: Callable[[], None] | None = None


def perimeter_points(rect: Rect, u: np.ndarray, margin: np.ndarray | float) -> tuple[np.ndarray, np.ndarray]:
    """Dikdörtgen çevresinde 0..1 konumları → x, y. Köşeler keskin kalmasın diye değil, halka hedefi tam çevrelesin diye."""
    x, y, w, h = rect
    x0, y0 = x - margin, y - margin
    fw, fh = w + 2 * margin, h + 2 * margin
    d = np.mod(u, 1.0) * 2 * (fw + fh)
    px, py = np.empty_like(d, dtype=np.float32), np.empty_like(d, dtype=np.float32)
    x1, y1 = x0 + fw, y0 + fh
    top = d < fw
    right = ~top & (d < fw + fh)
    bottom = ~top & ~right & (d < 2 * fw + fh)
    left = ~top & ~right & ~bottom
    px = np.where(top, x0 + d, np.where(right, x1, np.where(bottom, x1 - (d - fw - fh), x0)))
    py = np.where(top, y0, np.where(right, y0 + (d - fw), np.where(bottom, y1, y1 - (d - 2 * fw - fh))))
    assert bool(np.all(top | right | bottom | left))
    return px, py


def clean_rect(rect: Rect, bounds: Rect) -> Rect | None:
    """Ekranla kesişen kısmı. Ekran dışı ya da anlamsız boyut: None (halka boşluğa çizilmesin)."""
    x, y, w, h = (int(round(v)) for v in rect)
    bx, by, bw, bh = bounds
    x0, y0 = max(x, bx), max(y, by)
    x1, y1 = min(x + w, bx + bw), min(y + h, by + bh)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    return x0, y0, x1 - x0, y1 - y0


def orb_position(rect: Rect, bounds: Rect, s: float) -> tuple[float, float]:
    """Halka olunca küçülen çekirdeğin yeri: hedefin sağ üstü, ekrana sığacak şekilde."""
    x, y, w, _ = rect
    bx, by, bw, bh = bounds
    ox, oy = x + w + 34 * s, y - 12 * s
    if ox > bx + bw - 24 * s:
        ox = x - 34 * s
    return max(bx + 24 * s, ox), max(by + 24 * s, min(oy, by + bh - 24 * s))


def place_balloon(rect: Rect, size: tuple[int, int], bounds: Rect, s: float) -> tuple[int, int]:
    """Yazı kutusu hedefin yanında, ekranda kalsın ve hedefi örtmesin: sağ → sol → alt → üst."""
    x, y, w, h = rect
    bw, bh = size
    sx, sy, sw, sh = bounds
    gap = int(58 * s)
    top = int(y - 30 * s)
    fit_y = max(sy, min(top, sy + sh - bh))
    if x + w + gap + bw <= sx + sw:
        return x + w + gap, fit_y
    if x - gap - bw >= sx:
        return x - gap - bw, fit_y
    fit_x = max(sx, min(x, sx + sw - bw))
    if y + h + int(14 * s) + bh <= sy + sh:
        return fit_x, y + h + int(14 * s)
    return fit_x, max(sy, y - int(14 * s) - bh)


class WindowWatch:
    """Halka altındaki pencere değişti mi? 2026-11-07: Yunus "yukarıda takılı kaldı" dedi; halka pencere değişince de
    aynı yerde boşlukta duruyordu. Öndeki pencere ya da konumu değişince gösterdiği şey artık orada değildir."""

    def __init__(self) -> None:
        self.base: tuple[int, tuple[int, int, int, int]] | None = None

    def reset(self) -> None:
        self.base = None

    def changed(self, hwnd: int, rect: tuple[int, int, int, int]) -> bool:
        if not hwnd:
            return False  # pencere geçişi sırasında Windows bir an 0 döner
        if self.base is None:
            self.base = (hwnd, rect)
            return False
        return (hwnd, rect) != self.base


def clicked_target(mark: Mark | None, settled: bool, down: bool, was_down: bool, cursor: tuple[int, int], margin: float) -> bool:
    """Oturmuş halkanın içine yeni basıldı mı? Basılı tutarak gelen fare sayılmaz. Hangi kipte olursa olsun: kullanıcı
    gösterilen yere tıkladıysa halkanın işi bitmiştir."""
    return bool(mark is not None and settled and down and not was_down and inside(cursor, mark.rect, margin))


class BubbleMotion:
    """Kabarcığın hareketi. Saf: zamanı `tick`e verilir; aynı girdi aynı konumu üretir."""

    def __init__(self, home: tuple[float, float], bounds: Rect, scale: float = 1.0) -> None:
        self.home = home
        self.bounds = bounds
        self.s = scale
        self.x, self.y = home
        self.vx = self.vy = 0.0
        self.mix = 0.0           # 0 bulut, 1 halka
        self.near = 0.0          # 0 köşe boyu, 1 hedef boyu
        self.vis = 0.0
        self.teal = 0.0
        self.balloon = 0.0
        self.mark: Mark | None = None
        self.pending: Mark | None = None
        self.clearing = False
        self.shown_at = 0.0
        self.now = 0.0
        self.trail: deque[tuple[float, float, float]] = deque()

        rng = np.random.default_rng(7)
        self.a0 = rng.random(PARTICLES, np.float32) * 6.283
        self.rr = 0.25 + rng.random(PARTICLES, np.float32) * 0.75
        self.sp = 0.35 + rng.random(PARTICLES, np.float32)
        self.z = rng.random(PARTICLES, np.float32)
        self.u = np.arange(PARTICLES, dtype=np.float32) / PARTICLES

    # ── komutlar ────────────────────────────────────────────────────────────
    def show(self, mark: Mark) -> None:
        self.clearing = False
        if self.mark is None:
            self.mark = mark
            self.shown_at = self.now
        else:
            self.pending = mark  # önce toplanır, sonra uçar

    def clear(self) -> None:
        self.pending = None
        self.clearing = True

    @property
    def active(self) -> bool:
        return (self.mark is not None or self.pending is not None) and not self.clearing

    @property
    def finished(self) -> bool:
        return self.mark is None and self.pending is None and self.vis < 0.01

    @property
    def settled(self) -> bool:
        """Halka oturdu: artık tıklama sayılabilir."""
        return self.mark is not None and self.active and self.pending is None and self.mix > 0.95

    def goal(self) -> tuple[float, float]:
        if self.mark is not None and not self.clearing:
            return orb_position(self.mark.rect, self.bounds, self.s)
        return self.home

    # ── zaman ───────────────────────────────────────────────────────────────
    def tick(self, dt: float) -> None:
        self.now += dt
        if self.mark is not None and not self.clearing and self.pending is None and self.now - self.shown_at > self.mark.hold:
            self.clear()

        gx, gy = self.goal()
        ax = SPRING * SPRING * (gx - self.x) - 2 * SPRING * self.vx
        ay = SPRING * SPRING * (gy - self.y) - 2 * SPRING * self.vy
        self.vx += ax * dt
        self.vy += ay * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        arrived = math.hypot(gx - self.x, gy - self.y) < 14 * self.s

        want_mix = 1.0 if (self.active and self.pending is None and self.mark is not None and arrived) else 0.0
        step = MIX_PER_SECOND * dt
        self.mix = min(want_mix, self.mix + step) if want_mix > self.mix else max(want_mix, self.mix - step)
        if self.mix < 0.03:
            if self.pending is not None:
                self.mark, self.pending = self.pending, None
                self.shown_at = self.now
            elif self.clearing:
                self.mark = None

        at_home = math.hypot(self.home[0] - self.x, self.home[1] - self.y) < 14 * self.s
        idle = self.mark is None and self.pending is None
        want_vis = 0.0 if idle and at_home else 1.0
        self.vis += (want_vis - self.vis) * min(1.0, dt * (5.0 if want_vis > self.vis else 2.4))
        want_near = 1.0 if self.active else 0.0
        self.near += (want_near - self.near) * min(1.0, dt * 3.0)
        self.teal += ((1.0 if self.active else 0.0) - self.teal) * min(1.0, dt * 3.5)
        want_balloon = 1.0 if self.settled else 0.0
        self.balloon += (want_balloon - self.balloon) * min(1.0, dt * (7.0 if want_balloon else 12.0))

        self.trail.append((self.now, self.x, self.y))
        while len(self.trail) > 2 and self.trail[1][0] < self.now - TAIL_SECONDS - 0.05:
            self.trail.popleft()

    def colors(self) -> tuple[np.ndarray, np.ndarray]:
        blue, teal = PHASE_COLORS["dinliyor"], PHASE_COLORS["konusuyor"]
        k = smooth(self.teal)
        return blue[0] + (teal[0] - blue[0]) * k, blue[1] + (teal[1] - blue[1]) * k

    def particles(self, amp: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(x, y, karışım) dizileri. 07 Parçacık'taki yörünge, üstüne kuyruk ve halka karışımı."""
        t = self.now
        when = t - self.z * TAIL_SECONDS
        if self.trail:
            times = np.fromiter((p[0] for p in self.trail), np.float32)
            lx = np.interp(when, times, np.fromiter((p[1] for p in self.trail), np.float32))
            ly = np.interp(when, times, np.fromiter((p[2] for p in self.trail), np.float32))
        else:
            lx, ly = np.full(PARTICLES, self.x), np.full(PARTICLES, self.y)
        radius = CLOUD_RADIUS * self.s * (1 - (1 - NEAR_RADIUS) * smooth(self.near))
        angle = self.a0 + t * self.sp * 0.7
        spread = radius * self.rr * (0.55 + amp * 0.75)
        x = lx + np.cos(angle) * spread
        y = ly + np.sin(angle) * spread * 0.86
        e = smooth(self.mix)
        each = np.clip(e * 1.25 - self.z * 0.25, 0.0, 1.0)
        if self.mark is not None and e > 0:
            margin = 9 * self.s + 3 * self.s * np.sin(t * self.sp * 2 + self.a0)
            qx, qy = perimeter_points(self.mark.rect, self.u + t * 0.035, margin)
            x = x + (qx - x) * each
            y = y + (qy - y) * each
        return x, y, each


# ── Çizim ────────────────────────────────────────────────────────────────────
_stamps: dict[int, np.ndarray] = {}


def _stamp(r: int) -> np.ndarray:
    if r not in _stamps:
        g = np.mgrid[-2 * r:2 * r + 1, -2 * r:2 * r + 1].astype(np.float32)
        _stamps[r] = np.exp(-(g[0] ** 2 + g[1] ** 2) / (r * r))
    return _stamps[r]


def _font(name: str, size: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), max(8, int(size)))


def wrap_text(text: str, measure: Callable[[str], float], width: float, max_lines: int = 5) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in " ".join(str(text).split()).split(" "):
        trial = f"{current} {word}".strip()
        if measure(trial) > width and current:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" .,") + "…"
    return lines


def render_balloon(kicker: str, body: str, tone: tuple[int, int, int], s: float) -> np.ndarray:
    """Yazı kutusu: önceden çarpılmış BGRA. 2x çizilip küçültülür."""
    k = 2 * s
    f1, f2 = _font("consola.ttf", 11 * k), _font("seguisb.ttf", 15 * k)
    pad, width = 15 * k, 300 * k
    lines = wrap_text(body, f2.getlength, width - 2 * pad)
    head = 19 * k if kicker else 0
    w, h = int(width), int(2 * pad + head + 21 * k * max(1, len(lines)))
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([1, 1, w - 2, h - 2], 14 * k, fill=(9, 15, 27, 244), outline=tone + (150,), width=max(2, int(1.5 * k)))
    if kicker:
        d.text((pad, pad), kicker, font=f1, fill=tone)
    y = pad + head
    for line in lines:
        d.text((pad, y), line, font=f2, fill=(240, 244, 250))
        y += 21 * k
    img = img.resize((w // 2, h // 2), Image.LANCZOS)
    arr = np.asarray(img, np.float32) / 255.0
    a = arr[..., 3:4]
    return np.concatenate([arr[..., 2:3] * a, arr[..., 1:2] * a, arr[..., 0:1] * a, a], axis=2)


def compose(motion: BubbleMotion, amp: float, balloon: np.ndarray | None) -> tuple[np.ndarray, int, int] | None:
    """Bir kare: (BGRA uint8, ekran x, ekran y). Çizilecek bir şey yoksa None."""
    if motion.vis < 0.01:
        return None
    s = motion.s
    col, hi = motion.colors()
    px, py, each = motion.particles(amp)
    e = smooth(motion.mix)
    near = 1 - (1 - NEAR_RADIUS) * smooth(motion.near)
    radius = CLOUD_RADIUS * s * near
    core = 1 - 0.55 * e
    r1 = max(2, int(radius * (0.45 + amp * 0.25) * core))
    r2 = max(3, int(radius * 1.1 * core))
    glow = 2 * r2 + 2
    x0, y0 = min(float(px.min()), motion.x - glow), min(float(py.min()), motion.y - glow)
    x1, y1 = max(float(px.max()), motion.x + glow), max(float(py.max()), motion.y + glow)

    ring: tuple[np.ndarray, np.ndarray] | None = None
    if motion.mark is not None and e > 0.02:
        x, y, w, h = motion.mark.rect
        count = int(min(320, max(70, 2 * (w + h) / (6 * s))))
        ring = perimeter_points(motion.mark.rect, np.arange(count, dtype=np.float32) / count, 9 * s)
        margin = 16 * s
        x0, y0 = min(x0, x - margin), min(y0, y - margin)
        x1, y1 = max(x1, x + w + margin), max(y1, y + h + margin)

    bx = by = 0
    show_balloon = balloon is not None and motion.mark is not None and motion.balloon > 0.01
    if show_balloon:
        bh, bw = balloon.shape[:2]
        bx, by = place_balloon(motion.mark.rect, (bw, bh), motion.bounds, s)
        x0, y0 = min(x0, bx), min(y0, by)
        x1, y1 = max(x1, bx + bw), max(y1, by + bh)

    # 16'ya hizalı: bitmap her karede yeniden ayrılmasın.
    pad = int(10 * s) + 8
    left, top = (int(x0) - pad) // 16 * 16, (int(y0) - pad) // 16 * 16
    w, h = (int(x1) + pad - left + 15) // 16 * 16, (int(y1) + pad - top + 15) // 16 * 16
    w, h = min(w, 16384), min(h, 16384)
    color = np.zeros((h, w, 3), np.float32)
    alpha = np.zeros((h, w), np.float32)

    def add(cx: float, cy: float, r: int, c: np.ndarray, gain: float) -> None:
        st = _stamp(r)
        n = st.shape[0]
        ax, ay = int(cx) - left - n // 2, int(cy) - top - n // 2
        ox0, oy0, ox1, oy1 = max(ax, 0), max(ay, 0), min(ax + n, w), min(ay + n, h)
        if ox0 >= ox1 or oy0 >= oy1:
            return
        m = st[oy0 - ay:oy1 - ay, ox0 - ax:ox1 - ax] * gain
        color[oy0:oy1, ox0:ox1] += m[..., None] * c
        alpha[oy0:oy1, ox0:ox1] += m

    vis = motion.vis
    add(motion.x, motion.y, r1, hi, 0.62 * vis)
    add(motion.x, motion.y, r2, col, 0.30 * vis)
    if ring is not None:
        line = max(1, int(1.4 * s))
        for qx, qy in zip(ring[0].tolist(), ring[1].tolist()):
            add(qx, qy, line, col, 0.26 * e * vis)
    for i in range(PARTICLES):
        z = float(motion.z[i])
        tone = hi if z > 0.6 else col
        tone = tone + (col - tone) * float(each[i]) * 0.8
        add(float(px[i]), float(py[i]), max(1, int((1.2 + z * 2.2) * s)), tone, 0.95 * vis)

    a = np.clip(alpha, 0, 1)
    c = np.minimum(np.clip(color, 0, None), a[..., None])
    out = np.empty((h, w, 4), np.float32)
    out[..., 0], out[..., 1], out[..., 2], out[..., 3] = c[..., 2], c[..., 1], c[..., 0], a

    if show_balloon:
        bh, bw = balloon.shape[:2]
        ox, oy = bx - left, by - top
        ox0, oy0, ox1, oy1 = max(ox, 0), max(oy, 0), min(ox + bw, w), min(oy + bh, h)
        if ox0 < ox1 and oy0 < oy1:
            spr = balloon[oy0 - oy:oy1 - oy, ox0 - ox:ox1 - ox] * smooth(motion.balloon)
            out[oy0:oy1, ox0:ox1] = spr + out[oy0:oy1, ox0:ox1] * (1 - spr[..., 3:4])
    return (out * 255 + 0.5).astype(np.uint8), left, top


# ── Pencere ve iş parçacığı ──────────────────────────────────────────────────
_DPI_AWARE_V2 = ctypes.c_void_p(-4)


def dpi_aware_thread() -> None:
    """Bu iş parçacığındaki Win32 koordinatları fiziksel piksel olsun. Hata: eski Windows, dokunma."""
    try:
        user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetThreadDpiAwarenessContext(_DPI_AWARE_V2)
    except Exception:
        logger.debug("[CHIRON] DPI bağlamı ayarlanamadı", exc_info=True)


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def monitor_bounds(rect: Rect) -> Rect:
    """Hedefin bulunduğu ekranın çalışma alanı (görev çubuğu hariç)."""
    try:
        user32.MonitorFromPoint.restype = ctypes.c_void_p
        user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MONITORINFO)]
        point = wintypes.POINT(int(rect[0] + rect[2] / 2), int(rect[1] + rect[3] / 2))
        handle = user32.MonitorFromPoint(point, 2)  # MONITOR_DEFAULTTONEAREST
        info = _MONITORINFO(cbSize=ctypes.sizeof(_MONITORINFO))
        if handle and user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            r = info.rcWork
            return r.left, r.top, r.right - r.left, r.bottom - r.top
    except Exception:
        logger.debug("[CHIRON] monitör bilgisi alınamadı", exc_info=True)
    left, top, right, bottom = work_area()
    return left, top, right - left, bottom - top


def home_position(s: float) -> tuple[float, float]:
    """Köşedeki bulutun merkezi: tray_indicator.Parcacik penceresiyle aynı yer."""
    _, top, right, _ = work_area()
    n = 150 * s
    return right - MARGIN * s - n / 2, top + MARGIN * s + n / 2


def _key_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def _cursor() -> tuple[int, int]:
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _front_window() -> tuple[int, tuple[int, int, int, int]]:
    user32.GetForegroundWindow.restype = wintypes.HWND
    hwnd = user32.GetForegroundWindow() or 0
    rect = wintypes.RECT()
    if hwnd:
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return int(hwnd), (rect.left, rect.top, rect.right, rect.bottom)


def inside(point: tuple[int, int], rect: Rect, margin: float = 0.0) -> bool:
    x, y, w, h = rect
    return x - margin <= point[0] <= x + w + margin and y - margin <= point[1] <= y + h + margin


class EkranRehberi:
    """Araçlar buradan konuşur; hepsi herhangi bir iş parçacığından güvenli."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._motion: BubbleMotion | None = None
        self._thread: threading.Thread | None = None
        self._queued: Mark | None = None
        self._balloon: np.ndarray | None = None

    def show(self, rect: Rect, label: str = "", kicker: str = "", circle: bool = False, hold: float | None = None,
             on_click: Callable[[], None] | None = None) -> None:
        mark = Mark(rect=tuple(int(v) for v in rect), label=label, kicker=kicker,
                    hold=hold if hold is not None else (HOLD_CIRCLE if circle else HOLD_POINT),
                    on_click=on_click)
        with self._lock:
            if self._motion is not None:
                self._motion.show(mark)
            else:
                self._queued = mark
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="chiron-ekran-rehberi", daemon=True)
                self._thread.start()

    def clear(self) -> bool:
        with self._lock:
            self._queued = None
            if self._motion is None or not self._motion.active:
                return False
            self._motion.clear()
            return True

    @property
    def active(self) -> bool:
        with self._lock:
            return self._queued is not None or (self._motion is not None and self._motion.active)

    def _level(self) -> float:
        try:
            from core.speaking_overlay import overlay

            return overlay.activity()[1]
        except Exception:
            return 0.0

    def _suppress_indicator(self, on: bool) -> None:
        """Köşedeki gösterge kapansın: aynı kabarcık iki yerde görünmesin."""
        try:
            from core.speaking_overlay import overlay

            overlay.set_suppressed(on)
        except Exception:
            logger.debug("[CHIRON] köşe göstergesi ayarlanamadı", exc_info=True)

    def _run(self) -> None:
        dpi_aware_thread()
        scale = 1.0
        try:
            user32.GetDpiForSystem.restype = wintypes.UINT
            scale = dpi_scale()
        except Exception:
            pass
        window = LayeredWindow()
        self._suppress_indicator(True)
        last_mark: Mark | None = None
        amp = 0.0
        was_down = _key_down(VK_LBUTTON)
        watch = WindowWatch()
        previous = time.perf_counter()
        try:
            while True:
                started = time.perf_counter()
                on_click = None
                dt = min(0.1, started - previous)
                previous = started
                window.pump()
                with self._lock:
                    if self._motion is None:
                        home = home_position(scale)
                        rect = self._queued.rect if self._queued else (int(home[0]), int(home[1]), 2, 2)
                        self._motion = BubbleMotion(home, monitor_bounds(rect), scale)
                    motion = self._motion
                    if self._queued is not None:
                        motion.bounds = monitor_bounds(self._queued.rect)
                        motion.show(self._queued)
                        self._queued = None
                    if _key_down(VK_ESCAPE) and motion.active:
                        motion.clear()
                    down = _key_down(VK_LBUTTON)
                    mark = motion.mark
                    if clicked_target(mark, motion.settled, down, was_down, _cursor(), 6 * scale):
                        motion.clear()  # gösterdiğim yere tıkladın: iş bitti
                        on_click = mark.on_click
                    was_down = down
                    if motion.settled:
                        if watch.changed(*_front_window()):
                            motion.clear()  # pencere değişti ya da oynadı: gösterdiğim şey artık orada değil
                    else:
                        watch.reset()
                    want = min(1.0, self._level() * 2.2)
                    amp += (want - amp) * min(1.0, dt * (20.0 if want > amp else 7.0))
                    motion.tick(dt)
                    if motion.mark is not last_mark:
                        last_mark = motion.mark
                        self._balloon = None
                        if last_mark is not None and last_mark.label:
                            self._balloon = render_balloon(last_mark.kicker, last_mark.label, (138, 232, 200), scale)
                    frame = compose(motion, amp, self._balloon)
                    if motion.finished:
                        self._motion = None
                        break
                if on_click is not None:
                    try:
                        on_click()
                    except Exception:
                        logger.exception("[CHIRON] ekran rehberi tıklama haberi gönderilemedi")
                if frame is not None:
                    window.present(frame[0], frame[1], frame[2])
                else:
                    window.hide()
                time.sleep(max(0.0, 1.0 / FPS - (time.perf_counter() - started)))
        except Exception:
            logger.exception("[CHIRON] ekran rehberi çöktü")
            with self._lock:
                self._motion = None
        finally:
            window.destroy()
            self._suppress_indicator(False)


rehber = EkranRehberi()


def demo() -> None:
    """Gerçek ekranda: `python -m core.ekran_rehberi --demo`. Tıklama geçer, Esc erken bitirir."""
    dpi_aware_thread()
    s = dpi_scale()
    x, y, w, h = monitor_bounds((0, 0, 10, 10))
    first = (x + w // 3, y + h // 3, int(120 * s), int(40 * s))
    second = (x + w // 2, y + h // 2, int(70 * s), int(70 * s))
    rehber.show(first, "Ekran rehberi denemesi. Bu kutu tıklamayı geçirir.", "ADIM 1 / 2", hold=4.5)
    time.sleep(4.0)
    rehber.show(second, "Şimdi buraya akıyorum.", "ADIM 2 / 2", hold=4.0)
    time.sleep(7.0)
    rehber.clear()
    while rehber.active or (rehber._thread and rehber._thread.is_alive()):
        time.sleep(0.1)


if __name__ == "__main__":
    import sys

    if "--demo" in sys.argv:
        demo()
