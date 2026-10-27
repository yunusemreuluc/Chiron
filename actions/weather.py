"""
Basit hava durumu ozeti — uzaktaki bir servis uzerinden calisir.
Alp Ünlü tarafından yapılmıştır — @alppunlu

KONUM ÖNCELİĞİ (2026-07-31'de gerçek konum tespiti eklendi):
1. Çağrıda verilen `location` — kullanıcı açıkça bir şehir söylediyse ("Ankara'da
   hava nasıl") o kazanır
2. `CHIRON_WEATHER_LOCATION` env değişkeni — elle konulmuş kalıcı geçersiz kılma
3. **Gerçek konum** (actions/location.py — Windows Konum Servisi, olmazsa IP)
4. `DEFAULT_LOCATION` — yalnızca yukarıdakilerin hepsi başarısızsa

3. adım eklenmeden önce sabit bir şehre bakılıyordu; tesadüfen doğruydu ama
kullanıcı taşınsa ya da seyahate çıksa sessizce yanlış cevap verirdi.
"""

from __future__ import annotations

import os

import requests

from actions.location import as_query, detect_location
from actions.tool_result import fail, ok
from core.tool_registry import register_tool

# Hiçbir kaynak çalışmazsa kullanılan son çare. Artık "varsayılan konum" değil,
# yalnızca gerçek tespit de IP de başarısız olduğunda devreye giren bir yedek.
DEFAULT_LOCATION = "Konya"


def _resolve_target(location: str | None) -> tuple[str, str]:
    """(servise gönderilecek sorgu, kullanıcıya gösterilecek ad).

    Gerçek konumda sorgu KOORDİNAT oluyor, şehir adı değil: "Konya" birden fazla
    yere işaret edebilir, koordinat tektir. Gösterilecek ad o zaman boş dönüyor
    ve servisin cevabındaki `nearest_area`dan doldurluyor — böylece kullanıcı
    hangi şehre bakıldığını görüyor, ham koordinat duymuyor.
    """
    explicit = (location or "").strip()
    if explicit:
        return explicit, explicit

    override = (os.environ.get("CHIRON_WEATHER_LOCATION") or "").strip()
    if override:
        return override, override

    detected = detect_location()
    query = as_query(detected)
    if query:
        return query, str((detected or {}).get("city") or "")

    return DEFAULT_LOCATION, DEFAULT_LOCATION


@register_tool("get_weather")
def get_weather_summary(location: str | None = None) -> dict:
    target, display = _resolve_target(location)
    try:
        response = requests.get(
            f"https://wttr.in/{target}",
            params={"format": "j1"},
            timeout=10,
            headers={"User-Agent": "Chiron Windows"},
        )
        response.raise_for_status()
        payload = response.json()
        current = (payload.get("current_condition") or [{}])[0]
        temp_c = current.get("temp_C")
        feels_like = current.get("FeelsLikeC")
        weather_desc = ((current.get("weatherDesc") or [{}])[0]).get("value", "")
        humidity = current.get("humidity")

        # Koordinatla sorulduysa okunur şehir adını cevaptan al — kullanıcıya
        # "37.88,32.49 için hava durumu" demek anlamsız olurdu.
        if not display:
            area = (payload.get("nearest_area") or [{}])[0]
            display = str(((area.get("areaName") or [{}])[0]).get("value", "")).strip()
        if not display:
            display = target

        parts = []
        if temp_c:
            parts.append(f"{temp_c} derece")
        if weather_desc:
            parts.append(weather_desc.lower())
        if feels_like and feels_like != temp_c:
            parts.append(f"hissedilen {feels_like} derece")
        if humidity:
            parts.append(f"nem yüzde {humidity}")

        if not parts:
            return fail("Hava durumu bilgisi şu anda alınamadı.")

        return ok(
            f"{display} için hava durumu: " + ", ".join(parts) + ".",
            location=display, temp_c=temp_c, feels_like_c=feels_like,
            description=weather_desc, humidity=humidity,
        )
    except Exception:
        return fail("Hava durumu bilgisi şu anda alınamadı.")
