"""Sesle onay — Claude Code'un izin sorusuna sesli cevap (2026-11-04).

Yunus: "onay bekleyen oturuma ... sesli komutla söyleyeyim." Bekleyen istekler backend/core/onay.py'de
(hook `~/.claude/hooks/chiron-onay.py` bırakıyor). Bu araç onları okur ve karar verir.

Güvenlik — shell_run ile aynı iki adım: İZİN vermek kod/komut çalıştırır, bu yüzden `confirm=false` önce isteği
geri okutur; kullanıcı açıkça "evet" derse aynı istek `confirm=true` ile tekrar çağrılır. Ekrandan/bildirimden
gelen bir metin Gemini'yi kandırsa bile tek çağrıda izin çıkmaz. REDDETMEK zararsız: tek adımda.

Backend'e HTTP ile gider (pc_isi.py ile aynı gerekçe: ses döngüsü backend modülünü import etmesin).
"""

from __future__ import annotations

import requests

from actions.tool_result import fail, ok
from backend.core.config import PORT
from core.tool_registry import register_tool

BASE = f"http://127.0.0.1:{PORT}/api/onay"
NEWS_URL = f"{BASE}"


def _pending() -> list[dict]:
    data = requests.get(BASE, timeout=5).json() or {}
    return ((data.get("data") or {}).get("items")) or []


def _pick(items: list[dict], session: str) -> tuple[dict | None, str]:
    if not items:
        return None, "Bekleyen onay yok."
    s = (session or "").strip().lower()
    if s:
        hits = [i for i in items if s in (i.get("project") or "").lower() or s in (i.get("summary") or "").lower()]
        if len(hits) == 1:
            return hits[0], ""
        if not hits:
            names = ", ".join(sorted({i.get("project") or "?" for i in items}))
            return None, f"'{session}' adında bekleyen onay yok. Bekleyenler: {names}."
        items = hits
    if len(items) == 1:
        return items[0], ""
    names = ", ".join(f"{i.get('project')}: {i.get('summary')}" for i in items[:4])
    return None, f"Birden çok bekleyen onay var, hangisi? {names}"


@register_tool("answer_approval")
def answer_approval(decision: str = "", session: str = "", message: str = "", always: bool = False,
                    confirm: bool = False) -> dict:
    decision = (decision or "").strip().lower()
    if decision not in ("izin", "red", "liste"):
        return fail("decision 'izin', 'red' ya da 'liste' olmalı.")
    try:
        items = _pending()
    except Exception as error:
        return fail(f"Onaylara ulaşılamadı ({error.__class__.__name__}).")
    if decision == "liste":
        if not items:
            return ok("Bekleyen onay yok.")
        return ok("Bekleyen onaylar.", items=[{"oturum": i.get("project"), "istek": i.get("summary")} for i in items])
    item, why = _pick(items, session)
    if item is None:
        return fail(why)
    if decision == "izin" and not confirm:
        return ok(
            f"{item.get('project')} şunu istiyor: {item.get('summary')}. Kullanıcıya bunu oku ve onaylıyor musun diye sor; "
            "açıkça evet derse aynı oturumla confirm=true ile tekrar çağır. Onaylamadan izin verme.",
            oturum=item.get("project"),
            istek=item.get("summary"),
            onay_bekliyor=True,
        )
    body = {"behavior": decision, "message": message or "", "always": bool(always), "by": "ses"}
    try:
        r = requests.post(f"{BASE}/{item['id']}/karar", json=body, timeout=5).json() or {}
    except Exception as error:
        return fail(f"Karar iletilemedi ({error.__class__.__name__}).")
    if not r.get("success"):
        return fail(r.get("message") or "Karar iletilemedi.")
    verb = "izin verildi" if decision == "izin" else "reddedildi"
    return ok(f"{item.get('project')}: {item.get('summary')} — {verb}.", oturum=item.get("project"))
