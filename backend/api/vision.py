"""Görü (vision) — kamera akışı ve yerel nesne tespiti.

Kullanıcı isteğiyle (2026-07-30) yeniden oluşturuldu. Önceki sürümü işlevsiz bir
iskelet olduğu için 2026-07-29 temizliğinde silinmişti; bu sürüm gerçekten
çalışıyor.

MİMARİ — bu uçlar SONUÇ DÖNDÜRMÜYOR, komut gönderiyor:

    Vision paneli ──HTTP──> burası ──commands──> ChironLive (ses döngüsü thread'i)
    Vision paneli <───────────── WebSocket <──────────── WebUI

Sebebi kameranın bu katmanın elinde olmaması: cihazı `WebcamStreamer` (main.py)
tutuyor ve o ses döngüsünün thread'inde yaşıyor. Komut kanalı (backend/core/
commands.py) bilinçli olarak tek yönlü ve sonuç taşımıyor. Bu yüzden tespit
sonuçları HTTP cevabıyla değil, `vision_detections` WebSocket olayıyla dönüyor —
zaten kameranın kareleri de (`webcam_frame`) aynı yoldan akıyor, yani panel tek
bir akışı dinliyor.

Pratik sonucu: `/detect` "tarama başladı" der, sonuç birkaç yüz ms sonra
soketten gelir. Panel bu arada "taranıyor" durumunu gösteriyor.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.core import commands

router = APIRouter(prefix="/api/vision", tags=["vision"])

# WebUI örneğine doğrudan erişimimiz yok (o ses döngüsünün tarafında yaşıyor),
# ama komutların kayıtlı olup olmaması "vision kullanılabilir mi" sorusunun
# cevabı: kayıt yalnızca WebUI ayağa kalktığında yapılıyor.
_WEBCAM_COMMAND = "webcam"
_DETECT_COMMAND = "vision_detect"
_OCR_COMMAND = "vision_ocr"


@router.get("/status")
async def vision_status() -> dict:
    """Görü özellikleri bu pencerede kullanılabilir mi?

    Arayüz tek başına da açılabiliyor (desktop.py --sadece-arayuz) — o durumda
    kamera diye bir şey yok ve panel bunu dürüstçe söylemeli, düğmeleri boşuna
    aktif göstermemeli.
    """
    available = commands.is_connected() and _WEBCAM_COMMAND in commands.known_commands()
    return {
        "success": True,
        "message": "görü hazır" if available else "sesli asistan çalışmıyor",
        "data": {"available": available},
    }


class WebcamToggle(BaseModel):
    enabled: bool


@router.post("/webcam")
async def toggle_webcam(update: WebcamToggle) -> dict:
    """Kamerayı açar/kapatır. Gerçek durum `webcam_state` olayıyla geri geliyor —
    burada "istek iletildi"den fazlasını söylemek yalan olurdu, cihazı açan taraf
    başka bir thread."""
    if not commands.dispatch(_WEBCAM_COMMAND, {"enabled": update.enabled}):
        return {"success": False, "message": "Sesli asistan çalışmıyor.", "data": {}}
    return {
        "success": True,
        "message": "Kamera açılıyor" if update.enabled else "Kamera kapatılıyor",
        "data": {"requested": update.enabled},
    }


@router.post("/detect")
async def detect_objects() -> dict:
    """Tek karelik yerel nesne tespiti (YOLO-World) tetikler.

    Sonuç `vision_detections` WebSocket olayıyla gelir. İlk çağrı yavaş olabilir:
    torch/ultralytics zinciri (~273 MB) o an yükleniyor (bkz.
    actions/object_recognition.py — bilerek tembel yükleme)."""
    if not commands.dispatch(_DETECT_COMMAND, {}):
        return {"success": False, "message": "Sesli asistan çalışmıyor.", "data": {}}
    return {"success": True, "message": "Tarama başladı", "data": {}}


@router.post("/ocr")
async def read_text() -> dict:
    """Tek karelik yerel metin okuma (EasyOCR) tetikler.

    Sonuç `vision_text` WebSocket olayıyla gelir. İlk çağrı yavaştır: EasyOCR
    tanıma modelleri (~100 MB) o an indiriliyor/yükleniyor olabilir
    (bkz. actions/ocr.py). Sonraki okumalar CPU'da ~1 saniye.
    """
    if not commands.dispatch(_OCR_COMMAND, {}):
        return {"success": False, "message": "Sesli asistan çalışmıyor.", "data": {}}
    return {"success": True, "message": "Okuma başladı", "data": {}}
