from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.api import remote
from backend.core import remote_auth


@pytest.fixture(autouse=True)
def isolated_remote_config(monkeypatch):
    """Gerçek app config'ine hiç dokunmadan her teste temiz durum verir."""
    config: dict[str, object] = {}

    def load_config() -> dict[str, object]:
        return dict(config)

    def save_config(updates: dict) -> dict[str, object]:
        config.update({key: value for key, value in updates.items() if value is not None})
        return dict(config)

    monkeypatch.setattr(remote_auth, "load_app_config", load_config)
    monkeypatch.setattr(remote_auth, "save_app_config", save_config)
    remote_auth._failures = 0
    remote_auth._locked_until = 0.0
    yield config
    remote_auth._failures = 0
    remote_auth._locked_until = 0.0


def _scope(
    *,
    server=("127.0.0.1", remote_auth.LOCAL_PORT),
    client=("127.0.0.1", 50000),
    headers=((b"host", b"localhost:8000"),),
) -> dict:
    return {"type": "http", "server": server, "client": client, "headers": list(headers)}


@pytest.mark.parametrize(
    "host",
    [b"localhost:8000", b"127.0.0.1:8000", b"[::1]:8000"],
)
def test_is_remote_scope_accepts_only_local_request_shape(host):
    assert remote_auth.is_remote_scope(_scope(headers=((b"host", host),))) is False


@pytest.mark.parametrize(
    "scope",
    [
        _scope(server=("127.0.0.1", remote_auth.REMOTE_PORT)),
        _scope(client=("100.64.0.2", 50000)),
        _scope(headers=((b"host", b"localhost:8000"), (b"x-forwarded-for", b"100.64.0.2"))),
        _scope(headers=((b"host", b"localhost:8000"), (b"tailscale-user-login", b"user@example.com"))),
        _scope(headers=((b"host", b"chiron.tailnet.ts.net"),)),
        _scope(server=None),
        _scope(client=None),
    ],
)
def test_is_remote_scope_rejects_any_nonlocal_or_unknown_signal(scope):
    assert remote_auth.is_remote_scope(scope) is True


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/m", True),
        ("/api/remote/login", True),
        ("/_next/static/chunk.js", True),
        ("/api/office/state", False),
        ("/api/system/telemetry", False),
    ],
)
def test_is_public_path_has_a_narrow_allowlist(path, expected):
    assert remote_auth.is_public_path(path) is expected


def test_pin_can_be_set_and_used_for_login():
    assert remote_auth.pin_is_set() is False
    remote_auth.set_pin("123456")
    assert remote_auth.pin_is_set() is True
    assert remote_auth.attempt_login("123456")[0] is True
    assert remote_auth.attempt_login("654321")[0] is False


def test_login_locks_after_free_attempts_and_recovers_after_timeout(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(remote_auth.time, "monotonic", lambda: clock["now"])
    remote_auth.set_pin("123456")

    for _ in range(remote_auth._FREE_ATTEMPTS):
        ok, _ = remote_auth.attempt_login("000000")
        assert ok is False

    assert remote_auth.lock_remaining() > 0
    assert remote_auth.attempt_login("123456")[0] is False

    clock["now"] += remote_auth._BASE_LOCK_SECONDS + 1
    assert remote_auth.lock_remaining() == 0
    assert remote_auth.attempt_login("123456")[0] is True


def test_login_backoff_never_exceeds_maximum(monkeypatch):
    clock = {"now": 2000.0}
    monkeypatch.setattr(remote_auth.time, "monotonic", lambda: clock["now"])
    remote_auth.set_pin("123456")

    longest_lock = 0
    for _ in range(remote_auth._FREE_ATTEMPTS + 8):
        assert remote_auth.attempt_login("000000")[0] is False
        remaining = remote_auth.lock_remaining()
        longest_lock = max(longest_lock, remaining)
        if remaining:
            clock["now"] += remaining

    assert longest_lock == remote_auth._MAX_LOCK_SECONDS
    assert remote_auth.lock_remaining() <= remote_auth._MAX_LOCK_SECONDS


def test_issued_session_accepts_only_untampered_token():
    remote_auth.set_pin("123456")
    token, max_age = remote_auth.issue_session()
    replacement = "0" if token[-1] != "0" else "1"

    assert max_age == remote_auth.SESSION_DAYS * 24 * 3600
    assert remote_auth.session_is_valid(token) is True
    assert remote_auth.session_is_valid(token[:-1] + replacement) is False
    assert remote_auth.session_is_valid("random-token") is False


def test_session_expires_when_wall_clock_advances(monkeypatch):
    clock = {"now": 1_800_000_000.0}
    monkeypatch.setattr(remote_auth.time, "time", lambda: clock["now"])
    remote_auth.set_pin("123456")
    token, max_age = remote_auth.issue_session()

    clock["now"] += max_age + 1
    assert remote_auth.session_is_valid(token) is False


def test_changing_pin_invalidates_existing_session():
    remote_auth.set_pin("123456")
    token, _ = remote_auth.issue_session()
    remote_auth.set_pin("654321")

    assert remote_auth.session_is_valid(token) is False


def _middleware_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(remote_auth.RemoteAccessMiddleware)

    @app.get("/api/office/state")
    async def office_state(request: Request) -> dict:
        return {"ok": True, "remote": request.state.remote}

    @app.post("/api/office/state")
    async def update_office_state() -> dict:
        return {"ok": True}

    @app.get("/private")
    async def private_page() -> dict:
        return {"ok": True}

    @app.get("/m")
    async def mobile_page(request: Request) -> dict:
        return {"ok": True, "remote": request.state.remote}

    @app.get("/_next/static/chunk.js")
    async def static_asset() -> dict:
        return {"ok": True}

    return app


def test_middleware_treats_default_testclient_scope_as_remote_and_gates_it():
    remote_auth.set_pin("123456")
    token, _ = remote_auth.issue_session()

    with TestClient(_middleware_app(), follow_redirects=False) as client:
        denied = client.get("/api/office/state")
        redirected = client.get("/private")
        mobile = client.get("/m")
        static = client.get("/_next/static/chunk.js")
        allowed = client.get(
            "/api/office/state",
            headers={"cookie": f"{remote_auth.COOKIE_NAME}={token}"},
        )

    assert denied.status_code == 401
    assert denied.json() == {"success": False, "message": "Oturum gerekli.", "data": {}}
    assert redirected.status_code == 307
    assert redirected.headers["location"] == "/m/"
    assert mobile.json() == {"ok": True, "remote": True}
    assert static.status_code == 200
    assert allowed.json() == {"ok": True, "remote": True}


def test_middleware_checks_post_origin_for_a_local_scope():
    with TestClient(
        _middleware_app(),
        base_url="http://127.0.0.1:8000",
        client=("127.0.0.1", 50000),
    ) as client:
        rejected = client.post(
            "/api/office/state", headers={"origin": "https://foreign.example"}
        )
        accepted = client.post(
            "/api/office/state", headers={"origin": "http://127.0.0.1:8000"}
        )

    assert rejected.status_code == 403
    assert rejected.json()["message"] == "Kaynak reddedildi."
    assert accepted.status_code == 200
    assert accepted.json() == {"ok": True}


def _router_app() -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def mark_remote(request: Request, call_next):
        request.state.remote = request.headers.get("x-test-remote") == "1"
        return await call_next(request)

    app.include_router(remote.router)
    return app


def test_remote_session_endpoint_reports_local_and_remote_state():
    remote_auth.set_pin("123456")
    token, _ = remote_auth.issue_session()

    with TestClient(_router_app()) as client:
        local = client.get("/api/remote/session").json()["data"]
        remote_without_cookie = client.get(
            "/api/remote/session", headers={"x-test-remote": "1"}
        ).json()["data"]
        remote_with_cookie = client.get(
            "/api/remote/session",
            headers={
                "x-test-remote": "1",
                "cookie": f"{remote_auth.COOKIE_NAME}={token}",
            },
        ).json()["data"]

    assert local == {
        "authenticated": True,
        "remote": False,
        "pinSet": True,
        "lockedSeconds": 0,
    }
    assert remote_without_cookie["authenticated"] is False
    assert remote_without_cookie["remote"] is True
    assert remote_with_cookie["authenticated"] is True


def test_remote_login_rejects_wrong_pin_and_sets_secure_cookie_for_correct_pin():
    remote_auth.set_pin("123456")

    with TestClient(_router_app()) as client:
        wrong = client.post(
            "/api/remote/login", json={"pin": "000000"}, headers={"x-test-remote": "1"}
        )
        correct = client.post(
            "/api/remote/login", json={"pin": " 123456 "}, headers={"x-test-remote": "1"}
        )

    assert wrong.status_code == 401
    assert wrong.json()["success"] is False
    assert correct.status_code == 200
    assert correct.json()["success"] is True
    cookie = correct.headers["set-cookie"]
    assert cookie.startswith(f"{remote_auth.COOKIE_NAME}=v1.")
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie


def test_local_login_is_already_authorized_and_does_not_set_cookie():
    with TestClient(_router_app()) as client:
        response = client.post("/api/remote/login", json={"pin": "anything"})

    assert response.json() == {"success": True, "message": "yerel istemci", "data": {}}
    assert "set-cookie" not in response.headers


def test_logout_clears_remote_cookie():
    with TestClient(_router_app()) as client:
        response = client.post("/api/remote/logout")

    assert response.json()["success"] is True
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f'{remote_auth.COOKIE_NAME}=""')
    assert "Max-Age=0" in cookie


@pytest.mark.parametrize("pin", ["12345", "1234567890123", "12ab56"])
def test_pin_endpoint_rejects_invalid_length_or_characters(pin):
    with TestClient(_router_app()) as client:
        response = client.post("/api/remote/pin", json={"pin": pin})

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert remote_auth.pin_is_set() is False


def test_pin_endpoint_refuses_remote_change_even_with_valid_value():
    with TestClient(_router_app()) as client:
        response = client.post(
            "/api/remote/pin", json={"pin": "123456"}, headers={"x-test-remote": "1"}
        )

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert remote_auth.pin_is_set() is False


def test_pin_endpoint_updates_pin_locally(monkeypatch):
    closed = {"count": 0}

    async def close_remote() -> int:
        closed["count"] += 1
        return 0

    monkeypatch.setattr(remote.manager, "close_remote", close_remote)
    with TestClient(_router_app()) as client:
        response = client.post("/api/remote/pin", json={"pin": " 123456 "})

    assert response.json()["success"] is True
    assert remote_auth.pin_is_set() is True
    assert remote_auth.attempt_login("123456")[0] is True
    assert closed["count"] == 1
