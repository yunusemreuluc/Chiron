"""
Airon'un salt-okunur yeteneklerini MCP'ye taşıyan ince sarmalayıcılar.

Buradaki fonksiyonlar Airon'un MEVCUT kodunu import edip çağırıyor; Airon'da
hiçbir dosya değişmiyor. Her fonksiyon ya Pydantic bir sonuç modeli döner ya da
`ToolError` fırlatır — MCPServer bunu `is_error=True` + okunabilir mesaja
çeviriyor, server çökmüyor.

GÜVENLİK SINIRI: Airon'da iki adımlı onay (`confirm=false` → `confirm=true`)
isteyen hiçbir araç buraya alınmadı. Buradaki dört aracın hiçbiri dosya yazmaz,
silmez, tıklamaz, ağ isteği atmaz. Ekran görüntüsü için Airon'un geçici bir PNG
yazması istisna — o dosya iş bitince siliniyor.
"""

from __future__ import annotations

import io
import os
import re
import sys
import threading
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

# Airon modülleri `from actions...`, `from core...` diye mutlak import ediyor —
# repo kökü sys.path'te olmalı. Server hangi klasörden başlatılırsa başlatılsın.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from actions import ambient_context, notifications, ocr  # noqa: E402
from memory import memory_manager  # noqa: E402

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000

# Hafızada olup MCP'ye ASLA açılmayan kategoriler. whatsapp_contacts telefon
# numarası tutuyor — Airon'un kendisi mesaj göndermek için kullanıyor ama bir
# dış modele dökülmesinin bir faydası yok, sadece riski var.
PRIVATE_MEMORY_CATEGORIES = {"whatsapp_contacts"}

# Kategori dışlamak yetmiyor: kullanıcı "annemin numarası ..." dediğinde Airon
# bunu notes/ altına da kaydedebiliyor. Her değerde telefon benzeri diziler
# (10–15 rakam, boşluk/tire/nokta/parantez ayraçlı, başta + olabilir) maskelenir.
_PHONE_CANDIDATE = re.compile(r"\+?\d[\d\s().-]{8,}\d")
PHONE_MASK = "[telefon gizlendi]"


def _mask_phones(text: str) -> str:
    def repl(match: re.Match) -> str:
        digits = sum(ch.isdigit() for ch in match.group(0))
        return PHONE_MASK if 10 <= digits <= 15 else match.group(0)

    return _PHONE_CANDIDATE.sub(repl, text)


# ── Sonuç modelleri (MCP outputSchema bunlardan üretiliyor) ─────────────────

class TextLine(BaseModel):
    text: str
    confidence: float = Field(description="EasyOCR güveni, 0..1")
    box: list[float] = Field(description="Normalize [x1, y1, x2, y2], 0..1")


class ReadTextResult(BaseModel):
    source: str = Field(description="'screen' veya okunan dosyanın yolu")
    text: str = Field(description="Okuma sırasına dizilmiş tüm metin, tek satırda")
    lines: list[TextLine]
    window_title: str = Field("", description="source='screen' ise o anki aktif pencere başlığı")


class ActiveContext(BaseModel):
    summary: str = Field(description="Tek satırlık insan-okur özet")
    app: str
    process: str
    window_title: str
    idle_seconds: float
    away: bool = Field(description="Kullanıcı uzun süredir klavye/fareye dokunmadı mı")
    time: str
    date: str


class MemoryHit(BaseModel):
    category: str
    key: str
    value: str


class MemorySearchResult(BaseModel):
    query: str
    matches: list[MemoryHit]


class Notification(BaseModel):
    app: str
    title: str
    message: str


class NotificationsResult(BaseModel):
    count: int
    notifications: list[Notification]


# ── 1. Ekrandaki / görüntüdeki yazıyı oku ───────────────────────────────────

def _is_remote(path_text: str) -> bool:
    """UNC (\\\\sunucu\\paylasim), aygıt yolu (\\\\?\\...) veya eşlenmiş ağ sürücüsü mü.

    NEDEN: Windows'ta bir UNC yoluna `is_file()` bile SMB bağlantısı açar ve
    kullanıcının NTLM kimlik özetini o sunucuya gönderir. Yol modelden geliyor;
    modele enjekte edilmiş bir metin bu yolu seçtirebilir. Bu yüzden kontrol
    dosya sistemine HİÇ dokunmadan, sadece metin üzerinden yapılıyor.
    """
    if path_text.startswith(("\\\\", "//")):
        return True
    drive = Path(path_text).drive
    if len(drive) == 2 and drive[1] == ":":
        import ctypes

        DRIVE_REMOTE = 4
        return ctypes.windll.kernel32.GetDriveTypeW(drive + "\\") == DRIVE_REMOTE
    return False


def _reject_links_to_remote(path: Path, depth: int = 0) -> None:
    """Yolun herhangi bir parçası ağa yönlenen bir symlink/junction mı.

    `resolve()` kullanılmıyor: Windows'ta hedefi çözmek için dosyayı AÇIYOR —
    hedef bir UNC yolsa korunmaya çalışılan ağ erişimi tam orada oluyor.
    `os.readlink` ise sadece bağlantının kendisini okuyor, hedefe gitmiyor.
    """
    if depth > 8:
        raise ToolError("Yolda çok fazla iç içe bağlantı var.")
    for part in [*reversed(path.parents), path]:
        try:
            target = os.readlink(part)
        except (OSError, ValueError):
            continue  # bağlantı değil ya da yok — normal
        if _is_remote(target):
            raise ToolError(f"Ağ konumuna yönlenen bağlantılar desteklenmiyor: {part}")
        _reject_links_to_remote(Path(target), depth + 1)


def _load_image_bytes(image_path: str) -> bytes:
    if _is_remote(image_path):
        raise ToolError("Ağ yolları (UNC / ağ sürücüsü) desteklenmiyor — yerel bir dosya verin.")
    path = Path(image_path).expanduser()
    if not path.is_absolute():
        raise ToolError(f"image_path mutlak bir yol olmalı, verilen: {image_path!r}")
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ToolError(
            f"Desteklenmeyen dosya türü: {path.suffix or '(uzantısız)'}. "
            f"Desteklenenler: {', '.join(sorted(IMAGE_EXTENSIONS))}"
        )
    _reject_links_to_remote(path)

    try:
        if not path.is_file():
            raise ToolError(f"Görüntü dosyası bulunamadı: {path}")
        size = path.stat().st_size
        if size > MAX_IMAGE_BYTES:
            raise ToolError(f"Görüntü çok büyük ({size // 1024 // 1024} MB), sınır 20 MB.")
        data = path.read_bytes()
    except OSError as exc:
        raise ToolError(f"Dosya okunamadı ({type(exc).__name__}): {path}") from exc

    # ocr.read_text_in_jpeg hatayı yutup boş liste dönüyor — bozuk bir dosya
    # "yazı yok" gibi görünmesin diye görüntüyü burada önceden doğruluyoruz.
    # Piksel sınırı: 20 MB sınırı sıkıştırılmış boyutu ölçüyor; ~100 KB'lık
    # bir PNG 100 megapiksel açılıp yüzlerce MB bellek yiyebiliyor.
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            width, height = img.size
            if width * height > MAX_IMAGE_PIXELS:
                raise ToolError(
                    f"Görüntü çözünürlüğü çok yüksek ({width}x{height}), "
                    f"sınır {MAX_IMAGE_PIXELS // 1_000_000} megapiksel."
                )
            img.verify()
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Dosya okunabilir bir görüntü değil: {path.name} ({exc})") from exc
    return data


_reader_lock = threading.Lock()


def _ensure_ocr_reader() -> None:
    """OCR okuyucusunu Airon'un önbelleğine İNDİRMESİZ kurar.

    Airon'un kendi `_get_reader()`'ı EasyOCR'ı varsayılan `download_enabled=True`
    ile başlatıyor: model eksikse ağdan indiriyor ve hatayı yutuyor (sonuç "yazı
    yok" görünüyor). MCP tarafı ağsız ve dürüst olmalı — okuyucuyu aynı
    ayarlarla ama indirme kapalı kurup Airon'un önbellek değişkenine koyuyoruz;
    Airon'un kodu değişmiyor, `read_text_in_jpeg` bu hazır okuyucuyu kullanıyor.
    """
    with _reader_lock:
        if ocr._reader_cache is not None:
            return
        try:
            import easyocr

            ocr._reader_cache = easyocr.Reader(
                ocr.LANGUAGES, gpu=False, verbose=False, download_enabled=False)
        except Exception as exc:
            raise ToolError(
                f"OCR modeli yüklenemedi ({exc}). Modeller ~/.EasyOCR/model altında olmalı; "
                "Airon'da bir kez metin okutmak onları indirir."
            ) from exc


def _capture_screen() -> tuple[bytes, str]:
    # screen_vision google-genai'yi modül seviyesinde import ediyor (~1 sn);
    # ekran hiç okunmazsa bu bedel ödenmesin diye burada, geç import.
    from actions import screen_vision

    captured, path_or_error, window_title = screen_vision._capture_active_window()
    if not captured:
        raise ToolError(path_or_error)
    # Airon bu PNG'yi tempfile'a yazıp bırakıyor (Gemini'ye yüklemek için).
    # Burada ekran görüntüsü diskte kalmasın: oku ve sil.
    tmp = Path(path_or_error)
    try:
        return tmp.read_bytes(), window_title
    finally:
        tmp.unlink(missing_ok=True)


def read_text(source: Literal["screen", "image"], image_path: str | None) -> ReadTextResult:
    if not ocr.HAS_EASYOCR:
        raise ToolError("easyocr kurulu değil — Airon'un requirements.txt notuna bakın.")
    _ensure_ocr_reader()

    if source == "image":
        if not image_path:
            raise ToolError("source='image' için image_path zorunlu.")
        data = _load_image_bytes(image_path)
        window_title = ""
        label = str(Path(image_path).expanduser())
    else:
        data, window_title = _capture_screen()
        label = "screen"

    lines = ocr.read_text_in_jpeg(data)
    return ReadTextResult(
        source=label,
        text=ocr.lines_to_text(lines),
        lines=[TextLine(**line) for line in lines],
        window_title=window_title,
    )


# ── 2. Kullanıcı şu an ne yapıyor ───────────────────────────────────────────

def active_context() -> ActiveContext:
    try:
        ctx = ambient_context.read_context()
        summary = ambient_context.describe_context(ctx)
    except Exception as exc:
        raise ToolError(f"Aktif pencere bilgisi okunamadı: {exc}") from exc
    return ActiveContext(summary=summary, **{k: ctx[k] for k in ActiveContext.model_fields if k != "summary"})


# ── 3. Airon hafızasında arama ──────────────────────────────────────────────

def search_memory(query: str, limit: int) -> MemorySearchResult:
    needle = memory_manager._normalize_text(query)
    if len(needle) < 2:
        raise ToolError("Sorgu en az 2 karakter olmalı.")

    mem = memory_manager.load_memory()
    hits: list[MemoryHit] = []
    for category, bucket in mem.items():
        if category in PRIVATE_MEMORY_CATEGORIES:
            continue
        # Airon'un delete_memory'si de aynı iki şekli ele alıyor: kategori
        # altında anahtar/değer sözlüğü ya da doğrudan bir değer.
        items = bucket.items() if isinstance(bucket, dict) else [(category, bucket)]
        for key, value in items:
            if memory_manager._entry_matches(needle, category, key, value):
                hits.append(MemoryHit(
                    category=category,
                    key=_mask_phones(str(key)),
                    value=_mask_phones(memory_manager._entry_value_text(value)),
                ))
            if len(hits) >= limit:
                return MemorySearchResult(query=query, matches=hits)
    return MemorySearchResult(query=query, matches=hits)


# ── 4. Windows bildirimleri ─────────────────────────────────────────────────

async def recent_notifications(limit: int) -> NotificationsResult:
    result = await notifications.get_recent_notifications(limit)
    if not result.get("success"):
        raise ToolError(result.get("message") or "Bildirimler okunamadı.")
    items = result.get("data", {}).get("notifications", [])
    return NotificationsResult(
        count=len(items),
        notifications=[
            Notification(app=i.get("app", ""), title=i.get("title", ""), message=i.get("message", ""))
            for i in items
        ],
    )
