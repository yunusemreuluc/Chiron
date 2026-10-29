"""PC'deki sesli Chiron'un iş vermesi (delegate_to_pc) ve Komuta ucunun yerel/uzak ayrımı."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from actions import pc_isi  # noqa: E402
from backend.core.sohbet import Sohbet  # noqa: E402


class _Response:
    def __init__(self, data: dict) -> None:
        self._data = data

    def json(self) -> dict:
        return self._data


def test_delegate_posts_to_komuta(monkeypatch):
    calls = []

    def post(url, json, timeout):
        calls.append((url, json))
        return _Response({"success": True, "data": {"title": "Dilcep", "job_id": "j1"}})

    monkeypatch.setattr(pc_isi.requests, "post", post)
    result = pc_isi.delegate_to_pc("Dilcep'te alt barı kırmızı yap")
    assert result["success"] and result["data"] == {"chat": "Dilcep", "job_id": "j1"}
    assert calls == [(pc_isi.KOMUTA_URL, {"text": "Dilcep'te alt barı kırmızı yap", "new_topic": False})]


def test_delegate_reports_busy_and_unreachable(monkeypatch):
    monkeypatch.setattr(pc_isi.requests, "post", lambda *a, **k: _Response({"success": False, "message": "önceki iş sürüyor"}))
    busy = pc_isi.delegate_to_pc("bir de şunu")
    assert not busy["success"] and "new_topic=true" in busy["message"]

    def down(*a, **k):
        raise ConnectionError("kapalı")

    monkeypatch.setattr(pc_isi.requests, "post", down)
    assert not pc_isi.delegate_to_pc("x")["success"]
    assert not pc_isi.delegate_to_pc("   ")["success"]


def test_pc_voice_task_is_not_notified_to_phone(tmp_path):
    """Yerel (PC sesli) iş origin=sohbet: telefona bildirim gitmez; telefondan gelen sohbet_tel."""
    calls = []

    class Jobs:
        def submit(self, task, resume_of=None, origin="telefon", cwd=None, engine="claude", mode="auto", session_id=None):
            calls.append(origin)
            return SimpleNamespace(id=f"j{len(calls)}")

        def get(self, job_id):
            return {"id": job_id, "status": "done", "summary": "ok", "finished_at": time.time(), "trail": []}

    store = Sohbet(tmp_path / "s.json", jobs=Jobs(), projects_dir=tmp_path / "p", session_active=lambda s: False)
    store.phone_task("PC'den iş", via="pc")
    store.phone_task("telefondan iş", new_topic=True)
    assert calls == ["sohbet", "sohbet_tel"]
