"""Son konuşma: sesli oturumlar arası kısa hafıza (memory/son_konusma.py, 2026-10-30)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from memory import son_konusma  # noqa: E402


def test_recent_lines_go_into_next_session(tmp_path, monkeypatch):
    monkeypatch.setattr(son_konusma, "STORE", tmp_path / "son_konusma.json")
    assert son_konusma.prompt_block() == ""
    son_konusma.add("Kullanıcı", "Dilcep'te  alt barı\nyeşil yap")
    son_konusma.add("Chiron", "Hallediyorum.")
    son_konusma.add("Chiron", "   ")  # boş satır yazılmaz

    block = son_konusma.prompt_block()
    assert block.startswith("[ÖNCEKİ KONUŞMA]")
    assert "Kullanıcı: Dilcep'te alt barı yeşil yap" in block and "Chiron: Hallediyorum." in block

    assert son_konusma.prompt_block(now=time.time() + 13 * 3600) == ""  # 12 saatten eski unutulur


def test_keeps_only_last_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(son_konusma, "STORE", tmp_path / "son_konusma.json")
    for i in range(son_konusma.MAX_LINES + 5):
        son_konusma.add("Kullanıcı", f"satır {i}")
    lines = son_konusma.recent()
    assert len(lines) == son_konusma.MAX_LINES and lines[-1]["text"] == f"satır {son_konusma.MAX_LINES + 4}"
