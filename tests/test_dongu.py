"""7/24 döngü (Ajan İstasyonu adım 8): sırayla başlatma, kota uykusu, günlük sınır, sabah raporu."""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.api import pano as pano_api  # noqa: E402
from backend.core import dongu as dongu_mod  # noqa: E402
from backend.core.dongu import Dongu, next_report_at, render_report  # noqa: E402
from backend.core.pano import Pano  # noqa: E402


class Jobs:
    """Elle sürülen iş kuyruğu + Claude kota kaydı."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.engines: list[str] = []
        self.quota: dict = {}

    def submit(self, task, resume_of=None, origin="telefon", cwd=None, engine="claude", mode="auto"):
        job_id = f"j{len(self.jobs) + 1}"
        self.engines.append(engine)
        self.jobs[job_id] = {"id": job_id, "status": "queued", "summary": "", "session_id": None, "approval": "",
                             "error": "", "steps": 0, "last_step": "", "cost_usd": 0.1}
        return SimpleNamespace(id=job_id)

    def get(self, job_id):
        job = self.jobs.get(job_id)
        return dict(job) if job else None

    def cancel(self, job_id):
        return True

    def limits(self):
        return dict(self.quota)

    def finish(self, job_id: str, **values) -> None:
        self.jobs[job_id].update({"status": "done", "summary": "Tamam."} | values)


class Clock:
    def __init__(self, ts: float) -> None:
        self.ts = ts

    def __call__(self) -> float:
        return self.ts


def _setup(tmp_path: Path, ts: float | None = None) -> tuple[Pano, Jobs, Dongu, Clock]:
    jobs = Jobs()
    board = Pano(store_path=tmp_path / "pano.json", jobs=jobs)
    clock = Clock(ts or datetime(2026, 10, 26, 22, 0).timestamp())
    loop = Dongu(board, tmp_path / "dongu.json", tmp_path / "rapor", clock=clock)
    return board, jobs, loop, clock


def _status(board: Pano, card_id: str) -> str:
    return board.get(card_id)["status"]


def test_closed_loop_does_nothing(tmp_path):
    board, jobs, loop, _ = _setup(tmp_path)
    board.create("İş")
    loop.tick()
    assert jobs.jobs == {} and loop.public()["durum"] == "kapali"


def test_runs_oldest_ready_card_one_at_a_time(tmp_path):
    board, jobs, loop, _ = _setup(tmp_path)
    first = board.create("Birinci")["id"]
    time.sleep(0.01)
    second = board.create("İkinci")["id"]
    loop.set_open(True)

    loop.tick()
    loop.tick()  # birinci sürerken ikinci başlamaz
    assert (_status(board, first), _status(board, second)) == ("calisiyor", "bekliyor")
    assert loop.public()["durum"] == "calisiyor"

    jobs.finish("j1")
    loop.tick()
    assert (_status(board, first), _status(board, second)) == ("bitti", "calisiyor")
    assert loop.public()["baslatilan"] == 2


def test_dependencies_order_and_waiting_cards_do_not_block(tmp_path):
    board, jobs, loop, _ = _setup(tmp_path)
    loop.set_open(True)
    a = board._new_card("A", "", None, None, "claude")  # Chiron'un alt kartları gibi
    b = board._new_card("B", "", None, None, "claude", after=[a["id"]])
    lone = board._new_card("Bağımsız", "", None, None, "claude")
    loop.tick()
    assert _status(board, a["id"]) == "calisiyor"
    jobs.jobs["j1"].update(status="needs_approval", approval="sil?")
    loop.tick()  # A onay bekliyor: B bekler ama bağımsız kart yürür
    assert (_status(board, a["id"]), _status(board, b["id"]), _status(board, lone["id"])) == (
        "onay", "bekliyor", "calisiyor")


def test_quota_stop_sleeps_claude_but_runs_gemini_and_wakes_after_reset(tmp_path):
    board, jobs, loop, _ = _setup(tmp_path)
    resets = time.time() + 2
    jobs.quota = {"ts": time.time(), "five_hour": {"used": 0.95, "resets_at": resets}}
    claude = board.create("Claude işi")["id"]
    gemini = board.create("Okuma", agent="gemini")["id"]
    loop.set_open(True)

    loop.tick()
    assert (_status(board, claude), _status(board, gemini)) == ("bekliyor", "calisiyor")
    jobs.finish("j1")
    loop.tick()
    state = loop.public()
    assert state["durum"] == "uyuyor" and "%95" in state["neden"]

    jobs.quota["five_hour"]["resets_at"] = time.time() - 1  # pencere sıfırlandı
    loop.tick()
    assert _status(board, claude) == "calisiyor"


def test_daily_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(dongu_mod, "DAILY_LIMIT", 1)
    board, jobs, loop, clock = _setup(tmp_path)
    board.create("Bir")
    board.create("İki")
    loop.set_open(True)
    loop.tick()
    jobs.finish("j1")
    loop.tick()
    assert loop.public()["durum"] == "sinir" and len(jobs.jobs) == 1
    clock.ts += 86400  # ertesi gün sayaç sıfırlanır
    loop.tick()
    assert len(jobs.jobs) == 2


def test_failed_start_is_skipped_not_retried_every_tick(tmp_path):
    board, jobs, loop, _ = _setup(tmp_path)
    bad = board.create("Repo kartı")["id"]
    board._find(bad)["repo"] = str(tmp_path / "yok")  # worktree açılamaz
    good = board.create("Sağlam")["id"]
    loop.set_open(True)
    loop.tick()
    assert (_status(board, bad), _status(board, good)) == ("bekliyor", "calisiyor")
    assert any("başlatılamadı" in e["metin"] for e in loop.public()["olaylar"])


def test_state_persists_and_morning_report(tmp_path):
    board, jobs, loop, clock = _setup(tmp_path, time.time())
    done = board.create("Biten iş")["id"]
    board.create("Onaylık iş")
    loop.set_open(True)
    loop.tick()
    jobs.finish("j1", summary="Dosya yazıldı.")
    loop.tick()
    jobs.jobs["j2"].update(status="needs_approval", approval="push?")
    board._find(done)["bekci"] = [{"ad": "git push", "engellendi": True, "at": clock.ts + 1}]

    clock.ts = next_report_at(time.time()) + 30
    loop.tick()
    report = loop.public()["rapor"]
    assert [r["id"] for r in report["bitti"]] == [done]
    assert [r["durum"] for r in report["bekliyor_yunus"]] == ["onay"]
    assert report["bekci"] == [{"kart": done, "ad": "git push", "engellendi": True}]
    day = datetime.fromtimestamp(clock.ts).strftime("%Y-%m-%d")
    text = (tmp_path / "rapor" / f"rapor-{day}.md").read_text(encoding="utf-8")
    assert "Biten iş" in text and "durduruldu" in text

    loop.tick()  # aynı sabah ikinci rapor yok
    assert loop.public()["rapor"]["at"] == report["at"]

    again = Dongu(board, tmp_path / "dongu.json", tmp_path / "rapor", clock=clock)
    assert again.public()["acik"] is True and again.public()["rapor"]["at"] == report["at"]


def test_next_report_at_and_render():
    evening = datetime(2026, 10, 26, 22, 0).timestamp()
    morning = datetime(2026, 10, 27, 7, 59).timestamp()
    assert datetime.fromtimestamp(next_report_at(evening)) == datetime(2026, 10, 27, 8, 0)
    assert datetime.fromtimestamp(next_report_at(morning)) == datetime(2026, 10, 27, 8, 0)
    text = render_report({"at": morning, "since": evening, "bitti": [], "bekliyor_yunus": [], "hata": [],
                          "sirada": 3, "bekci": [], "maliyet_usd": 0.4, "kota": "rahat"})
    assert "Sırada 3 kart" in text and "## Bitti (0)" in text


def test_loop_api(tmp_path, monkeypatch):
    board, _, loop, _ = _setup(tmp_path)
    monkeypatch.setattr(pano_api, "pano", board)
    monkeypatch.setattr(pano_api, "dongu", loop)
    app = FastAPI()
    app.include_router(pano_api.router)
    with TestClient(app) as client:
        opened = client.post("/api/pano/dongu", json={"acik": True})
        listed = client.get("/api/pano")
        closed = client.post("/api/pano/dongu", json={"acik": False})
    assert opened.json()["data"]["dongu"]["acik"] is True
    assert listed.json()["data"]["dongu"]["durum"] in ("bekliyor", "calisiyor")
    assert closed.json()["data"]["dongu"]["durum"] == "kapali"
