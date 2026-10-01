from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import vision_worker as vw
from core.idle_model import IdleModel


def test_start_failure_returns_empty_list(monkeypatch):
    worker = vw._Worker()

    def boom():
        raise OSError("yorumlayıcı yok")

    monkeypatch.setattr(worker, "_start", boom)
    assert worker.call("ocr", b"x") == []
    assert worker._proc is None


def test_unknown_request_round_trip_and_shutdown():
    worker = vw._Worker()
    try:
        assert worker.call("bilinmeyen") == []  # çocuk hata yutar, liste döner
        assert worker._proc is not None and worker._proc.poll() is None
    finally:
        worker.shutdown()


def test_child_exits_when_parent_dies():
    # Sahte "Aıron": 2 sn yaşayıp ölen bir süreç; çocuk onun pid'ini izliyor.
    parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(2)"])
    child = subprocess.Popen(
        [sys.executable, "-m", "core.vision_worker", "--child", str(parent.pid)],
        cwd=str(PROJECT_ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        parent.wait(10)
        # stdin açık kalıyor: çocuk "ebeveyn gitti" sinyalini pipe'tan DEĞİL bekçiden almalı.
        child.wait(15)
        assert child.returncode == 0
    finally:
        if child.poll() is None:
            child.kill()
        child.stdin.close()


def test_ensure_loader_survives_release():
    loads: list[str] = []
    m = IdleModel("t", lambda: loads.append("varsayılan") or object(), idle_seconds=60)
    m.ensure(lambda: loads.append("indirmesiz") or object())
    m.release()
    with m.use():
        pass
    assert loads == ["indirmesiz", "indirmesiz"]
    m.release()
