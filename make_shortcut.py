"""
Chiron kısayol yardımcıları — Windows sürümü.

macOS sürümü .app/.command ve LaunchAgent plist üretiyordu; Windows'ta
bunların karşılığı .lnk kısayollarıdır:
  - Masaüstü kısayolu  → Desktop\\Chiron.lnk
  - Açılışta başlat     → Başlangıç klasörü\\Chiron.lnk

PowerShell WScript.Shell kullanılır, ek bağımlılık gerekmez.
Kısayollar pythonw.exe ile desktop.py'yi konsolsuz başlatır.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _desktop_dir() -> Path:
    """OneDrive masaüstü veya klasik masaüstünü bulur."""
    candidates = []
    one = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer")
    if one:
        candidates.append(Path(one) / "Desktop")
    candidates.append(Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]


def _startup_dir() -> Path:
    """Windows Başlangıç klasörü (açılışta otomatik çalışanlar)."""
    return (
        Path(os.environ.get("APPDATA", str(Path.home())))
        / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    )


def _pythonw() -> str:
    """Konsolsuz başlatma için pythonw.exe, yoksa python.exe."""
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    return str(pyw if pyw.exists() else exe)


# Tek uygulama: desktop.py (3D arayüz + sesli asistan aynı süreçte).
# 2026-07-29'a kadar burada bir de "voice" (main.py, Tkinter penceresi) vardı;
# o arayüz kaldırıldı, main.py artık giriş noktası değil.
APPS = {
    "desktop": ("desktop.py", "Chiron"),
}


def _write_shortcut(link_path: Path, app: str = "desktop") -> Path:
    """Verilen yola Chiron .lnk kısayolu yazar."""
    if app not in APPS:
        raise ValueError(f"Bilinmeyen uygulama: {app!r} (geçerli: {', '.join(APPS)})")

    link_path.parent.mkdir(parents=True, exist_ok=True)
    target = _pythonw()
    script_name, description = APPS[app]
    script_path = BASE_DIR / script_name

    icon_line = ""
    ico_candidate = BASE_DIR / "Icon" / "chiron.ico"
    if ico_candidate.exists():
        icon_line = f"$s.IconLocation = '{ico_candidate}'; "

    ps_script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{link_path}'); "
        f"$s.TargetPath = '{target}'; "
        f"$s.Arguments = '\"{script_path}\"'; "
        f"$s.WorkingDirectory = '{BASE_DIR}'; "
        f"$s.Description = '{description}'; "
        f"{icon_line}"
        "$s.Save()"
    )

    result = subprocess.run(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
        capture_output=True,
        text=True,
        timeout=20,
        creationflags=_CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(detail or "Kısayol oluşturulamadı.")
    return link_path


# ── Masaüstü kısayolu ────────────────────────────────────────────────────────
_SHORTCUT_NAMES = {"desktop": "Chiron.lnk"}


def desktop_shortcut_path(app: str = "desktop") -> Path:
    return _desktop_dir() / _SHORTCUT_NAMES[app]


def create_desktop_shortcut(app: str = "desktop") -> Path:
    return _write_shortcut(desktop_shortcut_path(app), app)


# ── Açılışta başlat (Başlangıç klasörü) ──────────────────────────────────────
def startup_shortcut_path() -> Path:
    return _startup_dir() / "Chiron.lnk"


def create_startup_shortcut(app: str = "desktop") -> Path:
    return _write_shortcut(startup_shortcut_path(), app)


def remove_startup_shortcut() -> None:
    path = startup_shortcut_path()
    if path.exists():
        path.unlink()


if __name__ == "__main__":
    created = create_desktop_shortcut()
    print(f"Masaüstü kısayolu oluşturuldu: {created}")
