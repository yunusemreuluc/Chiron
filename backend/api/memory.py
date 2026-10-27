"""Hafıza — kullanıcı hakkında kalıcı olarak bilinenler.

Kullanıcı isteğiyle (2026-07-30) yeniden oluşturuldu; önceki iskelet sürümü
işlevsiz olduğu için 2026-07-29'da silinmişti.

BU UÇ SES DÖNGÜSÜNE İHTİYAÇ DUYMUYOR: hafıza `memory/memory.json` dosyasında
duruyor ve doğrudan buradan okunuyor. Yani Hafıza paneli, arayüz tek başına
açıldığında da (desktop.py --sadece-arayuz) gerçek veriyi gösteriyor. Vision ya
da Otomasyon için bu geçerli değil — onların verisi ses döngüsünün belleğinde.

SALT OKUNUR. Silme işlemi bilinçli olarak yok: hafızayı silmenin yolu Chiron'a
söylemek (`delete_memory` aracı iki adımlı onay istiyor, bkz.
memory/memory_manager.py). Panele bir çöp kutusu koymak, o onay akışını
atlatan ikinci bir yol açardı.
"""

from __future__ import annotations

from fastapi import APIRouter

from memory.memory_manager import load_memory

router = APIRouter(prefix="/api/memory", tags=["memory"])

# `_updated_at`, `_archived_count` gibi iç alanlar kullanıcıya gösterilmiyor;
# bunlar sıkıştırma mekanizmasının defter tutması (bkz. memory_manager).
INTERNAL_PREFIX = "_"

# Kategori adları dosyada teknik anahtarlar hâlinde duruyor. Panelde okunur
# karşılıkları gösteriliyor; listede olmayan bir kategori adı olduğu gibi geçer
# (yeni kategori eklendiğinde panel yine çalışmaya devam etsin).
CATEGORY_LABELS = {
    "identity": "Kimlik",
    "notes": "Notlar",
    "preferences": "Tercihler",
    "personal": "Kişisel",
    "habits": "Alışkanlıklar",
    "whatsapp_contacts": "WhatsApp kişileri",
    "known_objects": "Tanınan nesneler",
    "scheduled_briefing": "Günlük brifing",
    "_archived_summary": "Arşiv",
}


def _entry_text(value: object) -> str:
    """Bir kaydın gösterilecek metni. Kayıtlar {"value": ...} sarmalında ama
    her zaman değil — eski kayıtlar düz string olabiliyor."""
    if isinstance(value, dict):
        inner = value.get("value")
        if inner is not None:
            return str(inner)
        # `value` yoksa iç alanlar hariç kalanları göster.
        visible = {k: v for k, v in value.items() if not k.startswith(INTERNAL_PREFIX)}
        return ", ".join(f"{k}: {v}" for k, v in visible.items())
    return str(value)


def _updated_at(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("_updated_at") or "")
    return ""


@router.get("")
@router.get("/")
async def read_memory() -> dict:
    """Hafızanın tamamı, kategorilere gruplanmış hâlde."""
    memory = load_memory()

    categories = []
    for name, bucket in memory.items():
        if isinstance(bucket, dict):
            entries = [
                {
                    "key": key,
                    # WhatsApp kişilerinde okunur ad ayrı bir alanda duruyor.
                    "label": str(value.get("display_name", key))
                    if isinstance(value, dict) and value.get("display_name")
                    else key,
                    "text": _entry_text(value),
                    "updatedAt": _updated_at(value),
                }
                for key, value in bucket.items()
                if not key.startswith(INTERNAL_PREFIX)
            ]
        else:
            # Düz (sözlük olmayan) kategori — tek bir kayıt gibi gösteriliyor.
            entries = [{"key": name, "label": name, "text": str(bucket), "updatedAt": ""}]

        if not entries:
            continue

        # En son güncellenen üstte; damgası olmayanlar (eski kayıtlar) sona.
        entries.sort(key=lambda entry: entry["updatedAt"], reverse=True)
        categories.append(
            {
                "id": name,
                "label": CATEGORY_LABELS.get(name, name),
                "count": len(entries),
                "entries": entries,
            }
        )

    # Çok kayıtlı kategori üstte: panelde önce hacimli olan görünsün.
    categories.sort(key=lambda category: category["count"], reverse=True)
    total = sum(category["count"] for category in categories)

    return {
        "success": True,
        "message": f"{total} kayıt",
        "data": {"total": total, "categories": categories},
    }
