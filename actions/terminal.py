"""Terminalde yeni sekme + Claude (İstek İ-010, 2026-10-30).

Kullanıcı: "terminalde yeni sekme aç ve Claude'a bağlan". `open_app("Terminal")` eski `cmd` penceresini açıyordu;
bu araç Windows Terminal'in SON penceresinde (`wt -w 0`, pencere yoksa yenisini kurar) istenen projenin
klasöründe bir sekme açar, istenirse içinde `claude` (ya da kaldığı yerden `claude --continue`) başlatır.

Serbest komut YOK: sekmede çalışabilecek tek şey sabit `claude` komutu, klasör de `~/Projects` altındaki bir
proje ya da ev klasörü. Serbest komut `shell_run`'ın işi (onun iki adımlı onayı var).

`;` wt'de komut ayırıcı — klasör adında geçerse komut ikiye bölünür, o yüzden öyle klasör reddedilir.
`claude` npm'in `.cmd` kabuğu; wt `.cmd`'yi doğrudan başlatamadığı için `cmd /k` içinde çalışır
(`/k`: Claude kapanınca sekme kapanmaz, kullanıcı terminalde kalır).
Kaynak: learn.microsoft.com/windows/terminal/command-line-arguments.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from actions.tool_result import fail, ok
from core.tool_registry import register_tool

PROJECTS_DIR = Path.home() / "Projects"


def _projects() -> list[Path]:
    try:
        return sorted((p for p in PROJECTS_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")),
                      key=lambda p: p.name.lower())
    except OSError:
        return []


def resolve_folder(project: str) -> Path | None:
    """Proje adını klasöre çevirir: boş → ev klasörü; tam ad (büyük/küçük harf farketmez), yoksa TEK eşleşen
    önek/parça. Birden çok ya da hiç eşleşme → None (yanlış klasörde açmaktansa sor)."""
    name = (project or "").strip().casefold()
    if not name:
        return Path.home()
    projects = _projects()
    for folder in projects:
        if folder.name.casefold() == name:
            return folder
    for match in (lambda f: f.name.casefold().startswith(name), lambda f: name in f.name.casefold()):
        found = [folder for folder in projects if match(folder)]
        if len(found) == 1:
            return found[0]
        if found:
            return None
    return None


def build_command(wt: str, folder: Path, run_claude: bool, continue_last: bool) -> list[str]:
    command = [wt, "-w", "0", "new-tab", "-d", str(folder), "--title", "Claude" if run_claude else folder.name]
    if run_claude:
        command += ["cmd", "/k", "claude --continue" if continue_last else "claude"]
    return command


@register_tool("open_terminal")
def open_terminal(project: str = "", run_claude: bool = True, continue_last: bool = False) -> dict:
    folder = resolve_folder(project)
    if folder is None:
        names = ", ".join(p.name for p in _projects()) or "yok"
        return fail(f"'{project}' projesi bulunamadı ya da birden çok eşleşti. Projeler: {names}.")
    if ";" in str(folder):
        return fail("Bu klasörün yolunda ';' var, Windows Terminal komutu bölerdi; açılmadı.")
    wt = shutil.which("wt")
    if not wt:
        return fail("Windows Terminal (wt) bulunamadı. Ayarlar > Uygulama yürütme diğer adlarında açık olmalı.")
    if run_claude and not shutil.which("claude"):
        return fail("Claude komutu bu PC'de bulunamadı.")
    try:
        subprocess.Popen(build_command(wt, folder, run_claude, continue_last), cwd=str(folder))
    except OSError as error:
        return fail(f"Terminal açılamadı: {error}")
    message = f"Terminalde {folder.name} klasöründe yeni sekme açıldı"
    if run_claude:
        message += ", Claude kaldığı yerden sürüyor" if continue_last else ", Claude başladı"
    return ok(message + ".", folder=str(folder))
