"""
Araç dönüşleri için standart şema.

Eskiden her araç düz bir Türkçe string dönüyordu; main.py ise bu string içinde
"hata", "gerekli", "bağlantı" gibi anahtar kelimeler arayarak başarı/başarısızlık
TAHMİN ediyordu (_result_looks_like_error) — kırılgan bir sezgiseldi (örn.
"gerekli." gibi çok genel bir kelime yanlış pozitif üretebilirdi). Artık her
araç `{"success": bool, "message": str, "data": dict}` döner, main.py da
doğrudan `success` alanına bakar.

`message` alanı hâlâ kullanıcıya sesli aktarılacak doğal dil metni — sadece
artık yanına açık bir başarı/başarısızlık bayrağı ve (varsa) yapılandırılmış
ek veri (`data`) eşlik ediyor.
"""

from __future__ import annotations


def ok(message: str, **data) -> dict:
    return {"success": True, "message": message, "data": data}


def fail(message: str, **data) -> dict:
    return {"success": False, "message": message, "data": data}


# Yunus 2026-11-07: "bilmiyorum demesin". Karar sınavında prompt kuralı yetmedi: model araç hata dönünce "yapamam" deyip
# bırakıyor, hatta hata dönen aracı "araştırıyorum" diye anlatıyordu. Model kararı verirken en çok araç sonucuna bakıyor.
FALLBACK_HINT = (
    "Bu yol olmadı. 'Yapamam' deyip bırakma, çalışıyormuş gibi de anlatma: aynı işi yapacak BAŞKA aracı şimdi çağır "
    "(bilmiyorsan learn_how; PC'de iş, dosya, dönüştürme için delegate_to_pc ya da shell_run). Sebep güvenlik, onay, oyun "
    "ya da kullanıcıdan eksik bilgiyse zorlama, kullanıcıya söyle. Hepsi olmazsa neyi denediğini dürüstçe söyle."
)


def with_fallback_hint(result: dict) -> dict:
    """Başarısız araç sonucuna sonraki adımı ekler. Başarılı sonuca ve yeni sözlük dışına dokunmaz."""
    if not isinstance(result, dict) or result.get("success", True):
        return result
    return {**result, "next_step": FALLBACK_HINT}
