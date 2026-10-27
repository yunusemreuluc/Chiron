#!/usr/bin/env python3
"""
Chiron — masaüstü penceresi.

Kullanıcı isteğiyle (2026-07-29): 3D arayüz artık tarayıcıda değil, kendi
uygulama penceresinde açılıyor. Arayüz YENİDEN YAZILMADI — aynı Next.js/WebGL
kodu Windows'un WebView2 (Chromium) motorunda çalışıyor, bu yüzden görüntü
tarayıcıdakiyle birebir aynı: aynı shader'lar, aynı bloom/vinyet, aynı 60 FPS.
Fark yalnızca kabuk: adres çubuğu, sekme, tarayıcı çerçevesi yok.

MİMARİ — tek Python süreci, iki katman:
    [WebView2 penceresi]  ──HTTP/WS──>  [FastAPI (127.0.0.1:8000, arka plan thread)]
    [Telefon · Tailscale] ──HTTPS──> tailscale serve ──> 127.0.0.1:8001 (aynı sunucu)
                                              ├── / .......... frontend/out (statik arayüz)
                                              ├── /api/* ..... REST
                                              └── /ws ........ canlı durum akışı

Ses ve araçlar (main.py → ChironLive) AYNI süreçte, kendi thread'inde çalışır ve
arayüzle core/web_ui.py adaptörü üzerinden konuşur. Eski Tkinter penceresi
(ui.py) 2026-07-29'da tamamen kaldırıldı — tek arayüz bu.

Çalıştırma:  venv\\Scripts\\pythonw.exe desktop.py   (veya CHIRON.bat)
"""

from __future__ import annotations

import json
import logging
import os
import socket
import sys
import threading
import time
from pathlib import Path

from core.speaking_overlay import overlay as speaking_overlay

# Chromium, kullanıcı sayfaya dokunmadan ses çalmayı engeller. Chiron'un ses
# efektleri (açılış sesi gibi) kullanıcı etkileşiminden ÖNCE çalmak zorunda —
# bu bir masaüstü uygulaması, gezinilen bir web sayfası değil. WebView2 ek
# argümanları yalnızca bu ortam değişkeninden okunuyor ve motor başlamadan
# ayarlanmalı, bu yüzden dosyanın en üstünde.
os.environ.setdefault(
    "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--autoplay-policy=no-user-gesture-required"
)

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# ── pythonw altında stdout/stderr YOKTUR ───────────────────────────────────
# Masaüstü kısayolu uygulamayı konsolsuz (pythonw.exe) başlatır; orada
# sys.stdout ve sys.stderr None olur. `print()` bunu sessizce tolere eder AMA
# logging/uvicorn tolere etmez: StreamHandler None bir akışa yazmaya çalışınca
# patlar ve backend thread'i daha ilk saniyede ölür — uygulama hiçbir belirti
# vermeden hiç açılmaz. Bu yüzden akışlar bir log dosyasına yönlendiriliyor;
# yan fayda: kısayoldan açılan uygulamanın hatası artık diskte görünür.
if sys.stdout is None or sys.stderr is None:
    _log_path = BASE_DIR / "logs" / "desktop.log"
    _log_path.parent.mkdir(parents=True, exist_ok=True)
    _log_file = open(_log_path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 — süreç ömrü boyunca açık
    sys.stdout = _log_file
    sys.stderr = _log_file

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}/"
# Telefon erişimi (2026-09-15). Aynı uvicorn sunucusu bu portu da dinliyor;
# `tailscale serve` buraya yönlendiriliyor. İsteğin uzak olduğu proxy
# başlıklarından değil bu porttan anlaşılıyor — bkz. backend/core/remote_auth.py.
REMOTE_PORT = 8001
FRONTEND_EXPORT_DIR = BASE_DIR / "frontend" / "out"

# İkonlar (bkz. make_icon.py — prosedürel üretim, boyut başına ayrı çizim).
ICON_PATH = BASE_DIR / "Icon" / "chiron.ico"
TRAY_ICON_PATH = BASE_DIR / "Icon" / "chiron-tray.png"

# Görev çubuğu kimliği. pythonw.exe ile başlayan bir süreç, Windows'a kendini
# tanıtmazsa görev çubuğunda "Python" olarak gruplanır ve Python'un ikonunu
# gösterir. Bu sabit uygulamayı kendi kimliğine taşıyor.
APP_USER_MODEL_ID = "Chiron.Desktop"

# Pencere: 3D sahne geniş ekranda tasarlandı (bkz. Notes/Tasarim-Kurallari.md § Duyarlılık —
# 1366 en dar hedef). Minimum boyut bunun altına inmeyi engelliyor ki yerleşim
# hiç bozulmasın.
WINDOW_TITLE = "Chiron"
WINDOW_SIZE = (1600, 950)
WINDOW_MIN_SIZE = (1280, 800)
# app/globals.css'teki --background ile aynı: pencere açılırken WebGL sahnesi
# hazır olana kadar beyaz bir kare parlamasın.
WINDOW_BACKGROUND = "#05070C"

SERVER_START_TIMEOUT = 15.0

# ── Pencere boyutu/konumu hafızası ──────────────────────────────────────────
# Kullanıcı isteğiyle (2026-07-29): "açılışta bu boyutta açılsın". Sabit bir sayı
# yazmak yerine pencerenin son hali hatırlanıyor — kullanıcı bir daha boyut
# değiştirdiğinde de istediği gibi kalsın diye. İlk açılışta (kayıt yokken)
# yukarıdaki WINDOW_SIZE varsayılanı geçerli.
#
# Ayrı dosya: config/api_keys.json kimlik bilgisi taşıyor, pencere konumu gibi
# geçici arayüz durumunu oraya karıştırmak doğru olmaz.
WINDOW_STATE_PATH = BASE_DIR / "config" / "window_state.json"


def _load_window_state() -> dict:
    try:
        state = json.loads(WINDOW_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return state if isinstance(state, dict) else {}


def _visible_bounds() -> tuple[int, int]:
    """Birincil ekranın FİZİKSEL piksel boyutu.

    DİKKAT — burada `webview.screens[0]` KULLANILMAZ: o, Windows ölçeklemesi
    uygulanmış "mantıksal" boyutu verir (%125 ölçekte 1920x1080 ekran için
    1536x864), oysa `create_window(width=..., height=...)` fiziksel piksel
    bekler. İkisini karşılaştırmak pencereyi her açılışta ölçekleme oranı kadar
    küçültüyordu (1600 → 1536).
    """
    try:
        import ctypes

        # GetDeviceCaps: DESKTOPHORZRES(118)/DESKTOPVERTRES(117) ölçeklemeden
        # etkilenmeyen gerçek piksel sayısını verir.
        dc = ctypes.windll.user32.GetDC(0)
        try:
            width = int(ctypes.windll.gdi32.GetDeviceCaps(dc, 118))
            height = int(ctypes.windll.gdi32.GetDeviceCaps(dc, 117))
        finally:
            ctypes.windll.user32.ReleaseDC(0, dc)
        if width > 0 and height > 0:
            return width, height
    except Exception:
        pass
    return 1920, 1080


# İlk açılış boyutu — ekranın oranı olarak. Sabit piksel yazmak farklı
# çözünürlükte ya bir kenara sıkışır ya taşardı; bu oran 1920x1080'de kullanıcının
# istediği görünümü (ekran görüntüsündeki pencere) veriyor.
DEFAULT_WIDTH_RATIO = 0.82
DEFAULT_HEIGHT_RATIO = 0.89


class WindowGeometry:
    """Pencere boyutunu/konumunu FİZİKSEL piksel cinsinden uygular ve saklar.

    NEDEN Win32: pywebview'in `create_window(width=...)` değeri ile `window.width`
    özelliği aynı birimde DEĞİL. %125 ölçeklemeli bir ekranda 1600 istendiğinde
    pencere ekranda 1942 piksel oluyor (ekrandan taşıyor) ve pywebview bunu 1553
    diye bildiriyor. Bu belirsizliği çözmek yerine tamamen dışında kalıyoruz:
    boyut Win32 `GetWindowRect` ile ölçülüyor, `SetWindowPos` ile uygulanıyor —
    ikisi de aynı, ölçeklemeden bağımsız birimi kullanır, dolayısıyla gidiş-dönüş
    kararlı: kullanıcı pencereyi nasıl bıraktıysa öyle açılır.
    """

    _SWP_NOZORDER = 0x0004
    _SWP_NOACTIVATE = 0x0010
    _SW_MAXIMIZE = 3

    def __init__(self, window) -> None:
        self._window = window
        self._hwnd = None

    # ── Win32 yardımcıları ──────────────────────────────────────────────────
    def _handle(self):
        import ctypes

        if self._hwnd:
            return self._hwnd
        self._hwnd = ctypes.windll.user32.FindWindowW(None, WINDOW_TITLE) or None
        return self._hwnd

    @staticmethod
    def _rect(hwnd) -> tuple[int, int, int, int] | None:
        import ctypes

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        rect = RECT()
        if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top

    # ── Açılış ──────────────────────────────────────────────────────────────
    def apply_saved(self) -> None:
        """Pencere göründükten sonra kayıtlı boyutu/konumu uygular."""
        import ctypes

        hwnd = self._handle()
        if not hwnd:
            return

        state = _load_window_state()
        screen_width, screen_height = _visible_bounds()

        if state.get("maximized"):
            ctypes.windll.user32.ShowWindow(hwnd, self._SW_MAXIMIZE)
            return

        width = int(state.get("width") or screen_width * DEFAULT_WIDTH_RATIO)
        height = int(state.get("height") or screen_height * DEFAULT_HEIGHT_RATIO)
        width = max(WINDOW_MIN_SIZE[0], min(width, screen_width))
        height = max(WINDOW_MIN_SIZE[1], min(height, screen_height))

        x, y = state.get("x"), state.get("y")
        if not isinstance(x, int) or not isinstance(y, int):
            x, y = (screen_width - width) // 2, (screen_height - height) // 2
        # Pencerenin en az bir kısmı ekranda kalmalı: tamamen dışarıda açılırsa
        # (ör. artık takılı olmayan bir monitörün koordinatları) kullanıcı
        # uygulamanın hiç açılmadığını sanır.
        if not (-width + 120 < x < screen_width - 120 and -20 < y < screen_height - 120):
            x, y = (screen_width - width) // 2, (screen_height - height) // 2

        ctypes.windll.user32.SetWindowPos(
            hwnd, 0, int(x), int(y), width, height, self._SWP_NOZORDER | self._SWP_NOACTIVATE
        )

    # ── Kapanış ─────────────────────────────────────────────────────────────
    def save(self) -> None:
        import ctypes

        hwnd = self._handle()
        if not hwnd:
            return
        try:
            state: dict = {"maximized": bool(ctypes.windll.user32.IsZoomed(hwnd))}
            if not state["maximized"]:
                measured = self._rect(hwnd)
                if measured is None:
                    return
                x, y, width, height = measured
                state.update({"x": x, "y": y, "width": width, "height": height})
            WINDOW_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            WINDOW_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except Exception:
            # Pencere durumunu kaydedememek uygulamanın kapanmasını engellemez.
            logging.getLogger("chiron").debug("Pencere durumu yazılamadı", exc_info=True)

    def bind(self) -> None:
        self._window.events.shown += self.apply_saved
        self._window.events.closing += self.save


# ── Pencere kimliği ve ikonu ────────────────────────────────────────────────
def _apply_taskbar_identity() -> None:
    """Görev çubuğunda Chiron'u Python'dan ayırır.

    Uygulama `pythonw.exe` ile başlıyor. Windows, süreç kendini açıkça
    tanıtmadıkça görev çubuğu düğmesini Python'un kimliğiyle gruplandırır ve
    onun ikonunu gösterir — sabitlenmiş öğede Chiron yerine yılan ikonu çıkmasının
    sebebi bu. Açık bir AppUserModelID düğmeyi kendi kimliğimize taşıyor.

    Pencere OLUŞTURULMADAN ÖNCE çağrılmalı: kimlik, pencere ilk kez görev
    çubuğuna kaydolurken okunuyor.
    """
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        # Kimlik ayarlanamazsa uygulama çalışır, sadece görev çubuğunda Python
        # ile gruplanır — açılışı engelleyecek bir sorun değil.
        logging.getLogger("chiron").debug("AppUserModelID ayarlanamadı", exc_info=True)


def _apply_window_icon(*_args) -> None:
    """Başlık çubuğu ve görev çubuğu ikonunu ayarlar.

    pywebview'in Windows/WebView2 arka ucu pencereye ikon vermiyor, bu yüzden
    doğrudan Win32: WM_SETICON ile KÜÇÜK (başlık çubuğu) ve BÜYÜK (görev çubuğu,
    Alt-Tab) ikonlar ayrı ayrı yükleniyor. İkisi ayrı çünkü Windows farklı
    boyutlar istiyor ve .ico içindeki uygun kareyi kendisi seçiyor — 16px'te
    sadeleştirilmiş çizim, 32px'te tam kompozisyon (bkz. make_icon.py).
    """
    import ctypes
    from ctypes import wintypes

    if not ICON_PATH.exists():
        return

    try:
        user32 = ctypes.windll.user32

        # x64'te tanıtıcılar 64 bit. argtypes/restype verilmezse ctypes dönüş
        # değerini `int`e (32 bit) kırpar; ikon sessizce ayarlanmaz.
        user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user32.FindWindowW.restype = wintypes.HWND
        user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE,
            wintypes.LPCWSTR,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.SendMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.SendMessageW.restype = wintypes.LPARAM

        hwnd = user32.FindWindowW(None, WINDOW_TITLE)
        if not hwnd:
            return

        image_icon, load_from_file, wm_seticon = 1, 0x0010, 0x0080
        # (WM_SETICON'un wParam'ı, GetSystemMetrics indeksi)
        icon_small, icon_big = (0, 49), (1, 11)

        for which, metric in (icon_small, icon_big):
            extent = user32.GetSystemMetrics(metric)
            handle = user32.LoadImageW(
                None, str(ICON_PATH), image_icon, extent, extent, load_from_file
            )
            if handle:
                user32.SendMessageW(hwnd, wm_seticon, which, handle)
    except Exception:
        logging.getLogger("chiron").debug("Pencere ikonu ayarlanamadı", exc_info=True)


def _fatal(message: str) -> int:
    """Ölümcül hatayı kullanıcıya GÖSTERİR.

    Masaüstü kısayolu uygulamayı `pythonw.exe` ile (konsolsuz) başlatıyor —
    orada stderr'e yazmak hiçbir yere yazmamakla aynı şey: uygulama sessizce
    hiç açılmaz. Konsol yoksa mesaj bir Windows iletişim kutusuna düşer.
    """
    print(message, file=sys.stderr)
    if sys.stderr is None or not sys.stderr.isatty():
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, "Chiron", 0x10)  # MB_ICONERROR
        except Exception:
            pass
    return 1


def _port_is_open(host: str, port: int, timeout: float = 0.4) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def _bind_socket(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # SO_REUSEADDR BİLEREK YOK: Windows'ta başka bir sürecin dinlediği portu
    # sessizce paylaşmaya izin veriyor — yanlış backend'e bağlanmak demek.
    sock.bind((host, port))
    sock.set_inheritable(True)
    return sock


def _start_backend() -> "threading.Thread | None":
    """Backend'i arka plan thread'inde başlatır.

    Port zaten dinlemedeyse hiç başlatmaz: kullanıcı backend'i elle (veya
    WEB-BASLAT.bat ile) çalıştırmış olabilir — ikinci bir örnek açmaya çalışmak
    "port kullanımda" hatasıyla uygulamayı hiç açılmaz hale getirirdi.
    """
    if _port_is_open(HOST, PORT):
        print(f"[Chiron] {PORT} portu zaten dinlemede — mevcut backend kullanılıyor.")
        return None

    import uvicorn

    from backend.main import app

    # İki soket, TEK sunucu: iki ayrı uvicorn sunucusu iki ayrı asyncio döngüsü
    # demek, oysa WebSocket yayını (backend/websocket/manager.py) tek döngüye
    # bağlı — ikinci döngüdeki bağlantılara yayın yapılamazdı.
    sockets = [_bind_socket(HOST, PORT)]
    try:
        sockets.append(_bind_socket(HOST, REMOTE_PORT))
    except OSError as exc:
        # Telefon erişimi olmasın diye uygulamanın hiç açılmaması kabul edilemez.
        print(f"[Chiron] Uzak erişim portu {REMOTE_PORT} açılamadı ({exc}) — telefon erişimi kapalı.")

    config = uvicorn.Config(app, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": sockets}, name="chiron-backend", daemon=True
    )
    thread.start()
    return thread


def _wait_for_server() -> bool:
    deadline = time.monotonic() + SERVER_START_TIMEOUT
    while time.monotonic() < deadline:
        if _port_is_open(HOST, PORT):
            return True
        time.sleep(0.15)
    return False


class TrayController:
    """Pencereyi sistem tepsisine indirir/geri getirir.

    Tepsi ikonu YALNIZCA küçültülmüşken var olur — sürekli duran bir ikon, kapalı
    sanılan bir uygulamanın arka planda çalıştığını gizlemek yerine görünür kılmalı;
    burada pencere zaten açıkken ikona gerek yok.

    pystray'in `run()` çağrısı bloklar, bu yüzden kendi thread'inde çalışır.
    """

    def __init__(self, window) -> None:
        self._window = window
        self._icon = None
        self._lock = threading.Lock()

    def minimize(self) -> None:
        with self._lock:
            if self._icon is not None:
                return  # zaten tepside
            try:
                import pystray
                from PIL import Image
            except Exception:
                logging.getLogger("chiron").warning("[Chiron] pystray/Pillow yok — tepsi kapalı")
                return

            # Tepsi ikonu Windows'ta 16-24px arasında çiziliyor. pystray .ico
            # içindeki kareleri seçemiyor (en büyüğünü alıp ezerdi) — bu yüzden
            # küçük varyanttan üretilmiş ayrı bir PNG veriliyor.
            image = Image.open(TRAY_ICON_PATH if TRAY_ICON_PATH.exists() else ICON_PATH)
            self._icon = pystray.Icon(
                "chiron",
                image,
                "Chiron",
                menu=pystray.Menu(
                    pystray.MenuItem("Chiron'u aç", self._restore, default=True),
                    pystray.MenuItem("Çıkış", self._quit),
                ),
            )
            icon = self._icon

        self._window.hide()
        # Pencere gizlendiği an Chiron'un konuştuğunu gösteren tek şey kalmıyor
        # (3D sahnedeki çekirdek görünmüyor). Sağ üstteki ses dalgası yalnızca
        # burada devreye giriyor — pencere açıkken gereksiz, çünkü çekirdek
        # zaten konuşmayı gösteriyor. Bkz. core/speaking_overlay.py.
        speaking_overlay.set_enabled(True)
        threading.Thread(target=icon.run, name="chiron-tray", daemon=True).start()

    def _clear_icon(self) -> None:
        with self._lock:
            icon, self._icon = self._icon, None
        if icon is not None:
            icon.stop()

    def _restore(self, *_args) -> None:
        self._clear_icon()
        speaking_overlay.set_enabled(False)
        self._window.show()

    def _quit(self, *_args) -> None:
        self._clear_icon()
        speaking_overlay.shutdown()
        self._window.destroy()


def _start_voice_assistant() -> None:
    """Sesli asistanı (main.py → ChironLive) bu sürecin içinde başlatır.

    Kullanıcı isteğiyle (2026-07-29) sesli asistan ile 3D arayüz TEK UYGULAMA
    oldu. ChironLive'ın kendisi DEĞİŞMEDİ — sadece Tkinter arayüzü yerine
    core/web_ui.WebUI adaptörü veriliyor (aynı yüzey, ekrana çizmek yerine
    WebSocket'e yayın). Sesin çalıştığı bilinen kod yoluna dokunulmadı.

    Kendi asyncio döngüsünü ayrı bir thread'de kurar: pywebview ANA THREAD'i
    ister (Windows'ta pencere mesaj döngüsü orada çalışmak zorunda), backend de
    kendi thread'inde. Üç döngü birbirine karışmadan yan yana çalışıyor.
    """
    import asyncio

    from core.web_ui import WebUI

    def runner() -> None:
        try:
            # main.py import edilirken pyaudio/araçlar yükleniyor; pencere
            # açılışını geciktirmemek için burada, thread'in içinde import edilir.
            from main import ChironLive

            ui = WebUI()
            ui.wait_for_api_key()
            assistant = ChironLive(ui)
            # Arayüzün "Chiron hazır mı" sorusunu cevaplayabilmesi için geri
            # referans: canlı oturum kurulmadan gönderilen komut kayboluyor.
            ui.bind_assistant(assistant)
            asyncio.run(assistant.run())
        except Exception:
            logging.getLogger("chiron").exception("[Chiron] Sesli asistan başlatılamadı")

    threading.Thread(target=runner, name="chiron-voice", daemon=True).start()


# Arayüz kaynağı: bunlardan biri derlenmiş kopyadan (out/index.html) yeniyse açılışta yeniden derlenir.
# NEDEN (2026-10-27): kısayol desktop.py'yi doğrudan açıyor, CHIRON.bat yalnız "out yoksa" derliyordu —
# arayüz değişiklikleri haftalarca eski kopyayla açıldı ("hâlâ aynı görünüyor").
FRONTEND_SOURCES = ("app", "components", "hooks", "layouts", "public", "services", "stores", "three")
FRONTEND_CONFIGS = ("package.json", "next.config.ts", "postcss.config.mjs")
FRONTEND_BUILD_TIMEOUT = 600


def _frontend_is_stale() -> bool:
    index = FRONTEND_EXPORT_DIR / "index.html"
    if not index.exists():
        return True
    built = index.stat().st_mtime
    root = BASE_DIR / "frontend"
    for name in FRONTEND_CONFIGS:
        path = root / name
        if path.exists() and path.stat().st_mtime > built:
            return True
    for name in FRONTEND_SOURCES:
        for dirpath, _dirs, files in os.walk(root / name):
            for file in files:
                try:
                    if os.path.getmtime(os.path.join(dirpath, file)) > built:
                        return True
                except OSError:
                    continue
    return False


def _rebuild_frontend_if_stale() -> None:
    """Kaynak derlenmiş kopyadan yeniyse `npm run build` (bir iki dakika). Olmazsa eski kopyayla açılır."""
    log = logging.getLogger("chiron")
    try:
        if not _frontend_is_stale():
            return
    except Exception:
        log.exception("[Chiron] Arayüzün güncelliği denetlenemedi")
        return
    import shutil
    import subprocess

    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        log.warning("[Chiron] Arayüz eski ama npm bulunamadı; eski kopyayla açılıyor")
        return
    log.info("[Chiron] Arayüz kaynağı değişmiş, yeniden derleniyor…")
    try:
        result = subprocess.run(
            [npm, "run", "build"],
            cwd=BASE_DIR / "frontend",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=FRONTEND_BUILD_TIMEOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        log.exception("[Chiron] Arayüz derlenemedi; eski kopyayla açılıyor")
        return
    if result.returncode != 0:
        log.error("[Chiron] Arayüz derlemesi başarısız (%s): %s", result.returncode, result.stdout[-2000:])


def main() -> int:
    _rebuild_frontend_if_stale()
    if not FRONTEND_EXPORT_DIR.is_dir():
        return _fatal(
            "Arayüz henüz derlenmemiş.\n\n"
            f"Beklenen klasör:\n{FRONTEND_EXPORT_DIR}\n\n"
            "Çözüm: proje klasöründeki CHIRON.bat dosyasını bir kez çalıştır — "
            "arayüzü kendisi derler."
        )

    # Pencere oluşturulmadan önce: görev çubuğu kimliği bu aşamada okunuyor.
    _apply_taskbar_identity()

    _start_backend()
    if not _wait_for_server():
        return _fatal(f"Backend {SERVER_START_TIMEOUT:.0f} saniyede açılmadı ({URL}).")

    # --sadece-arayuz: sesli asistan olmadan yalnızca 3D sahne (tasarım üzerinde
    # çalışırken Gemini kotasını ve mikrofonu boşuna meşgul etmemek için).
    if "--sadece-arayuz" not in sys.argv:
        _start_voice_assistant()

    import webview

    # Boyut/konum burada DEĞİL, pencere göründükten sonra Win32 ile uygulanıyor
    # (bkz. WindowGeometry — pywebview'in birimleri ölçeklemeli ekranda güvenilir
    # değil). Buradaki değerler yalnızca ilk çizim için bir başlangıç.
    window = webview.create_window(
        WINDOW_TITLE,
        URL,
        width=WINDOW_SIZE[0],
        height=WINDOW_SIZE[1],
        min_size=WINDOW_MIN_SIZE,
        background_color=WINDOW_BACKGROUND,
        text_select=False,  # HUD'da metin seçimi imleci arayüzü "belge" gibi gösteriyor
    )
    WindowGeometry(window).bind()
    # İkon pencere GÖRÜNDÜKTEN sonra ayarlanıyor: HWND ancak o zaman var.
    window.events.shown += _apply_window_icon

    # "Tepsiye al" ayarlar panelinden geliyor (backend/api/settings.py → /tray),
    # komut yolu üzerinden buraya ulaşıyor.
    from backend.core import commands

    tray = TrayController(window)
    commands.register("tray", lambda _payload: tray.minimize())

    # gui="edgechromium": Windows'ta WebView2 (Chromium) motorunu ZORUNLU kılar.
    # Açıkça belirtilmezse pywebview eski MSHTML/EdgeHTML'e düşebilir — orada
    # WebGL2 ve modern CSS (backdrop-filter) çalışmaz, arayüz boş/siyah görünürdü.
    webview.start(gui="edgechromium")
    return 0


if __name__ == "__main__":
    sys.exit(main())
