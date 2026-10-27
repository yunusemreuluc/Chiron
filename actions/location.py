"""
Gerçek konum tespiti — Windows Konum Servisi, olmazsa IP tabanlı.

Kullanıcı isteğiyle (2026-07-31): hava durumu sabit bir şehre değil, kullanıcının
GERÇEKTEN bulunduğu yere baksın. Önceden `actions/weather.py` sırasıyla
parametre → `CHIRON_WEATHER_LOCATION` → sabit "Konya" deniyordu; sabit değer
tesadüfen doğruydu ama taşınınca ya da seyahatte yanlış olurdu.

İKİ KAYNAK, SIRAYLA:

1. **Windows Konum Servisi** (`winsdk`, zaten bildirimler için kurulu) — WiFi/GPS
   tabanlı, bu makinede ölçülen doğruluk ~126 m. Kullanıcı Windows ayarlarından
   konum iznini kapattıysa kullanılamaz.
2. **IP tabanlı** (ip-api.com) — izin gerektirmez, her zaman çalışır ama VPN ya
   da operatör yönlendirmesi yüzünden yanlış şehir verebilir.

İkisi de başarısız olursa `None` döner ve çağıran taraf kendi varsayılanına
düşer — bu modül asla exception fırlatmaz.

GİZLİLİK: konum yalnızca bellekte tutulur, hiçbir yere yazılmaz. Dışarı giden
tek istek hava durumu sorgusunun kendisidir.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import threading
import time
from typing import Any

import requests

logger = logging.getLogger("chiron")

HAS_WINSDK = importlib.util.find_spec("winsdk") is not None

# Windows konum servisi bazen ilk çağrıda donanımı uyandırırken bekletiyor.
# Bu süreyi aşarsa IP'ye düşülüyor — kullanıcı hava durumu sorduğunda 20 saniye
# beklemek kabul edilebilir değil.
WINDOWS_TIMEOUT_SECONDS = 8.0
IP_TIMEOUT_SECONDS = 6.0

# Konum sık değişmiyor; her hava durumu sorgusunda cihazı/servisi yeniden
# yormanın anlamı yok. Seyahat hâlinde 15 dakikalık gecikme kabul edilebilir.
CACHE_SECONDS = 15 * 60

_cache: dict[str, Any] | None = None
_cache_at = 0.0
_lock = threading.Lock()


def _detect_windows() -> dict[str, Any] | None:
    """Windows Konum Servisi (WinRT, asenkron).

    KENDİ THREAD'İNDE kendi olay döngüsüyle çalışıyor: bu fonksiyon senkron bir
    araçtan (get_weather) çağrılıyor ama çağıran taraf bazen zaten bir asyncio
    döngüsünün içinde oluyor. `asyncio.run()` doğrudan çağrılırsa "this event
    loop is already running" hatası verirdi.
    """
    if not HAS_WINSDK:
        return None

    sonuc: dict[str, Any] | None = None

    def calis() -> None:
        nonlocal sonuc
        try:
            from winsdk.windows.devices.geolocation import Geolocator, GeolocationAccessStatus

            async def al():
                durum = await Geolocator.request_access_async()
                if durum != GeolocationAccessStatus.ALLOWED:
                    return None
                position = await Geolocator().get_geoposition_async()
                point = position.coordinate.point.position
                return {
                    "lat": float(point.latitude),
                    "lon": float(point.longitude),
                    "accuracy_m": float(position.coordinate.accuracy or 0),
                    "source": "windows",
                }

            sonuc = asyncio.run(asyncio.wait_for(al(), WINDOWS_TIMEOUT_SECONDS))
        except Exception:
            logger.debug("[Konum] Windows konum servisi kullanılamadı", exc_info=True)

    thread = threading.Thread(target=calis, name="chiron-location", daemon=True)
    thread.start()
    # Thread'in kendi zaman aşımı var; buradaki pay ona ek olarak WinRT'nin
    # kapanış süresini kapsıyor.
    thread.join(WINDOWS_TIMEOUT_SECONDS + 3)
    return sonuc


def _detect_ip() -> dict[str, Any] | None:
    """IP tabanlı konum — izin gerektirmez, şehir adını da verir."""
    try:
        response = requests.get(
            "http://ip-api.com/json/",
            params={"fields": "status,country,city,regionName,lat,lon"},
            timeout=IP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "success":
            return None
        return {
            "lat": float(data["lat"]),
            "lon": float(data["lon"]),
            "city": str(data.get("city") or "").strip(),
            "country": str(data.get("country") or "").strip(),
            "accuracy_m": None,
            "source": "ip",
        }
    except Exception:
        logger.debug("[Konum] IP tabanlı konum alınamadı", exc_info=True)
        return None


def _reverse_name(lat: float, lon: float) -> str:
    """Koordinat → okunur yer adı.

    Windows Konum Servisi yalnızca koordinat veriyor, şehir adı vermiyor
    (`civic_address` çoğu makinede boş). Ad olmadan kullanıcıya "37.88,32.49 için
    hava durumu" ya da "Bulunduğun yer için tahmin" demek zorunda kalıyorduk.

    wttr.in'in `j1` cevabındaki `nearest_area` kullanılıyor — hava durumu için
    zaten çağırdığımız servis, ekstra bağımlılık yok.

    DİKKAT: `format=%l` biçimi denendi ve İŞE YARAMIYOR — koordinatla
    sorulduğunda koordinatı olduğu gibi geri yankılıyor, ad çözmüyor. Ad
    yalnızca `j1` cevabının içinde geliyor.

    Başarısız olursa boş string döner, çağıran taraf kendi yedeğine düşer.
    """
    try:
        response = requests.get(
            f"https://wttr.in/{lat:.4f},{lon:.4f}",
            params={"format": "j1"},
            timeout=IP_TIMEOUT_SECONDS,
            headers={"User-Agent": "Chiron Windows"},
        )
        response.raise_for_status()
        area = (response.json().get("nearest_area") or [{}])[0]
        name = str(((area.get("areaName") or [{}])[0]).get("value", "")).strip()
        # Ad çözülemediğinde servis koordinatı geri verebiliyor.
        return "" if not name or name[0].isdigit() else name
    except Exception:
        logger.debug("[Konum] Yer adı çözülemedi", exc_info=True)
        return ""


def detect_location(force: bool = False) -> dict[str, Any] | None:
    """Kullanıcının bulunduğu yer.

    `{"lat", "lon", "source", "accuracy_m", "city"?}` döner; hiçbir kaynak
    çalışmazsa `None`. ASLA exception fırlatmaz.

    `force=True` önbelleği atlar (kullanıcı "konumumu güncelle" derse).
    """
    global _cache, _cache_at

    with _lock:
        if not force and _cache is not None and (time.monotonic() - _cache_at) < CACHE_SECONDS:
            return _cache

    konum = _detect_windows() or _detect_ip()

    if konum is not None:
        # Windows kaynağı ad vermiyor; bir kez çözüp önbelleğe koy. IP kaynağı
        # adı zaten getiriyor, o zaman bu istek hiç yapılmıyor.
        if not konum.get("city"):
            konum["city"] = _reverse_name(konum["lat"], konum["lon"])

        with _lock:
            _cache, _cache_at = konum, time.monotonic()
        logger.info(
            "[Konum] %s → %.4f, %.4f (%s)",
            konum["source"], konum["lat"], konum["lon"], konum.get("city") or "adsız",
        )
    return konum


def as_query(konum: dict[str, Any] | None) -> str | None:
    """Konumu hava durumu servislerinin anlayacağı sorguya çevirir.

    Koordinat tercih ediliyor, şehir adı değil: "Konya" birden fazla yere
    işaret edebilir ama koordinat tektir. wttr.in `lat,lon` biçimini kabul
    ediyor ve cevabında `nearest_area` ile okunur şehir adını geri veriyor.
    """
    if not konum:
        return None
    return f"{konum['lat']:.4f},{konum['lon']:.4f}"
