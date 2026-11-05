"""Gözetim oturum kontrolü — geri alma planı/uygulaması ve kayıt özeti (backend/core/oturum_kontrol.py)."""

import json
from pathlib import Path

import pytest

from backend.core import oturum_kontrol as ok

SID = "11111111-2222-3333-4444-555555555555"


def _write_use(tid: str, name: str, path: str) -> dict:
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": tid, "name": name, "input": {"file_path": path}}]}}


def _result(tid: str, created: bool = False, error: bool = False) -> dict:
    rec = {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": tid, "is_error": error, "content": "ok"}]}}
    rec["toolUseResult"] = {"type": "create" if created else "update"}
    return rec


@pytest.fixture
def world(tmp_path, monkeypatch):
    hist = tmp_path / "file-history"
    monkeypatch.setattr(ok, "FILE_HISTORY", hist)
    monkeypatch.setattr(ok, "UNDO_ROOT", tmp_path / "undo")
    monkeypatch.setattr(ok, "CLAUDE_HOME", tmp_path)
    work = tmp_path / "proje"
    work.mkdir()
    edited = work / "eski.txt"       # oturumdan önce vardı, düzenlendi
    created = work / "yeni.txt"      # oturum oluşturdu
    blind = work / "yedeksiz.txt"    # düzenlendi ama yedeği yok → dokunulmaz
    same = work / "ayni.txt"         # düzenlendi, sonra eski haline döndü
    edited.write_text("SONRA", encoding="utf-8")
    created.write_text("YENI", encoding="utf-8")
    blind.write_text("B", encoding="utf-8")
    same.write_text("A", encoding="utf-8")
    sdir = hist / SID
    sdir.mkdir(parents=True)
    (sdir / f"{ok._hash(str(edited))}@v1").write_text("ONCE", encoding="utf-8")
    (sdir / f"{ok._hash(str(same))}@v1").write_text("A", encoding="utf-8")
    recs = [
        {"type": "user", "message": {"content": "mobil uygulamaya telefon kontrolü ekle"}},
        _write_use("t1", "Edit", str(edited)), _result("t1"),
        _write_use("t2", "Write", str(created)), _result("t2", created=True),
        _write_use("t3", "Edit", str(blind)), _result("t3"),
        _write_use("t4", "Edit", str(same)), _result("t4"),
        _write_use("t5", "Edit", str(work / "hatali.txt")), _result("t5", error=True),
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Bitti, derledim."}]}},
    ]
    (tmp_path / "projects" / "p").mkdir(parents=True)
    transcript = tmp_path / "projects" / "p" / f"{SID}.jsonl"
    transcript.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs), encoding="utf-8")
    return {"t": str(transcript), "edited": edited, "created": created, "blind": blind, "same": same}


def test_plan_actions(world):
    p = ok.plan(SID, world["t"])
    acts = {Path(i["path"]).name: i["action"] for i in p["items"]}
    assert acts == {"eski.txt": "geri", "yeni.txt": "sil", "yedeksiz.txt": "atla", "ayni.txt": "ayni"}
    # plan hiçbir şeye dokunmaz
    assert world["created"].exists() and world["edited"].read_text(encoding="utf-8") == "SONRA"


def test_apply_restores_deletes_and_keeps_copies(world):
    res = ok.apply(SID, world["t"])
    assert (res["geri"], res["sil"], res["hata"], res["skipped"]) == (1, 1, 0, 1)
    assert world["edited"].read_text(encoding="utf-8") == "ONCE"
    assert not world["created"].exists()
    assert world["blind"].read_text(encoding="utf-8") == "B"
    undo = Path(res["undo_dir"])
    manifest = json.loads((undo / "manifest.json").read_text(encoding="utf-8"))
    saved = {Path(f["path"]).name: (undo / f["saved"]).read_text(encoding="utf-8") for f in manifest["files"]}
    assert saved == {"eski.txt": "SONRA", "yeni.txt": "YENI"}


def test_plan_without_transcript():
    assert ok.plan(None, None)["ok"] is False


def test_digest_has_task_reply_and_tools(world):
    d = ok.digest(world["t"])
    assert "[YUNUS] mobil uygulamaya" in d
    assert "[OTURUM] Bitti, derledim." in d
    assert "Write" in d and "yeni.txt" in d


def test_stop_without_process_is_not_found_not_closed(monkeypatch):
    monkeypatch.setattr(ok, "find_process", lambda *a: None)
    assert ok.stop(None, None, SID)[0] == ok.NOT_FOUND


def test_plan_rejects_foreign_transcript(world, tmp_path):
    outside = tmp_path / "baska.jsonl"
    outside.write_text(Path(world["t"]).read_text(encoding="utf-8"), encoding="utf-8")
    assert ok.plan(SID, str(outside))["ok"] is False
    assert ok.plan("../../x", world["t"])["ok"] is False


def test_subagent_created_file_counts_as_created_even_if_main_writes_later(world, tmp_path):
    """Alt ajan oluşturur, ana döngü SONRA yazar: kayıt sırası değil zaman belirler."""
    late = tmp_path / "proje" / "alt.txt"
    late.write_text("X", encoding="utf-8")
    main = Path(world["t"])
    recs = [_write_use("m1", "Write", str(late)), _result("m1")]
    recs[0]["timestamp"] = recs[1]["timestamp"] = "2026-11-05T02:00:00Z"
    with main.open("a", encoding="utf-8") as f:
        f.write("\n" + "\n".join(json.dumps(r) for r in recs))
    subs = main.parent / main.stem / "subagents"
    subs.mkdir(parents=True)
    srecs = [_write_use("s1", "Write", str(late)), _result("s1", created=True)]
    srecs[0]["timestamp"] = srecs[1]["timestamp"] = "2026-11-05T01:00:00Z"
    (subs / "agent-a.jsonl").write_text("\n".join(json.dumps(r) for r in srecs), encoding="utf-8")
    acts = {Path(i["path"]).name: i["action"] for i in ok.plan(SID, world["t"])["items"]}
    assert acts["alt.txt"] == "sil"


def test_kill_tree_refuses_tree_containing_chiron(monkeypatch):
    """Korunan süreç hedefin ALT ağacındaysa (Chiron oturumun içinden başlatılmış) hiçbiri kapanmaz."""
    import subprocess
    import sys
    import time

    import psutil

    code = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); time.sleep(30)"
    top = subprocess.Popen([sys.executable, "-c", code])
    try:
        proc = psutil.Process(top.pid)
        for _ in range(50):
            kids = proc.children(recursive=True)
            if kids:
                break
            time.sleep(0.1)
        assert kids
        monkeypatch.setattr(ok, "_protected", lambda: {kids[-1].pid})
        with pytest.raises(RuntimeError):
            ok.kill_tree(proc)
        assert proc.is_running() and kids[-1].is_running()
    finally:
        for x in psutil.Process(top.pid).children(recursive=True) + [psutil.Process(top.pid)]:
            try:
                x.kill()
            except psutil.NoSuchProcess:
                pass
