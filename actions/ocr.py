"""
Metin okuma (OCR) — EasyOCR ile YEREL, Türkçe + İngilizce.

NEDEN GEMINI DEĞİL: Gemini vision bu işi yapabilirdi ama her okuma günlük
kotadan yerdi ve kota bu projede gerçek bir kısıt (vision-ağır özellikler aynı
gün art arda denenince 429'a takılıyor). EasyOCR tamamen yerel çalışıyor: kotaya
dokunmuyor, internet gerektirmiyor (ilk çalıştırmadaki model indirmesi hariç).

DİKKAT — easyocr BURADA import EDİLMEZ. Aynı gerekçe object_recognition.py'deki
ultralytics notunda: modül seviyesinde import edilirse torch + scikit-image
zinciri her açılışta yükleniyor ve kullanıcı OCR'ı hiç çalıştırmasa bile bu bedel
ödeniyor. Paketin KURULU OLUP OLMADIĞINI öğrenmek için import gerekmiyor;
find_spec yalnızca dosya sisteminde arar.

İLK ÇAĞRI YAVAŞTIR: EasyOCR tanıma modellerini (~100 MB) ilk kullanımda
~/.EasyOCR/ altına indiriyor. Sonraki çağrılar diskten okuyor.
"""

from __future__ import annotations

import importlib.util
import io
import logging

from core.idle_model import IdleModel

HAS_EASYOCR = importlib.util.find_spec("easyocr") is not None

try:
    from PIL import Image

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

logger = logging.getLogger("airon")

# Türkçe + İngilizce birlikte: EasyOCR Latin alfabeli dilleri aynı modelde
# birleştirebiliyor. Türkçe'ye özgü karakterler (ş, ğ, ı, ö, ü, ç) 'tr' olmadan
# yanlış okunuyor — 'paket' yerine 'paket' gibi görünse de 'ışık' bozuluyor.
LANGUAGES = ["tr", "en"]

# Bu eşiğin altındaki okumalar atılıyor. OCR düşük güvenli sonuçlarda
# gerçekte olmayan kelimeler uyduruyor; yanlış metin, metin olmamasından kötü.
MIN_CONFIDENCE = 0.35

# Aynı karede en fazla kaç satır döndürülür. Yoğun bir ekran/sayfa yüzlerce
# parça üretebiliyor; ne arayüz ne de sesli okuma bunu taşır.
MAX_LINES = 40

# İki parçanın "aynı satırda" sayılması için dikey merkezlerinin en fazla ne
# kadar ayrışabileceği — satır yüksekliğinin oranı olarak.
ROW_TOLERANCE = 0.6



def _sort_reading_order(lines: list[dict]) -> list[dict]:
    """Parçaları insan okuma sırasına dizer: satır satır yukarıdan aşağı,
    her satırın içinde soldan sağa.

    NEDEN DÜZ (y, x) SIRALAMASI YETMİYOR: EasyOCR aynı görsel satırdaki
    kelimeleri ayrı parçalar olarak döndürüyor ve bunların üst kenarları birkaç
    piksel oynuyor. Ham y'ye göre sıralayınca "çilek şeftali üzüm" → "şeftali
    çilek üzüm" oluyordu; metin sesli okunduğu ve kopyalanabildiği için bu
    gerçek bir hata. Önce parçalar satırlara kümeleniyor, sonra her satır kendi
    içinde x'e göre sıralanıyor.
    """
    if not lines:
        return []

    def center_y(line: dict) -> float:
        return (line["box"][1] + line["box"][3]) / 2.0

    rows: list[dict] = []
    for line in sorted(lines, key=center_y):
        height = max(line["box"][3] - line["box"][1], 1e-6)
        placed = False
        for row in rows:
            if abs(center_y(line) - row["center"]) <= max(height, row["height"]) * ROW_TOLERANCE:
                row["items"].append(line)
                row["center"] = sum(center_y(item) for item in row["items"]) / len(row["items"])
                row["height"] = max(row["height"], height)
                placed = True
                break
        if not placed:
            rows.append({"center": center_y(line), "height": height, "items": [line]})

    ordered: list[dict] = []
    for row in rows:
        ordered.extend(sorted(row["items"], key=lambda item: item["box"][0]))
    return ordered


def _load_reader():
    """EasyOCR okuyucusu — ağır; kullanınca kurulur."""
    import easyocr

    # gpu=False: projedeki torch CPU sürümü (2.13.0+cpu). True verilirse
    # EasyOCR her çağrıda bir uyarı basıp yine CPU'ya düşüyor.
    return easyocr.Reader(LANGUAGES, gpu=False, verbose=False)


# Kullanınca yüklenir, 2 dk kullanılmazsa bellekten çıkar (Faz 0, 2026-10-02).
# Bkz. core/idle_model.py.
_reader = IdleModel("EasyOCR", _load_reader, idle_seconds=120)


def read_text_in_jpeg(jpeg_bytes: bytes) -> list[dict]:
    """JPEG bayt verisindeki metni okur.

    [{"text", "confidence", "box"}] listesi döner; `box` NORMALİZE
    [x1, y1, x2, y2] (0..1). Nesne tanımayla (object_recognition.py) AYNI kutu
    sözleşmesi — Vision paneli iki sonucu da aynı çizim koduyla gösterebilsin diye.

    EasyOCR dört köşe (dönmüş olabilir) döndürüyor; burada eksene hizalı sınır
    kutusuna indirgeniyor: arayüzde kutular CSS ile çiziliyor, dönmüş dörtgen
    çizmek için canvas gerekirdi ve okunabilirliğe katkısı olmazdı.

    Bu fonksiyon ASLA exception fırlatmaz — çağıran taraf her zaman bir liste alır.
    """
    if not HAS_EASYOCR or not HAS_PIL:
        return []

    try:
        image = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
        width, height = image.size
        if width <= 0 or height <= 0:
            return []

        import numpy as np

        with _reader.use() as reader:
            results = reader.readtext(np.array(image))
    except Exception:
        logger.debug("[OCR] Metin okunamadı", exc_info=True)
        return []

    lines: list[dict] = []
    try:
        for corners, text, confidence in results:
            cleaned = str(text or "").strip()
            if not cleaned or float(confidence) < MIN_CONFIDENCE:
                continue

            xs = [float(point[0]) for point in corners]
            ys = [float(point[1]) for point in corners]
            lines.append(
                {
                    "text": cleaned,
                    "confidence": round(float(confidence), 2),
                    "box": [
                        round(min(xs) / width, 4),
                        round(min(ys) / height, 4),
                        round(max(xs) / width, 4),
                        round(max(ys) / height, 4),
                    ],
                }
            )
    except Exception:
        logger.debug("[OCR] Sonuç ayrıştırılamadı", exc_info=True)
        return []

    return _sort_reading_order(lines)[:MAX_LINES]


def lines_to_text(lines: list[dict]) -> str:
    """Okunan satırları tek bir metne birleştirir (sesli cevap ve araç sonucu için)."""
    return " ".join(line["text"] for line in lines).strip()
