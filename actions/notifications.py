"""
Windows bildirim (toast) okuma (YAPILACAKLAR.md #8).

`UserNotificationListener` (WinRT) ile sistemde o an aktif olan (Bildirim
Merkezi'nde duran) toast bildirimlerini okur — `winsdk` paketi gerekiyor
(Microsoft'un resmi WinRT Python projeksiyonu). İlk kullanımda Windows bir izin
kontrolü yapar (Ayarlar > Gizlilik ve güvenlik > Bildirimler ile eşdeğer);
kullanıcı reddederse veya izin yoksa bu araç sessizce "izin verilmedi" döner,
Chiron çökmez.

Bu, main.py'deki diğer proaktif bekçilerin (ekran/sistem sağlığı/genel izleme)
aksine kendiliğinden konuşmaz — kullanıcı "bildirimlerim var mı" gibi bir şey
sorduğunda çağrılan, isteğe bağlı (on-demand) bir araç. Kendiliğinden bildirim
anonsu istenirse (yeni bildirim gelince otomatik haber verme) bu fonksiyon
kolayca bir arka plan bekçisine bağlanabilir.
"""

from __future__ import annotations

from actions.tool_result import fail, ok
from core.tool_registry import register_tool

try:
    from winsdk.windows.ui.notifications.management import (
        UserNotificationListener,
        UserNotificationListenerAccessStatus,
    )
    from winsdk.windows.ui.notifications import NotificationKinds
    HAS_WINSDK = True
except ImportError:
    HAS_WINSDK = False


def _extract_texts(notification) -> list[str]:
    texts: list[str] = []
    try:
        for binding in notification.notification.visual.bindings:
            for el in binding.get_text_elements():
                if el.text:
                    texts.append(el.text)
    except Exception:
        pass
    return texts


def _app_name(notification) -> str:
    try:
        return str(notification.app_info.display_info.display_name or "").strip()
    except Exception:
        return ""


@register_tool("get_notifications")
async def get_recent_notifications(limit: int = 10) -> dict:
    """Şu an sistemde aktif (Bildirim Merkezi'nde duran) toast bildirimlerini okur."""
    if not HAS_WINSDK:
        return fail("Bildirim okuma için 'winsdk' kurulu değil. 'pip install winsdk' ile kur.")

    try:
        listener = UserNotificationListener.current
        status = await listener.request_access_async()
        if status != UserNotificationListenerAccessStatus.ALLOWED:
            return fail(
                "Bildirimlere erişim izni verilmedi. Windows Ayarlar > Gizlilik ve güvenlik > "
                "Bildirimler bölümünden Chiron'a izin vermen gerekebilir."
            )

        notifications = await listener.get_notifications_async(NotificationKinds.TOAST)

        items = []
        for n in notifications:
            texts = _extract_texts(n)
            items.append({
                "id": n.id,
                "app": _app_name(n) or "Bilinmeyen uygulama",
                "title": texts[0] if texts else "",
                "message": " — ".join(texts[1:]) if len(texts) > 1 else "",
            })

        limit = max(1, min(50, int(limit or 10)))
        items = items[:limit]

        if not items:
            return ok("Şu an bekleyen bir bildirim yok.", notifications=[])

        lines = [
            f"{it['app']}: {it['title']}" + (f" — {it['message']}" if it["message"] else "")
            for it in items
        ]
        return ok(f"{len(items)} bildirim var. " + " | ".join(lines), notifications=items)
    except Exception as exc:
        return fail(f"Bildirimler okunamadı: {exc}")
