from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.idle_model import IdleModel


def _counting_loader():
    calls = {"n": 0}

    def load():
        calls["n"] += 1
        return object()

    return calls, load


def _wait_until(predicate, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_loads_once_and_reuses_while_warm():
    calls, load = _counting_loader()
    m = IdleModel("t", load, idle_seconds=5)
    with m.use() as a:
        pass
    with m.use() as b:
        pass
    assert a is b and calls["n"] == 1
    m.release()


def test_released_after_idle_and_reloaded_on_next_use():
    calls, load = _counting_loader()
    m = IdleModel("t", load, idle_seconds=0.15)
    with m.use():
        pass
    assert m.loaded
    assert _wait_until(lambda: not m.loaded)
    with m.use():
        pass
    assert calls["n"] == 2
    m.release()


def test_never_released_while_in_use():
    _, load = _counting_loader()
    m = IdleModel("t", load, idle_seconds=0.05)
    gate = threading.Event()
    inside = threading.Event()

    def long_user():
        with m.use():
            inside.set()
            gate.wait(2)

    # Önce kısa bir kullanım zamanlayıcı kursun, sonra uzun kullanım başlasın.
    with m.use():
        pass
    t = threading.Thread(target=long_user)
    t.start()
    inside.wait(1)
    time.sleep(0.2)  # boşta süresinin 4 katı
    assert m.loaded
    gate.set()
    t.join()
    assert _wait_until(lambda: not m.loaded)


def test_ensure_uses_given_loader_and_counts_as_use():
    calls, default = _counting_loader()
    m = IdleModel("t", default, idle_seconds=0.3)
    special = object()
    m.ensure(lambda: special)
    with m.use() as got:
        assert got is special
    assert calls["n"] == 0  # varsayılan (ör. indirmeli) yükleyici hiç çağrılmadı
    m.ensure(lambda: object())  # dolu: dokunmaz
    with m.use() as again:
        assert again is special
    m.release()


def test_loader_error_propagates_and_leaves_model_empty():
    def broken():
        raise FileNotFoundError("ağırlık yok")

    m = IdleModel("t", broken, idle_seconds=1)
    try:
        with m.use():
            raise AssertionError("buraya gelmemeli")
    except FileNotFoundError:
        pass
    assert not m.loaded
