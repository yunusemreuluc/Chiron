"""Ekranda açık olanı izle + "bunu nasıl yapmış, ben de istiyorum" (2026-10-31).

Yunus bir Instagram reel'inde başka birinin asistan arayüzünü gördü ve şunu istedi: sesle, yazıyla ya da
tepsideyken "ekranımda şu an açık olanı analiz et" deyince Chiron baksın; ardından "bunu nasıl yapmış, ben de
istiyorum" deyince yapsın. Ses, yazı ve tepsi aynı canlı oturumdan geçtiği için tek araç üçünü de karşılıyor.

`analyze_open_content`: önündeki pencereyi bulur — Chiron'un kendi penceresi atlanır, yazıyla sorulduğunda öndeki
pencere Chiron'dur. Tarayıcıdaysa adres çubuğundaki link (UI Automation) yt-dlp ile indirilip baştan sona izlenir:
sesli, tam video. Link video değilse ya da tarayıcı değilse ekran RECORD_SECONDS saniye kaydedilir (sessiz) ve o
kayıt izlenir — tek kare değil, çünkü istenen çoğu zaman bir akış/animasyon.

`build_like_analyzed`: son analizi (video_analysis.LAST_FILE) brief'e çevirip Komuta'ya iş olarak verir
(pc_isi.delegate_to_pc — bitince sesli haber de oradan gelir). Video dosyasının yolu brief'te: işi alan taraf
kareleri kendisi çıkarıp bakar, Gemini raporuna güvenmez.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import tempfile
from ctypes import wintypes
from pathlib import Path

import psutil

from actions import video_analysis
from actions.pc_isi import MAX_TASK_CHARS, delegate_to_pc
from actions.tool_result import fail, ok
from app_config import get_app_config_value
from core.tool_registry import register_tool

BROWSERS = {"chrome.exe", "msedge.exe", "brave.exe", "opera.exe", "vivaldi.exe", "firefox.exe"}
RECORD_SECONDS = 10
PROJECTS_DIR = Path.home() / "Projects"
DEFAULT_PROJECT = PROJECTS_DIR / "Chiron"
REPORT_CHARS = 2200  # brief MAX_TASK_CHARS'a sığsın; asıl kaynak video

_NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW: pythonw altında konsol yanıp sönmesin
_GW_HWNDNEXT = 2
_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x00000080
_DWMWA_CLOAKED = 14

# Adres çubuğu = pencerenin ilk Edit denetimi (Chrome/Edge/Brave'de dilden bağımsız; adı yerelleştirilmiş:
# "Adres ve arama çubuğu"). Windows PowerShell 5.1'in .NET UIAutomation'ı — Python'da comtypes/pywinauto yok.
# Ölçüldü 2026-10-31: ~140 ms + PowerShell açılışı.
_URL_SCRIPT = r"""
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]{hwnd})
$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)
$edit = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
if ($edit) { [Console]::Out.Write($edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value) }
"""


def _window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _window_title(hwnd: int) -> str:
    user32 = ctypes.windll.user32
    buffer = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(hwnd) + 1)
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value.strip()


def _is_candidate(hwnd: int, own_pid: int) -> bool:
    user32 = ctypes.windll.user32
    if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd) or not _window_title(hwnd):
        return False
    if user32.GetWindowLongW(hwnd, _GWL_EXSTYLE) & _WS_EX_TOOLWINDOW:
        return False
    cloaked = wintypes.DWORD()  # arka plandaki UWP pencereleri "görünür" ama ekranda yok
    ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, _DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    return not cloaked.value and _window_pid(hwnd) != own_pid


def _target_window() -> tuple[int, str, str, bool]:
    """(hwnd, başlık, süreç adı, chiron_ondeydi). Öndeki pencereden Z-sırasında aşağı iner, Chiron'un kendi
    pencerelerini (aynı süreç: WebView2 penceresi, konuşma göstergesi) atlar."""
    user32 = ctypes.windll.user32
    own_pid = os.getpid()
    hwnd = user32.GetForegroundWindow()
    chiron_front = bool(hwnd) and _window_pid(hwnd) == own_pid
    while hwnd:
        if _is_candidate(hwnd, own_pid):
            try:
                process = psutil.Process(_window_pid(hwnd)).name().lower()
            except psutil.Error:
                process = ""
            return hwnd, _window_title(hwnd), process, chiron_front
        hwnd = user32.GetWindow(hwnd, _GW_HWNDNEXT)
    return 0, "", "", chiron_front


def _browser_url(hwnd: int) -> str:
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _URL_SCRIPT.replace("{hwnd}", str(hwnd))],
            capture_output=True, text=True, encoding="utf-8", timeout=10, creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    value = (result.stdout or "").strip()
    # Adres çubuğunda yazılmakta olan bir arama da olabilir: boşluklu ya da noktasızsa link değil.
    if not value or " " in value or "." not in value.split("/")[0]:
        return ""
    return value if value.startswith(("http://", "https://")) else f"https://{value}"


def _record_screen(path: str) -> str:
    """Tüm masaüstünü RECORD_SECONDS saniye kaydeder; hata metni döner (boşsa başarılı)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return "Ekranı kaydetmek için ffmpeg bulunamadı."
    try:
        result = subprocess.run(
            [ffmpeg, "-v", "error", "-y", "-f", "gdigrab", "-framerate", "8", "-i", "desktop",
             "-t", str(RECORD_SECONDS), "-vf", "scale=trunc(min(1280\\,iw)/2)*2:-2",
             "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", path],
            capture_output=True, text=True, timeout=RECORD_SECONDS + 30, creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"Ekran kaydı alınamadı ({error.__class__.__name__})."
    if result.returncode != 0 or not Path(path).exists():
        return f"Ekran kaydı alınamadı: {(result.stderr or '').strip()[:200]}"
    return ""


@register_tool("analyze_open_content")
def analyze_open_content(question: str = "") -> dict:
    api_key = str(get_app_config_value("gemini_api_key", "") or "").strip()
    if not api_key:
        return fail("Gemini API anahtarı eksik olduğu için analiz yapılamadı.")

    hwnd, title, process, chiron_front = _target_window()
    url = _browser_url(hwnd) if hwnd and process in BROWSERS else ""

    tmp_dir = tempfile.mkdtemp(prefix="chiron-ekran-")
    try:
        video_path, label, kind, note = "", "", "", ""
        if url:
            dl_ok, result, video_title, dl_dir = video_analysis._download_video(url)
            if dl_ok:
                video_path, label, kind = result, video_title or url, "video"
                tmp_dir, dl_dir = dl_dir, tmp_dir  # indirme kendi klasöründe; ikisi de silinsin
                shutil.rmtree(dl_dir, ignore_errors=True)
        if not video_path:
            url = ""  # sayfa video değil: kaydın kaynağı link değil, ekran
            video_path = str(Path(tmp_dir) / "ekran.mp4")
            error = _record_screen(video_path)
            if error:
                return fail(error + " Tek kare için analyze_screen kullanılabilir.")
            label, kind = f"{RECORD_SECONDS} sn ekran kaydı (sessiz) — öndeki pencere: {title or 'bilinmiyor'}", "ekran"
            if chiron_front:
                note = (" Not: Chiron'un penceresi öndeydi, kayıtta Chiron görünüyor olabilir; öyleyse kullanıcıya "
                        "Chiron'u tepsiye alıp tekrar istemesini söyle.")

        analysis = video_analysis.analyze_file(video_path, question, label, api_key)
        try:
            video_analysis.remember_analysis(url=url, label=label, report=analysis, video_path=video_path,
                                             owned=True, kind=kind)
        except Exception:
            pass
        source = f"[Link: {url}]" if url else f"[{label}]"
        return ok(f"{source}\n{analysis}{note}", label=label, url=url, kind=kind)
    except Exception as error:
        return fail(f"Analiz tamamlanamadı: {error}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _brief(last: dict, request: str, project: str) -> str:
    target = (f"{project} (projeler {PROJECTS_DIR} altında)" if project
              else f"belirtilmedi — varsayılan Chiron ({DEFAULT_PROJECT}); kullanıcının sözünden başka bir proje "
                   "kastettiği açıksa ona uygula")
    video = last.get("video_path") or ""
    head = "\n".join([
        f'Kullanıcı az önce şunu izletti ve "nasıl yapmış, ben de istiyorum" dedi. Sözü: "{request or "ben de istiyorum"}"',
        f"Kaynak: {last.get('url') or last.get('label') or 'bilinmiyor'}",
        (f"Video dosyası: {video} — ffmpeg ile kareler çıkarıp (ör. 2 sn'de bir, tile ile tek görsel) KENDİN bak; "
         "aşağıdaki özet Gemini'nin iddiası, doğrula." if video and Path(video).exists()
         else "Video dosyası yok — yalnız aşağıdaki özet var, linkten tekrar indirebilirsin."),
        f"Hedef proje: {target}",
        "Yapılacak: 1) Ne gösterildiğini ve nasıl yapılmış olabileceğini çıkar (yapı, animasyon, kütüphane). "
        "2) Hedef projeye uygula, projenin CLAUDE.md kurallarına uy, birebir kopya değil projenin diline uyarlanmış "
        "hali. 3) Bitince kısaca ne yaptığını ve onun nasıl yapıldığını anlat.",
        "Gemini özeti:",
    ])
    room = max(0, min(REPORT_CHARS, MAX_TASK_CHARS - len(head) - 10))
    report = str(last.get("report") or "").strip()
    return f"{head}\n{report[:room]}"


@register_tool("build_like_analyzed")
def build_like_analyzed(request: str = "", project: str = "") -> dict:
    last = video_analysis.last_analysis()
    if not last:
        return fail("Henüz analiz edilmiş bir şey yok. Önce ekrandakini ya da bir videoyu analiz ettir.")
    return delegate_to_pc(_brief(last, request.strip(), project.strip()), new_topic=True)
