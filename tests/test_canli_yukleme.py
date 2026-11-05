"""Canlı yükleme: çalışan modül yamalanır, durum korunur, yeni rota "/" mount'undan önce takılır."""

from __future__ import annotations

import importlib
import sys
import textwrap
import uuid
from pathlib import Path

import pytest

from backend.core.canli_yukleme import LiveReloader, Patcher, sync_routes


@pytest.fixture
def make_module(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    created: list[str] = []

    def make(source: str, package: str = ""):
        name = f"canli_mod_{uuid.uuid4().hex[:8]}"
        folder = tmp_path
        full = name
        if package:
            folder = tmp_path / package
            folder.mkdir(exist_ok=True)
            (folder / "__init__.py").touch()
            full = f"{package}.{name}"
        path = folder / f"{name}.py"
        path.write_text(textwrap.dedent(source), encoding="utf-8")
        module = importlib.import_module(full)
        created.append(full)
        patcher = Patcher()
        patcher.remember(full, path.read_text(encoding="utf-8"))

        def update(new_source: str):
            path.write_text(textwrap.dedent(new_source), encoding="utf-8")
            return patcher.patch(module, path)

        return module, update, patcher

    yield make
    for name in created:
        sys.modules.pop(name, None)


BASE = """
    import threading

    STATE = {"count": 0}
    LIMIT = 3
    NAMES = ["a"]
    _lock = threading.Lock()

    def greet(name):
        return f"merhaba {name}"

    def bump():
        STATE["count"] += 1
        return STATE["count"]

    class Base:
        def kind(self):
            return "base"

    class Counter(Base):
        def __init__(self):
            self.value = 10

        def get(self):
            return self.value

        @staticmethod
        def tag():
            return "eski"

        @property
        def double(self):
            return self.value * 2

    counter = Counter()
"""


def test_function_code_is_patched_in_place_and_state_survives(make_module):
    module, update, _ = make_module(BASE)
    greet_ref = module.greet
    lock = module._lock
    module.bump()

    result = update(BASE.replace('f"merhaba {name}"', 'f"selam {name}"').replace("+= 1", "+= 10"))

    assert result.ok and not result.restart, result
    assert greet_ref("Yunus") == "selam Yunus"  # eski referans yeni kodu çalıştırır
    assert module.bump() == 11  # sayaç sıfırlanmadı (gövde yeniden çalışmadı)
    assert module._lock is lock


def test_methods_on_existing_instance_and_new_method_with_super(make_module):
    module, update, _ = make_module(BASE)
    counter = module.counter
    counter.value = 5

    new = BASE.replace("return self.value\n", "return self.value + 100\n").replace('"eski"', '"yeni"')
    new = new.replace("return self.value * 2", "return self.value * 3")
    new = new.replace(
        "    counter = Counter()",
        "        def kind(self):\n            return 'sayac/' + super().kind()\n\n    counter = Counter()",
    )
    result = update(new)

    assert result.ok, result
    assert counter.get() == 105
    assert counter.tag() == "yeni"
    assert counter.double == 15
    assert counter.kind() == "sayac/base"  # super() eski (gerçek) sınıfa bağlı
    assert module.counter is counter


def test_new_function_constant_and_import_are_added(make_module):
    module, update, _ = make_module(BASE)
    result = update(BASE + "\n    import json\n    EXTRA = 7\n\n    def added():\n        return json.dumps(EXTRA)\n")
    assert result.ok, result
    assert module.added() == "7"


def test_changed_constants_update_and_lists_mutate_in_place(make_module):
    module, update, _ = make_module(BASE)
    names_ref = module.NAMES
    result = update(BASE.replace("LIMIT = 3", "LIMIT = 5").replace('NAMES = ["a"]', 'NAMES = ["a", "b"]'))
    assert module.LIMIT == 5
    assert names_ref == ["a", "b"] and module.NAMES is names_ref
    assert {"LIMIT", "NAMES"} <= set(result.applied)


def test_state_object_and_module_body_change_ask_for_restart(make_module):
    module, update, _ = make_module(BASE)
    counter = module.counter
    result = update(BASE.replace("counter = Counter()", "counter = Base()") + "\n    print('yan etki')\n")
    assert module.counter is counter
    assert any("counter" in r for r in result.restart)
    assert any("modül gövdesi" in r for r in result.restart)


def test_syntax_error_changes_nothing(make_module):
    module, update, _ = make_module(BASE)
    result = update(BASE.replace("def greet(name):", "def greet(name)"))
    assert not result.ok and "SyntaxError" in result.error
    assert module.greet("a") == "merhaba a"


def test_decorated_registered_function_keeps_registry_entry(make_module):
    registry_src = """
        REG = {}

        def register(name):
            def deco(fn):
                REG[name] = fn
                return fn
            return deco
    """
    reg_module, _, _ = make_module(registry_src)
    src = f"""
        from {reg_module.__name__} import register

        @register("arac")
        def tool():
            return 1
    """
    module, update, _ = make_module(src)
    result = update(src.replace("return 1", "return 2"))
    assert result.ok, result
    assert len(reg_module.REG) == 1
    assert reg_module.REG["arac"]() == 2


def test_new_api_route_is_inserted_before_ui_mount(make_module, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from starlette.staticfiles import StaticFiles

    src = """
        from fastapi import APIRouter

        router = APIRouter(prefix="/api/deneme")

        @router.get("")
        async def first() -> dict:
            return {"v": 1}
    """
    module, update, patcher = make_module(src, package="canli_api_pkg")
    # Yalnız backend.api.* modülleri rota eşitler — test modülünü öyle göster.
    module.__name__ = "backend.api." + module.__name__.split(".")[-1]
    patcher.remember(module.__name__, Path(module.__file__).read_text(encoding="utf-8"))

    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "index.html").write_text("ui", encoding="utf-8")
    app = FastAPI()
    app.include_router(module.router)
    app.mount("/", StaticFiles(directory=ui, html=True), name="ui")
    patcher.on_api_change = lambda m: sync_routes(app, m)
    client = TestClient(app)
    assert client.get("/api/deneme/yeni").status_code == 404

    result = update(src.replace('return {"v": 1}', 'return {"v": 2}') + """
        @router.get("/yeni")
        async def second() -> dict:
            return {"yeni": True}
    """)

    assert result.ok, result
    assert client.get("/api/deneme").json() == {"v": 2}
    assert client.get("/api/deneme/yeni").json() == {"yeni": True}
    assert any("rota" in a for a in result.applied), result.applied
    assert client.get("/").text == "ui"


def test_endpoint_signature_change_asks_for_restart(make_module):
    src = """
        from fastapi import APIRouter

        router = APIRouter()

        @router.get("/x")
        async def x() -> dict:
            return {}
    """
    module, update, patcher = make_module(src, package="canli_api_pkg2")
    module.__name__ = "backend.api." + module.__name__.split(".")[-1]
    patcher.remember(module.__name__, Path(module.__file__).read_text(encoding="utf-8"))
    result = update(src.replace("async def x()", "async def x(q: int = 0)"))
    assert any("imzası" in r for r in result.restart)


def test_reloader_applies_changed_file_and_reports_ui_build(make_module, tmp_path, monkeypatch):
    import backend.core.canli_yukleme as canli

    module, _, _ = make_module(BASE, package="izlenen")
    ui = tmp_path / "out"
    ui.mkdir()
    marker = ui / "index.html"
    marker.write_text("1", encoding="utf-8")
    monkeypatch.setattr(canli, "WATCH_DIRS", ("izlenen",))
    monkeypatch.setattr(canli, "WATCH_FILES", ())
    monkeypatch.setattr(canli, "UI_MARKER", marker)
    monkeypatch.setattr(canli, "SETTLE_SECONDS", 0)
    monkeypatch.setattr(canli, "UI_SETTLE_SECONDS", 0)
    monkeypatch.setattr(canli, "SKIP_PARTS", {"__pycache__"})

    events: list[tuple[str, dict]] = []
    reloader = LiveReloader(base_dir=tmp_path)
    reloader.on_event = lambda e, d: events.append((e, d))
    reloader._scan(initial=True)

    path = Path(module.__file__)
    path.write_text(textwrap.dedent(BASE).replace("merhaba", "hey"), encoding="utf-8")
    reloader._mtimes[path] -= 5  # aynı saniyede yazılan dosyanın mtime'ı değişmemiş görünmesin
    marker.write_text("2", encoding="utf-8")
    reloader._ui_mtime = (reloader._ui_mtime or 0) - 5
    reloader._scan()
    reloader._flush()

    assert module.greet("a") == "hey a"
    kinds = [e for e, _ in events]
    assert "code_reload" in kinds and "ui_updated" in kinds
    assert reloader.status()["history"][0]["module"] == module.__name__


# ── İnceleme bulguları (2026-11-04) ─────────────────────────────────────


def test_runtime_filled_registry_is_not_wiped_by_literal_change(make_module):
    src = """
        REG: dict = {}

        def register(name, fn):
            REG[name] = fn
    """
    module, update, _ = make_module(src)
    module.register("arac", print)
    result = update(src.replace("REG: dict = {}", "REG: dict[str, object] = {}"))
    assert module.REG == {"arac": print}
    assert any("REG" in r for r in result.restart)


def test_changed_state_constructor_is_not_executed(make_module):
    src = """
        CREATED = []

        class Client:
            def __init__(self, timeout):
                CREATED.append(timeout)

        client = Client(5)
    """
    module, update, _ = make_module(src)
    client = module.client
    result = update(src.replace("Client(5)", "Client(10)"))
    assert module.CREATED == [5]  # ikinci istemci kurulmadı
    assert module.client is client
    assert any("client" in r for r in result.restart)


def test_failed_definition_is_retried_on_next_save(make_module):
    module, update, _ = make_module(BASE)
    broken = BASE.replace("def greet(name):", "def greet(name, sep=TANIMSIZ):")
    first = update(broken)
    assert not first.ok
    assert module.greet("a") == "merhaba a"
    # Aynı tanım bu kez düzgün: taban eski kaldığı için yeniden denenir.
    second = update(BASE.replace('f"merhaba {name}"', 'f"tekrar {name}"'))
    assert second.ok, second
    assert module.greet("a") == "tekrar a"


def test_decorator_change_asks_for_restart(make_module):
    registry_src = """
        REG = {}

        def register(name):
            def deco(fn):
                REG[name] = fn
                return fn
            return deco
    """
    reg_module, _, _ = make_module(registry_src)
    src = f"""
        from {reg_module.__name__} import register

        @register("eski")
        def tool():
            return 1
    """
    _, update, _ = make_module(src)
    result = update(src.replace('"eski"', '"yeni"'))
    assert any("dekoratör" in r for r in result.restart)
    assert list(reg_module.REG) == ["eski"]


def test_endpoint_sync_to_async_asks_for_restart(make_module):
    src = """
        from fastapi import APIRouter

        router = APIRouter()

        @router.get("/x")
        def x() -> dict:
            return {}
    """
    module, update, patcher = make_module(src, package="canli_api_pkg3")
    module.__name__ = "backend.api." + module.__name__.split(".")[-1]
    patcher.remember(module.__name__, Path(module.__file__).read_text(encoding="utf-8"))
    result = update(src.replace("def x()", "async def x()"))
    assert any("imzası" in r for r in result.restart)


def test_method_to_staticmethod_swaps_descriptor(make_module):
    src = """
        class Tool:
            def helper(self, x):
                return x
    """
    module, update, _ = make_module(src)
    tool = module.Tool()
    result = update(src.replace("    def helper(self, x):", "    @staticmethod\n            def helper(x):").replace("return x", "return x * 2"))
    assert result.ok, result
    assert tool.helper(3) == 6
    assert module.Tool.helper(4) == 8


def test_unwrapped_decorator_is_not_dropped(make_module):
    src = """
        CALLS = []

        def logged(fn):
            def inner(*a):
                CALLS.append(fn.__name__)
                return fn(*a)
            return inner

        @logged
        def work():
            return 1
    """
    module, update, _ = make_module(src)
    result = update(src.replace("return 1", "return 2"))
    module.work()
    assert module.CALLS == ["work"]  # sarmalayıcı yerinde
    assert any("sarmalanmış" in r for r in result.restart)


def test_unknown_module_is_only_recorded(make_module, tmp_path):
    module, _, _ = make_module(BASE)
    fresh = Patcher()  # bu modülün tabanı yok
    path = Path(module.__file__)
    path.write_text(textwrap.dedent(BASE).replace("merhaba", "hey"), encoding="utf-8")
    first = fresh.patch(module, path)
    assert module.greet("a") == "merhaba a"
    assert any("ilk kez" in r for r in first.restart)
    path.write_text(textwrap.dedent(BASE).replace("merhaba", "yo"), encoding="utf-8")
    second = fresh.patch(module, path)
    assert second.ok and module.greet("a") == "yo a"


def test_removed_function_is_reported(make_module):
    module, update, _ = make_module(BASE)
    result = update(BASE.replace("def bump():", "def bump_renamed():"))
    assert any("bump: dosyadan kalktı" in r for r in result.restart)
    assert module.bump_renamed() == 1
