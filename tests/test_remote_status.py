from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import remote


class _Jobs:
    def __init__(self, items):
        self.items = items

    def list(self):
        return self.items


class _Office:
    def __init__(self, workers=None, error: Exception | None = None):
        self.workers = workers or []
        self.error = error

    def snapshot(self):
        if self.error:
            raise self.error
        return {"workers": self.workers}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(remote.router)
    return TestClient(app)


def _patch_pc(monkeypatch) -> None:
    monkeypatch.setattr(
        remote.system_api,
        "read_pc_metrics",
        lambda: {
            "uptime_minutes": 42,
            "cpu_percent": 12.5,
            "ram_percent": 61.2,
            "battery": 73.0,
        },
    )
    monkeypatch.setattr(
        remote,
        "_read_context",
        lambda: {
            "idle_seconds": 8.5,
            "app": "Visual Studio Code",
            "window_title": "p" * 100,
        },
    )
    monkeypatch.setattr(remote, "_locked_status", lambda: False)


def test_status_is_small_truncates_and_splits_claude_jobs(monkeypatch):
    _patch_pc(monkeypatch)
    jobs = [
        {
            "id": "active-running",
            "status": "running",
            "last_step": "pytest",
            "elapsed_seconds": 17,
            "task": "t" * 140,
            "finished_at": None,
        },
        {
            "id": "old",
            "status": "done",
            "summary": "eski",
            "approval": "",
            "finished_at": 10.0,
        },
        {
            "id": "newest",
            "status": "failed",
            "summary": "s" * 350,
            "approval": "a" * 350,
            "finished_at": 50.0,
        },
        {
            "id": "active-queued",
            "status": "queued",
            "last_step": "",
            "elapsed_seconds": 0,
            "task": "sıradaki",
            "finished_at": None,
        },
        {
            "id": "middle",
            "status": "needs_approval",
            "summary": "onay bekliyor",
            "approval": "devam edeyim mi",
            "finished_at": 40.0,
        },
        {
            "id": "third",
            "status": "timeout",
            "summary": "zaman aşımı",
            "approval": "",
            "finished_at": 30.0,
        },
    ]
    monkeypatch.setattr(remote.claude_jobs, "jobs", _Jobs(jobs))
    workers = [
        {
            "name": f"Ajan {index}",
            "status": remote.WORKING,
            "current": "i" * 120,
            "title": "başlık",
            "brief": "brief",
        }
        for index in range(6)
    ]
    workers.append(
        {"name": "Boş", "status": "bosta", "current": "", "title": "", "brief": ""}
    )
    monkeypatch.setattr(remote, "office_state", _Office(workers))
    monkeypatch.setattr(remote.commands, "is_ready", lambda: True)

    with _client() as client:
        response = client.get("/api/remote/status")

    body = response.json()
    data = body["data"]
    assert response.status_code == 200
    assert body["success"] is True
    assert data["pc"] == {
        "uptime_minutes": 42,
        "cpu_percent": 12.5,
        "ram_percent": 61.2,
        "idle_seconds": 8.5,
        "locked": False,
        "battery": 73.0,
    }
    assert data["foreground"] == {"app": "Visual Studio Code", "title": "p" * 80}
    assert [job["id"] for job in data["claude"]["active"]] == [
        "active-running",
        "active-queued",
    ]
    assert len(data["claude"]["active"][0]["task"]) == 120
    assert [job["id"] for job in data["claude"]["recent"]] == [
        "newest",
        "middle",
        "third",
    ]
    assert len(data["claude"]["recent"][0]["summary"]) == 300
    assert len(data["claude"]["recent"][0]["approval"]) == 300
    assert len(data["office"]) == 5
    assert all(len(worker["task"]) == 100 for worker in data["office"])
    assert data["assistant"] == {"voice_ready": True}
    assert len(response.content) < 4096


def test_one_broken_section_does_not_hide_the_others(monkeypatch):
    _patch_pc(monkeypatch)

    class _BrokenJobs:
        def list(self):
            raise RuntimeError("job deposu okunamadı")

    monkeypatch.setattr(remote.claude_jobs, "jobs", _BrokenJobs())
    monkeypatch.setattr(remote, "office_state", _Office([]))
    monkeypatch.setattr(remote.commands, "is_ready", lambda: False)

    with _client() as client:
        response = client.get("/api/remote/status")

    data = response.json()["data"]
    assert response.status_code == 200
    assert data["claude"] is None
    assert data["pc"]["cpu_percent"] == 12.5
    assert data["foreground"]["app"] == "Visual Studio Code"
    assert data["office"] == []
    assert data["assistant"] == {"voice_ready": False}


def test_pc_and_foreground_fail_independently_and_office_errors_are_empty(monkeypatch):
    def broken_metrics():
        raise RuntimeError("psutil hatası")

    monkeypatch.setattr(remote.system_api, "read_pc_metrics", broken_metrics)
    monkeypatch.setattr(
        remote,
        "_read_context",
        lambda: {"idle_seconds": 1.0, "app": "PowerShell", "window_title": "pytest"},
    )
    monkeypatch.setattr(remote.claude_jobs, "jobs", _Jobs([]))
    monkeypatch.setattr(remote, "office_state", _Office(error=RuntimeError("ofis yok")))
    monkeypatch.setattr(remote.commands, "is_ready", lambda: True)

    with _client() as client:
        response = client.get("/api/remote/status")

    data = response.json()["data"]
    assert response.status_code == 200
    assert data["pc"] is None
    assert data["foreground"] == {"app": "PowerShell", "title": "pytest"}
    assert data["claude"] == {"active": [], "recent": []}
    assert data["office"] == []
    assert data["assistant"] == {"voice_ready": True}


def test_maximum_text_payload_stays_under_four_kilobytes(monkeypatch):
    _patch_pc(monkeypatch)
    active = [
        {
            "id": f"active-{index}",
            "status": "running",
            "last_step": "l" * 160,
            "elapsed_seconds": 999999,
            "task": "t" * 120,
            "finished_at": None,
        }
        for index in range(4)
    ]
    recent = [
        {
            "id": f"recent-{index}",
            "status": "needs_approval",
            "summary": "ö" * 300,
            "approval": "a" * 300,
            "finished_at": float(100 - index),
        }
        for index in range(3)
    ]
    workers = [
        {
            "name": "ş" * 80,
            "status": remote.WORKING,
            "current": "i" * 100,
            "title": "",
            "brief": "",
        }
        for _ in range(5)
    ]
    monkeypatch.setattr(remote.claude_jobs, "jobs", _Jobs(active + recent))
    monkeypatch.setattr(remote, "office_state", _Office(workers))
    monkeypatch.setattr(remote.commands, "is_ready", lambda: True)

    with _client() as client:
        response = client.get("/api/remote/status")

    assert response.status_code == 200
    assert len(response.content) < 4096
