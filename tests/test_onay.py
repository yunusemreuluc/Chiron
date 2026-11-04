from __future__ import annotations

import io
import json
import sys
import threading
import time
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import onay as onay_api
from backend.core import gozetim
from backend.core.ofis import OfficeState
from backend.core.onay import OnayBroker, describe

REQ = {
    "session_id": "sess-o",
    "cwd": r"C:\Projects\Dilcep",
    "tool_name": "Bash",
    "tool_input": {"command": "npx expo export --platform android", "description": "APK dışa aktar"},
    "permission_suggestions": [{"type": "addRules", "rules": [{"toolName": "Bash", "ruleContent": "npx expo export:*"}],
                                "behavior": "allow", "destination": "localSettings"}],
}


def test_describe_masks_secrets_and_summarises():
    summary, detail = describe("Bash", {"command": "curl -H 'Authorization: Bearer abcdefghijklmnopqrstuvwx' x"})
    assert summary.startswith("Bash(") and "abcdefghijklmnop" not in summary
    s2, _ = describe("Edit", {"file_path": r"C:\a\b.py", "old_string": "x", "new_string": "y"})
    assert s2 == r"Edit(C:\a\b.py)"


def test_wait_returns_allow_with_always_rules():
    b = OnayBroker()
    rid = b.add(REQ)["id"]
    assert b.pending()[0]["project"] == "Dilcep" and b.pending()[0]["can_always"] is True

    def later():
        time.sleep(0.2)
        assert b.decide(rid, "izin", always=True) == (True, "")

    threading.Thread(target=later).start()
    res = b.wait(rid, timeout=5)
    assert res["state"] == "izin"
    assert res["updated_permissions"][0]["type"] == "addRules"
    assert b.decide(rid, "red") == (False, "Bu isteğe zaten karar verilmiş.")
    assert b.pending() == []


def test_deny_carries_message_and_terminal_release():
    b = OnayBroker()
    rid = b.add(REQ)["id"]
    b.decide(rid, "red", message="önce testleri çalıştır")
    assert b.wait(rid, 1) == {"state": "red", "message": "önce testleri çalıştır"}
    rid2 = b.add(REQ)["id"]
    b.decide(rid2, "terminal")
    assert b.wait(rid2, 1)["state"] == "terminal"


def test_deadline_expires_and_news_once():
    b = OnayBroker()
    rid = b.add(REQ, wait_s=5)["id"]
    assert [n["id"] for n in b.pop_news()] == [rid]
    assert b.pop_news() == []
    with mock.patch("backend.core.onay.time.time", return_value=time.time() + 6):
        assert b.wait(rid, 1)["state"] == "sure_doldu"
        ok, why = b.decide(rid, "izin")
        assert ok is False


def test_api_rejects_remote_request_creation():
    app = FastAPI()
    app.include_router(onay_api.router)
    client = TestClient(app)
    with mock.patch.object(onay_api, "is_remote_scope", return_value=True):
        r = client.post("/api/onay/istek", json=REQ).json()
    assert r["success"] is False
    # TestClient'ın istemcisi "testclient" — gerçek kapı onu da uzak sayar (doğru); yerel hook'u taklit et.
    with mock.patch.object(onay_api, "is_remote_scope", return_value=False):
        r = client.post("/api/onay/istek", json=REQ).json()
    assert r["success"] is True
    rid = r["data"]["id"]
    assert client.post(f"/api/onay/{rid}/karar", json={"behavior": "sil"}).status_code == 422
    assert client.post(f"/api/onay/{rid}/karar", json={"behavior": "izin"}).json()["success"] is True


def _run_hook(stdin: dict, responses: list[dict], env: dict | None = None) -> str:
    """Hook betiğini (~/.claude/hooks/chiron-onay.py) ağsız çalıştır: call() taklit edilir."""
    import importlib.util

    path = Path.home() / ".claude" / "hooks" / "chiron-onay.py"
    spec = importlib.util.spec_from_file_location("chiron_onay_hook", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    calls = iter(responses)
    out = io.StringIO()
    raw = io.BytesIO(json.dumps(stdin).encode())
    # Test Chiron'un başlattığı bir Claude oturumunda koşabilir: o zaman CHIRON_CLAUDE_JOB dışarıdan gelir.
    env = {"CHIRON_CLAUDE_JOB": "", **(env or {})}
    with mock.patch.object(mod, "call", side_effect=lambda *a, **k: next(calls)), \
         mock.patch.object(sys, "stdin", mock.Mock(buffer=raw)), \
         mock.patch.object(sys, "stdout", out), \
         mock.patch.dict("os.environ", env, clear=False):
        assert mod.main() == 0
    return out.getvalue()


def test_hook_outputs_allow_deny_and_stays_silent_otherwise():
    allow = _run_hook(REQ, [{"success": True, "data": {"id": "r1"}},
                            {"success": True, "data": {"state": "izin", "updated_permissions": [{"type": "addRules"}]}}])
    d = json.loads(allow)["hookSpecificOutput"]
    assert d["hookEventName"] == "PermissionRequest"
    assert d["decision"] == {"behavior": "allow", "updatedPermissions": [{"type": "addRules"}]}
    deny = _run_hook(REQ, [{"success": True, "data": {"id": "r1"}},
                           {"success": True, "data": {"state": "bekliyor"}},
                           {"success": True, "data": {"state": "red", "message": "yapma"}}])
    assert json.loads(deny)["hookSpecificOutput"]["decision"] == {"behavior": "deny", "message": "yapma"}
    assert _run_hook(REQ, [{"success": True, "data": {"id": "r1"}}, {"success": True, "data": {"state": "terminal"}}]) == ""
    assert _run_hook(REQ, [{"success": False}]) == ""
    # Chiron'un kendi işleri hiç sormaz
    assert _run_hook(REQ, [], env={"CHIRON_CLAUDE_JOB": "j1"}) == ""


def test_hook_silent_when_chiron_unreachable():
    def boom(*a, **k):
        raise OSError("bağlantı yok")

    import importlib.util

    path = Path.home() / ".claude" / "hooks" / "chiron-onay.py"
    spec = importlib.util.spec_from_file_location("chiron_onay_hook2", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = io.StringIO()
    with mock.patch.object(mod, "call", side_effect=boom), \
         mock.patch.object(sys, "stdin", mock.Mock(buffer=io.BytesIO(json.dumps(REQ).encode()))), \
         mock.patch.object(sys, "stdout", out):
        assert mod.main() == 0
    assert out.getvalue() == ""


def test_orbit_view_links_decisions_and_background_jobs(monkeypatch):
    now = time.time()
    st = OfficeState()
    base = {"session_id": "sess-o", "cwd": r"C:\Projects\Dilcep"}
    st.apply({**base, "event": "UserPromptSubmit", "ts": now - 30, "prompt": "apk"})
    st.apply({**base, "event": "PreToolUse", "ts": now - 20, "tool_name": "Bash", "tool_use_id": "bg1",
              "command": "npm run dev", "description": "Dev sunucusu", "background": True})
    b = OnayBroker()
    b.add(REQ)
    monkeypatch.setattr("backend.core.onay.broker", b)
    monkeypatch.setattr(gozetim.runaways, "items", lambda: [])
    monkeypatch.setattr(gozetim.runaways, "listeners",
                        lambda: [{"pid": 5, "name": "node.exe", "ports": [8081], "cwd": r"C:\Projects\Dilcep\app"}])
    v = gozetim.orbit_view(st)
    assert v["decisions"][0]["worker_id"] == "claude:sess-o"
    assert v["bg"][0]["label"] == "Dev sunucusu" and v["bg"][0]["session"] == "claude:sess-o"
    assert v["dev"][0]["ports"] == [8081] and v["dev"][0]["session"] == "claude:sess-o"
    # Bitiş bildirimi işi kapatır
    st.apply({**base, "event": "UserPromptSubmit", "ts": now - 5, "prompt":
              "<task-notification><tool-use-id>bg1</tool-use-id><status>completed</status><summary>exit code 0</summary></task-notification>"})
    assert st.bg_jobs["bg1"]["status"] == "bitti"
