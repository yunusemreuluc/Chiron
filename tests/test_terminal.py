"""Terminalde yeni sekme + Claude (open_terminal, İstek İ-010)."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from actions import terminal  # noqa: E402


def _projects(tmp_path, monkeypatch, *names):
    for name in names:
        (tmp_path / name).mkdir()
    monkeypatch.setattr(terminal, "PROJECTS_DIR", tmp_path)


def test_resolve_exact_prefix_and_ambiguous(tmp_path, monkeypatch):
    _projects(tmp_path, monkeypatch, "Chiron", "chiron-mobile", "dilcep", ".pano-worktrees")
    assert terminal.resolve_folder("chiron") == tmp_path / "Chiron"  # tam ad, önek çakışmasına rağmen
    assert terminal.resolve_folder("Dilc") == tmp_path / "dilcep"
    assert terminal.resolve_folder("mobile") == tmp_path / "chiron-mobile"
    assert terminal.resolve_folder("chi") is None  # iki eşleşme: yanlış klasörde açma
    assert terminal.resolve_folder("pano") is None  # gizli klasörler proje değil
    assert terminal.resolve_folder("") == Path.home()


def test_build_command_runs_only_claude(tmp_path):
    cmd = terminal.build_command("wt", tmp_path, run_claude=True, continue_last=True)
    assert cmd == ["wt", "-w", "0", "new-tab", "-d", str(tmp_path), "--title", "Claude", "cmd", "/k", "claude --continue"]
    plain = terminal.build_command("wt", tmp_path, run_claude=False, continue_last=False)
    assert plain[-2:] == ["--title", tmp_path.name] and "cmd" not in plain


def test_open_terminal_launches_and_reports(tmp_path, monkeypatch):
    _projects(tmp_path, monkeypatch, "dilcep")
    launched = []
    monkeypatch.setattr(terminal.shutil, "which", lambda name: f"C:/bin/{name}.exe")
    monkeypatch.setattr(terminal.subprocess, "Popen", lambda cmd, cwd: launched.append((cmd, cwd)))
    result = terminal.open_terminal("Dilcep")
    assert result["success"] and "dilcep" in result["message"]
    assert launched[0][0][-1] == "claude" and launched[0][1] == str(tmp_path / "dilcep")


def test_open_terminal_fails_honestly(tmp_path, monkeypatch):
    _projects(tmp_path, monkeypatch, "dilcep")
    monkeypatch.setattr(terminal.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("açılmamalı")))
    monkeypatch.setattr(terminal.shutil, "which", lambda name: None)
    assert not terminal.open_terminal("dilcep")["success"]  # wt yok
    unknown = terminal.open_terminal("yok-boyle")
    assert not unknown["success"] and "dilcep" in unknown["message"]
    monkeypatch.setattr(terminal.shutil, "which", lambda name: "C:/bin/wt.exe" if name == "wt" else None)
    assert "Claude" in terminal.open_terminal("dilcep")["message"]  # claude kurulu değil
