from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter
from pydantic import BaseModel

from backend.models.events import WSEvent
from backend.websocket.manager import manager

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:  # pragma: no cover — psutil requirements.txt'te var
    HAS_PSUTIL = False

router = APIRouter(prefix="/api/system", tags=["system"])


def read_pc_metrics() -> dict[str, object]:
    """Ağ sondası olmadan hızlı PC ölçümleri; telemetri ve uzak durum bunu paylaşır."""
    if not HAS_PSUTIL:
        raise RuntimeError("psutil yok")

    data: dict[str, object] = {
        "cpu_percent": round(psutil.cpu_percent(interval=None), 1),
        "ram_percent": round(psutil.virtual_memory().percent, 1),
    }
    try:
        data["uptime_minutes"] = max(0, int((time.time() - psutil.boot_time()) // 60))
    except Exception:
        data["uptime_minutes"] = None
    try:
        battery = psutil.sensors_battery()
        if battery is not None:
            data["battery"] = round(battery.percent, 1)
            data["charging"] = bool(battery.power_plugged)
    except Exception:
        pass
    return data


# ── İnternet sondası (2026-07-31) ───────────────────────────────────────────
# "İnternet var mı" sorusunun DÜRÜST cevabı bir arayüz bayrağı değil, gerçek bir
# bağlantı denemesi. psutil'in `net_io_counters`'ı yalnızca arayüzden kaç bayt
# geçtiğini söylüyor — kablo takılı ama internet yokken de artmaya devam eder,
# yani "bağlı" demek için yanlış ölçüt.
#
# TCP/53'e bağlanıp bağlantının kurulma süresini ölçüyoruz. Ping (ICMP) değil:
# Windows'ta ham soket yönetici hakkı ister ve alt süreç açmak gerekirdi.
_PROBE_HOSTS = (("1.1.1.1", 53), ("8.8.8.8", 53))
_PROBE_TIMEOUT_S = 1.5
# Telemetri 3 sn'de bir sorgulanıyor ama sonda 15 sn'de bir çalışıyor: bağlantı
# durumu o hızda değişmiyor ve her karta bir TCP el sıkışması bindirmek gereksiz.
_PROBE_CACHE_S = 15.0
_probe_cache: tuple[float, dict[str, object]] | None = None


async def _probe_internet() -> dict[str, object]:
    """Gerçek bir TCP bağlantısıyla internet durumu + gecikme (ms)."""
    global _probe_cache
    now = time.monotonic()
    if _probe_cache is not None and now - _probe_cache[0] < _PROBE_CACHE_S:
        return _probe_cache[1]

    sonuc: dict[str, object] = {"online": False}
    for host, port in _PROBE_HOSTS:
        basla = time.monotonic()
        try:
            # asyncio ile: bloklayan `socket.create_connection` olay döngüsünü
            # 1.5 sn'ye kadar dondurur ve o sırada WebSocket yayınları da durur.
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=_PROBE_TIMEOUT_S
            )
            gecikme = (time.monotonic() - basla) * 1000
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            # Taban 1 ms: bir TCP el sıkışması asla 0 ms sürmez, ama ölçüm bir
            # kez 0 yuvarladı (2026-07-31). Ekranda "0ms" yazması "kusursuz
            # bağlantı" diye okunurdu — olmayan bir kesinlik iddiası.
            #
            # UYARI: bu sayı "1.1.1.1'e TCP bağlanma süresi", internet
            # kalitesinin tamamı değil. Araya şeffaf bir vekil/güvenlik duvarı
            # giren ağlarda SYN'i o cihaz yanıtlar ve süre gerçekte olduğundan
            # iyi görünür. Ulaşılabilirlik için doğru, hız testi için değil.
            sonuc = {"online": True, "latency": max(1, round(gecikme))}
            break
        except Exception:
            continue

    _probe_cache = (now, sonuc)
    return sonuc


@router.get("/telemetry")
async def telemetry() -> dict:
    """Üst telemetri kartının verisi (2026-07-30).

    YALNIZCA GERÇEKTEN ÖLÇEBİLDİKLERİMİZ dönüyor. Notes/Tasarim-Kurallari.md § Panel yerleşimi ayrıca
    GPU ve sıcaklık istiyor ama Windows'ta psutil ikisini de güvenilir şekilde
    veremiyor (`sensors_temperatures` çoğu masaüstünde boş döner, GPU için ayrı
    bir satıcı kütüphanesi gerekir). Uydurulmuş ya da "N/A" dolu bir kart,
    olmayan bir yeteneği varmış gibi gösterirdi — o alanlar hiç yok.

    `cpu_percent(interval=None)` bloklamıyor: son çağrıdan bu yana geçen süreyi
    baz alıyor. İlk çağrı 0.0 döner, sonrakiler anlamlıdır — kart periyodik
    sorguladığı için bu doğru davranış (interval=0.5 verseydik her istek yarım
    saniye backend'i bloklardı).
    """
    try:
        metrics = read_pc_metrics()
        data: dict[str, object] = {
            "cpu": metrics["cpu_percent"],
            "ram": metrics["ram_percent"],
        }
        data["disk"] = round(psutil.disk_usage("C:\\").percent, 1)
    except Exception:
        return {"success": False, "message": "sistem bilgisi okunamadı", "data": {}}

    # Pil yalnızca dizüstünde var; masaüstünde alan hiç gönderilmiyor (null
    # göndermek arayüzde "pil %—" gibi anlamsız bir satır üretirdi).
    if "battery" in metrics:
        data["battery"] = metrics["battery"]
        data["charging"] = metrics["charging"]

    # İnternet: gerçek bağlantı denemesi (bkz. _probe_internet). Çevrimdışıysa
    # `online: False` dönüyor ve alan GİZLENMİYOR — "internet yok" bir eksiklik
    # değil, kullanıcının bilmesi gereken bir bilgi. GPU/sıcaklıktan farkı bu:
    # onları ölçemiyoruz, bunu ölçebiliyoruz ve cevabı "hayır".
    data["net"] = await _probe_internet()

    return {"success": True, "message": "telemetri", "data": data}


@router.get("/context")
async def context() -> dict:
    """Ambient bağlam — Aıron'un "kullanıcı şu an ne yapıyor" farkındalığı.

    Aynı kaynağı `get_context` aracı da kullanıyor (actions/ambient_context.py):
    araç modele, bu uç nokta arayüze. İkisi AYNI fonksiyondan besleniyor, yani
    arayüzde gördüğün şey Aıron'un gerçekten bildiği şey — ayrı yazılsalardı
    biri bayatlar ve arayüz olmayan bir farkındalığı varmış gibi gösterirdi
    (bkz. Notes/Bilinen-Tuzaklar.md § Arayüzde dürüstlük).

    Import fonksiyon İÇİNDE: `actions/` zinciri (psutil, ctypes) backend
    açılışında değil, ilk istekte yükleniyor.
    """
    try:
        from actions.ambient_context import describe_context, read_context

        ham = read_context()
        return {"success": True, "message": describe_context(ham), "data": ham}
    except Exception as exc:
        return {"success": False, "message": f"bağlam okunamadı: {exc}", "data": {}}


class StateUpdate(BaseModel):
    state: str


# Durumu dışarıdan enjekte etmek için. Ses döngüsü bunu KULLANMAZ — o, aynı
# süreçte çalıştığı için olayı doğrudan yayınlıyor (bkz. core/web_ui.py set_state).
# Burası arayüzü elle test etmek ve ileride harici bir entegrasyonun durum
# göndermesi için duruyor.
@router.post("/state")
async def system_state(update: StateUpdate) -> dict:
    await manager.broadcast(WSEvent(event="energy_state", data={"state": update.state}))
    return {"success": True, "message": "yayınlandı", "data": {}}
