"""Otomasyon — aktif izlemeler ve zamanlanmış görevler.

Kullanıcı isteğiyle (2026-07-30) eklendi. Hafızanın aksine bu verinin dosyada
karşılığı YOK: aktif izlemeler (`start_watch` ile kurulanlar) ses döngüsünün
belleğinde, `ChironLive._active_watches` içinde yaşıyor. Bu yüzden okuma
`backend/core/commands.read_provider` üzerinden yapılıyor — ses döngüsü kendi
durumunu okuyan bir fonksiyon bırakıyor, burası onu çağırıyor.

Ses döngüsü çalışmıyorsa (arayüz tek başına açıldıysa) `available: False` döner
ve panel bunu dürüstçe söyler — boş bir liste göstermek "hiç izleme yok"
demekle karışırdı, oysa gerçek şu: bakacak bir yer yok.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.core import commands

router = APIRouter(prefix="/api/automation", tags=["automation"])

PROVIDER = "automation"


@router.get("")
@router.get("/")
async def read_automation() -> dict:
    snapshot = commands.read_provider(PROVIDER)
    if snapshot is None:
        return {
            "success": True,
            "message": "sesli asistan çalışmıyor",
            "data": {"available": False, "watches": [], "briefing": None},
        }

    watches = snapshot.get("watches") or []
    briefing = snapshot.get("briefing")
    return {
        "success": True,
        "message": f"{len(watches)} aktif izleme",
        "data": {"available": True, "watches": watches, "briefing": briefing},
    }
