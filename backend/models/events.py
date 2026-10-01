"""WebSocket olay zarfı — backend'den arayüze giden her olayın tek tipi.

Yeni bir olay eklerken: buradaki EventType'a ekle, yayınlayan tarafta
`manager.broadcast_threadsafe` ile gönder, arayüzde `useAIStateConnection.ts`
içindeki switch'e bir dal ekle. Üçü birden yapılmazsa olay sessizce düşer."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

EventType = Literal[
    "voice_start",
    "voice_stop",
    "thinking",
    "vision_update",
    "memory_update",
    "task_started",
    "task_finished",
    "system_status",
    "notification",
    "energy_state",
    # 2026-07-29 — sesli asistan (main.py) artık aynı süreçte, Tkinter yerine bu
    # arayüzü kullanıyor (bkz. core/web_ui.py). Aşağıdakiler AironUI'nin ekrana
    # yazdığı şeylerin WebSocket karşılığı.
    "log",  # sohbet satırı: "Siz: ..." / "Aıron: ..." / "SYS:" / "ERR:"
    "debug",  # geliştirici günlüğü (seviye: INFO/WARN/ERROR)
    "panel_focus",  # bir aracın ilgili paneli vurgulaması (saat/hava/sistem)
    "webcam_state",  # webcam açıldı/kapandı
    "webcam_frame",  # base64 JPEG önizleme karesi
    "vision_detections",  # yerel YOLO-World nesne tespiti sonuçları (Vision paneli)
    "vision_text",  # yerel EasyOCR ile okunan metin satırları (Vision paneli)
    "mic_level",  # mikrofon ses seviyesi 0..1 (sohbet dock'undaki dalga formu)
    "reasoning",  # modelin düşünme adımı (alt zaman çizelgesi)
    "sfx",  # arayüzün çalması istenen ses efekti
    "user_activity",  # kullanıcı konuşuyor (giriş transkripti geldi)
    "assistant_status",  # muted/paused gibi kalıcı durum bayrakları
    "office_update",  # Ajan Ofisi anlık görüntüsü (backend/core/ofis.py)
]


class WSEvent(BaseModel):
    event: EventType
    data: dict[str, Any] = {}
