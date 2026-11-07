from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from actions import ekran_gosterge as eg
from actions.ekran_gosterge import Element, best_match, explain_rect, normalize, parse_box, parse_elements
from core.ekran_rehberi import (
    BubbleMotion,
    Mark,
    WindowWatch,
    clicked_target,
    clean_rect,
    compose,
    orb_position,
    perimeter_points,
    place_balloon,
    render_balloon,
    wrap_text,
)

SCREEN = (0, 0, 1920, 1040)
HOME = (1800.0, 110.0)
TARGET = (400, 300, 120, 40)


def run(motion: BubbleMotion, seconds: float, dt: float = 1 / 40) -> None:
    for _ in range(int(seconds / dt)):
        motion.tick(dt)


def fresh(**kw) -> BubbleMotion:
    return BubbleMotion(HOME, SCREEN, kw.get("scale", 1.0))


# ── hareket ─────────────────────────────────────────────────────────────────
def test_flies_to_target_and_becomes_ring():
    m = fresh()
    m.show(Mark(TARGET, "x"))
    run(m, 0.2)
    assert m.mix == 0  # uçarken halka olmaz
    run(m, 2.5)
    assert m.settled and m.mix == 1
    gx, gy = orb_position(TARGET, SCREEN, 1.0)
    assert abs(m.x - gx) < 2 and abs(m.y - gy) < 2


def test_particles_sit_on_ring_when_settled():
    m = fresh()
    m.show(Mark(TARGET))
    run(m, 3)
    x, y, each = m.particles(0.0)
    assert each.min() > 0.99
    tx, ty, tw, th = TARGET
    # Her parçacık hedefin çevresinde, içinde değil: yazı okunabilir kalsın.
    assert np.all((x < tx) | (x > tx + tw) | (y < ty) | (y > ty + th))
    assert x.min() > tx - 20 and x.max() < tx + tw + 20 and y.min() > ty - 20 and y.max() < ty + th + 20


def test_new_target_gathers_before_moving():
    m = fresh()
    m.show(Mark(TARGET))
    run(m, 3)
    second = (900, 600, 80, 80)
    m.show(Mark(second))
    m.tick(1 / 40)
    assert m.mark.rect == TARGET  # halka eski yerinde çözülür, ışınlanmaz
    run(m, 3.5)
    assert m.mark.rect == second and m.settled


def test_clear_returns_home_and_finishes():
    m = fresh()
    m.show(Mark(TARGET))
    run(m, 3)
    m.clear()
    assert not m.active
    run(m, 4)
    assert m.finished and abs(m.x - HOME[0]) < 2


def test_hold_expires_on_its_own():
    m = fresh()
    m.show(Mark(TARGET, hold=2.0))
    run(m, 1.9)
    assert m.active
    run(m, 0.3)
    assert not m.active


def test_new_show_during_clear_wins():
    m = fresh()
    m.show(Mark(TARGET))
    run(m, 3)
    m.clear()
    m.tick(1 / 40)
    m.show(Mark((900, 600, 80, 80)))
    assert m.active
    run(m, 4)
    assert m.mark.rect == (900, 600, 80, 80) and m.settled


def test_color_goes_teal_when_active_and_back():
    m = fresh()
    start = m.colors()[0].copy()
    m.show(Mark(TARGET))
    run(m, 3)
    assert not np.allclose(m.colors()[0], start)
    m.clear()
    run(m, 4)
    assert np.allclose(m.colors()[0], start, atol=0.02)


# ── takılı kalmasın ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("circle_hold", [15.0, 60.0])
def test_click_inside_counts_in_every_mode(circle_hold):
    mark = Mark(TARGET, hold=circle_hold)
    assert clicked_target(mark, True, True, False, (410, 310), 6)


def test_click_outside_or_held_or_unsettled_does_not_count():
    mark = Mark(TARGET)
    assert not clicked_target(mark, True, True, False, (5, 5), 6)      # dışarı
    assert not clicked_target(mark, True, True, True, (410, 310), 6)   # fare zaten basılıydı
    assert not clicked_target(mark, False, True, False, (410, 310), 6)  # halka henüz oturmadı
    assert not clicked_target(None, True, True, False, (410, 310), 6)


def test_window_watch_notices_change_and_ignores_transition():
    w = WindowWatch()
    rect = (0, 0, 800, 600)
    assert not w.changed(10, rect)  # ilk bakış taban
    assert not w.changed(10, rect)
    assert not w.changed(0, rect)   # geçiş anı
    assert w.changed(11, rect)      # başka pencere öne geldi
    assert w.changed(10, (5, 0, 800, 600))  # pencere oynadı
    w.reset()
    assert not w.changed(11, rect)


def test_circle_does_not_stay_for_minutes():
    from core.ekran_rehberi import HOLD_CIRCLE

    assert HOLD_CIRCLE <= 60


# ── geometri ────────────────────────────────────────────────────────────────
def test_perimeter_stays_on_rectangle():
    x, y = perimeter_points((10, 20, 100, 50), np.linspace(0, 0.999, 400, dtype=np.float32), 5.0)
    on_h = np.isclose(y, 15) | np.isclose(y, 75)
    on_v = np.isclose(x, 5) | np.isclose(x, 115)
    assert np.all(on_h | on_v)
    assert x.min() == pytest.approx(5, abs=0.5) and x.max() == pytest.approx(115, abs=0.5)


@pytest.mark.parametrize("rect", [(400, 300, 120, 40), (1800, 40, 100, 40), (5, 5, 60, 60), (1700, 980, 200, 50), (0, 0, 1900, 900)])
def test_balloon_stays_on_screen(rect):
    bx, by = place_balloon(rect, (300, 90), SCREEN, 1.0)
    assert bx >= 0 and by >= 0 and bx + 300 <= 1920 and by + 90 <= 1040


@pytest.mark.parametrize("rect", [(400, 300, 120, 40), (1800, 40, 100, 40), (5, 5, 60, 60), (1700, 980, 200, 50)])
def test_balloon_does_not_cover_target(rect):
    bx, by = place_balloon(rect, (300, 90), SCREEN, 1.0)
    x, y, w, h = rect
    assert bx >= x + w or bx + 300 <= x or by >= y + h or by + 90 <= y


def test_clean_rect_clips_and_rejects():
    assert clean_rect((-10, -10, 50, 50), SCREEN) == (0, 0, 40, 40)
    assert clean_rect((3000, 10, 50, 50), SCREEN) is None
    assert clean_rect((10, 10, 0, 50), SCREEN) is None


def test_wrap_limits_lines():
    lines = wrap_text("bir iki üç dört beş altı yedi", len, 3, max_lines=3)
    assert len(lines) == 3 and lines[-1].endswith("…")


# ── çizim ───────────────────────────────────────────────────────────────────
def test_compose_returns_small_region_not_whole_screen():
    m = fresh()
    m.show(Mark(TARGET, "x"))
    run(m, 3)
    frame, left, top = compose(m, 0.1, render_balloon("BURADA", "Karanlık mod burada.", (138, 232, 200), 1.0))
    h, w = frame.shape[:2]
    assert w * h < 0.3 * 1920 * 1040
    assert frame.dtype == np.uint8 and frame[..., 3].max() > 200
    # Önceden çarpılmış: renk alfayı geçemez, yoksa Windows taşan renk gösterir.
    assert int(frame[..., :3].max()) <= 255 and np.all(frame[..., :3].max(axis=2).astype(int) <= frame[..., 3].astype(int) + 1)
    assert left % 16 == 0 and top % 16 == 0 and w % 16 == 0 and h % 16 == 0


def test_compose_none_when_invisible():
    assert compose(fresh(), 0.0, None) is None


# ── eşleşme ─────────────────────────────────────────────────────────────────
def E(name, kind="Button", rect=(0, 0, 50, 20)):
    return Element(name, kind, rect)


def test_normalize_turkish():
    assert normalize("KAPAT Düğmesİ") == normalize("kapat düğmesi") == "kapat dugmesi"


def test_exact_name_wins():
    assert best_match("Ekle", [E("Ekleme modu"), E("Ekle")]).name == "Ekle"


def test_description_words_are_ignored():
    assert best_match("ekle sekmesi", [E("Giriş", "TabItem"), E("Ekle", "TabItem")]).name == "Ekle"


def test_button_preferred_over_same_text_label():
    assert best_match("Kaydet", [E("Kaydet", "Text"), E("Kaydet", "Button")]).kind == "Button"


def test_innermost_preferred_on_tie():
    big, small = E("Kaydet", rect=(0, 0, 500, 500)), E("Kaydet", rect=(0, 0, 50, 20))
    assert best_match("Kaydet", [big, small]) is small


def test_longer_query_does_not_grab_partial_name():
    # "Dosya" menüsü "dosya kaydet" isteği için doğru hedef değil: görüntüden bulmaya düşmeli.
    assert best_match("dosya kaydet", [E("Dosya", "MenuItem")]) is None


def test_no_match_returns_none():
    assert best_match("karanlık mod", [E("Dark"), E("Light")]) is None


def test_parse_elements_skips_bad_lines():
    raw = "Ekle\tControlType.TabItem\t10\t20\t30\t40\nbozuk satır\nX\tControlType.Button\ta\t1\t1\t1\n"
    assert parse_elements(raw) == [Element("Ekle", "TabItem", (10, 20, 30, 40))]


# ── görüntü kutusu ──────────────────────────────────────────────────────────
def test_parse_box_scales_to_capture():
    assert parse_box({"found": True, "box": [100, 200, 200, 400]}, (0, 0, 1000, 500)) == (200, 50, 200, 50)


def test_parse_box_uses_monitor_offset():
    assert parse_box({"found": True, "box": [0, 0, 100, 100]}, (-1920, 100, 1000, 1000))[:2] == (-1920, 100)


@pytest.mark.parametrize("data", [None, {"found": False}, {"found": True}, {"found": True, "box": [1, 2, 3]},
                                  {"found": True, "box": [500, 500, 100, 100]}, {"found": True, "box": ["a", 0, 1, 1]},
                                  {"found": True, "box": [0, 0, 1000, 1000]}])
def test_parse_box_rejects_nonsense(data):
    assert parse_box(data, (0, 0, 1000, 1000)) is None


def test_explain_rect_shrinks_whole_window():
    window = Element("Pencere", "Window", (0, 0, 1900, 1000))
    x, y, w, h = explain_rect(window, 500, 400, 1.0, SCREEN)
    assert w == h == 90 and x <= 500 <= x + w and y <= 400 <= y + h


def test_explain_rect_keeps_small_element():
    assert explain_rect(Element("Düğme", "Button", (10, 10, 60, 24)), 20, 20, 1.0, SCREEN) == (10, 10, 60, 24)


# ── araçlar ─────────────────────────────────────────────────────────────────
class FakeRehber:
    def __init__(self):
        self.calls = []
        self.cleared = False

    def show(self, rect, label="", kicker="", circle=False, hold=None, on_click=None):
        self.calls.append((rect, label, kicker, circle))
        self.on_click = on_click

    def clear(self):
        self.cleared = True
        return True


@pytest.fixture()
def tool_env(monkeypatch):
    fake = FakeRehber()
    monkeypatch.setattr(eg, "rehber", fake)
    monkeypatch.setattr(eg, "_target_hwnd", lambda: 123)
    monkeypatch.setattr(eg, "monitor_bounds", lambda rect: SCREEN)
    monkeypatch.setattr(eg, "game_in_front", lambda: False)
    monkeypatch.setattr(eg.otomatik_tepsi, "before_showing", lambda *a, **k: None)
    monkeypatch.setattr(eg, "_windows_behind", lambda hwnd, limit=3: [])
    return fake


def test_target_in_window_behind_is_found_and_raised(tool_env, monkeypatch):
    raised = []
    monkeypatch.setattr(eg, "_windows_behind", lambda hwnd, limit=3: [55, 66])
    monkeypatch.setattr(eg, "_bring_forward", raised.append)
    monkeypatch.setattr(eg, "find_with_uia", lambda q, h: E("Ekle", "TabItem", (10, 10, 60, 24)) if h == 66 else None)
    monkeypatch.setattr(eg, "find_with_vision", lambda q, h: pytest.fail("arkada bulunduysa görüntü gönderilmemeli"))
    assert eg.show_on_screen("Ekle")["success"]
    assert raised == [66] and tool_env.calls[0][0] == (10, 10, 60, 24)


def test_front_window_found_raises_nothing(tool_env, monkeypatch):
    monkeypatch.setattr(eg, "_bring_forward", lambda h: pytest.fail("öndeki pencere için gerekmez"))
    monkeypatch.setattr(eg, "find_with_uia", lambda q, h: E("Ekle"))
    assert eg.show_on_screen("Ekle")["success"]


def test_click_tells_model_to_continue(tool_env, monkeypatch):
    from actions import arastirma_panosu as motor

    monkeypatch.setattr(motor, "_announcements", [])
    monkeypatch.setattr(eg, "find_with_uia", lambda q, h: E("Ekle"))
    eg.show_on_screen("Ekle")
    tool_env.on_click()
    said = motor._announcements[-1]
    assert said.startswith("[SİSTEM]") and "Ekle" in said and "sıradaki adım" in said and "kullanıcının sözü değil" in said


def test_goes_to_tray_before_reading_screen(tool_env, monkeypatch):
    order = []
    monkeypatch.setattr(eg.otomatik_tepsi, "before_showing", lambda *a, **k: order.append("tepsi"))
    monkeypatch.setattr(eg, "find_with_uia", lambda q, h: order.append("ara") or E("Ekle"))
    eg.show_on_screen("Ekle")
    assert order == ["tepsi", "ara"]


def test_no_tray_when_game_refused(tool_env, monkeypatch):
    monkeypatch.setattr(eg, "game_in_front", lambda: True)
    monkeypatch.setattr(eg.otomatik_tepsi, "before_showing", lambda *a, **k: pytest.fail("reddederken pencereye dokunma"))
    assert not eg.show_on_screen("Ekle")["success"]


def test_refuses_over_game_without_reading_screen(tool_env, monkeypatch):
    monkeypatch.setattr(eg, "game_in_front", lambda: True)
    monkeypatch.setattr(eg, "_locate", lambda *a: pytest.fail("oyun öndeyken ekran okunmamalı"))
    monkeypatch.setattr(eg, "_gather_under_cursor", lambda *a: pytest.fail("oyun öndeyken ekran okunmamalı"))
    for result in (eg.show_on_screen("Ekle"), eg.explain_on_screen()):
        assert not result["success"] and "Oyun" in result["message"]
    assert not tool_env.calls


def test_game_detection_uses_window_behind_chiron(monkeypatch):
    import actions.ekran_icerigi as ei

    monkeypatch.setattr(eg, "_fullscreen_d3d", lambda: False)
    monkeypatch.setattr(ei, "_target_window", lambda: (1, "VALORANT", "valorant-win64-shipping.exe", True))
    assert eg.game_in_front()
    monkeypatch.setattr(ei, "_target_window", lambda: (1, "Belge", "winword.exe", False))
    assert not eg.game_in_front()


def test_show_prefers_uia_and_skips_vision(tool_env, monkeypatch):
    monkeypatch.setattr(eg, "find_with_uia", lambda q, h: E("Ekle", "TabItem", (10, 10, 60, 24)))
    monkeypatch.setattr(eg, "find_with_vision", lambda q, h: pytest.fail("UIA bulduysa görüntü gönderilmemeli"))
    result = eg.show_on_screen("Ekle", label="Burada")
    assert result["success"] and tool_env.calls == [((10, 10, 60, 24), "Burada", "BURADA", False)]
    assert result["data"]["method"] == "uia"


def test_show_falls_back_to_vision(tool_env, monkeypatch):
    monkeypatch.setattr(eg, "find_with_uia", lambda q, h: None)
    monkeypatch.setattr(eg, "find_with_vision", lambda q, h: ((100, 100, 40, 40), "Dark"))
    assert eg.show_on_screen("karanlık mod", circle=True)["success"]
    assert tool_env.calls[0][0] == (100, 100, 40, 40) and tool_env.calls[0][3] is True


def test_show_fails_honestly_when_not_found(tool_env, monkeypatch):
    monkeypatch.setattr(eg, "find_with_uia", lambda q, h: None)
    monkeypatch.setattr(eg, "find_with_vision", lambda q, h: None)
    result = eg.show_on_screen("olmayan şey")
    assert not result["success"] and not tool_env.calls


def test_show_rejects_empty_target(tool_env):
    assert not eg.show_on_screen("   ")["success"]


def test_explain_never_sends_password_field_image(tool_env, monkeypatch):
    monkeypatch.setattr(eg, "_gather_under_cursor", lambda x, y: (E("Şifre", "Edit"), "", True))
    monkeypatch.setattr(eg, "_explain_with_vision", lambda *a: pytest.fail("şifre alanının görüntüsü gönderilmemeli"))
    result = eg.explain_on_screen()
    assert result["success"] and "şifre" in result["message"].lower()


def test_explain_survives_vision_error_with_uia_name(tool_env, monkeypatch):
    monkeypatch.setattr(eg, "_gather_under_cursor", lambda x, y: (E("Resim", "Button"), "Resim ekler", False))

    def boom(*a):
        raise RuntimeError("ağ yok")

    monkeypatch.setattr(eg, "_explain_with_vision", boom)
    result = eg.explain_on_screen()
    assert result["success"] and "Resim ekler" in result["message"]


def test_clear_tool(tool_env):
    assert eg.clear_screen_marks()["success"] and tool_env.cleared


# ── kablolama ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("name", ["show_on_screen", "explain_on_screen", "clear_screen_marks"])
def test_tool_is_wired_everywhere(name):
    from core.tool_registry import get_tool
    from tool_defs import TOOL_DECLARATIONS

    assert next(d for d in TOOL_DECLARATIONS if d["name"] == name)
    assert name in (PROJECT_ROOT / "core" / "prompt.txt").read_text(encoding="utf-8")
    assert name in (PROJECT_ROOT / "Notes" / "Araclar" / "Ekran-Rehberi.md").read_text(encoding="utf-8")
    assert f"from actions.ekran_gosterge import" in (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
    assert get_tool(name) is not None


def test_indicator_hides_while_suppressed():
    from core.speaking_overlay import SpeakingOverlay

    o = SpeakingOverlay()
    o.set_suppressed(True)
    assert o._suppressed
    o.set_suppressed(False)
    assert not o._suppressed
    assert o.activity() == ("", 0.0)
