"""
Nesne tanıma (YAPILACAKLAR.md #2) — YOLO-World (yerel, açık kelime dağarcıklı,
gerçek zamanlı nesne tespiti) + Gemini vision (kullanıcının öğrettiği özel
nesneler için zengin açıklama üretme).

YOLO-World gerçek anlamda "yeniden eğitilen" bir model değil — dağarcığı
(vocabulary) çalışma anında metinle genişletilebiliyor, yeniden eğitim
gerektirmiyor. "Öğrenme" burada memory.json üzerinden yapılıyor: kullanıcı bir
nesneyi isimlendirdiğinde (learn_object, main.py'de), Gemini vision'dan zengin
bir açıklama alınıp hafızaya kaydediliyor; sonraki recognize_objects
çağrılarında bu özel isimler de YOLO-World'ün dağarcığına eklenip aranıyor.

Model ağır olduğu için (yükleme birkaç saniye sürüyor) modül seviyesinde tek
seferlik (lazy singleton) yükleniyor — her çağrıda yeniden yüklenmiyor.
"""

from __future__ import annotations

import importlib.util
import io

from google import genai
from google.genai import types

from core.idle_model import IdleModel

# DİKKAT — ultralytics BURADA import EDİLMEZ (2026-07-29 bellek ölçümü):
# `from ultralytics import YOLOWorld` modül seviyesindeyken torch + ultralytics +
# matplotlib zinciri açılışta yükleniyordu ve tek başına **273 MB** tutuyordu.
# main.py bu modülü araç kaydı için her açılışta import ettiğinden, kullanıcı
# nesne tanımayı hiç çalıştırmasa bile bu bedel ödeniyordu.
#
# Paketin KURULU OLUP OLMADIĞINI öğrenmek için import etmek gerekmiyor:
# find_spec sadece dosya sisteminde arar, modülü çalıştırmaz (mikrosaniyeler).
# Gerçek import ilk tespit çağrısında, _load_model içinde yapılıyor.
HAS_ULTRALYTICS = importlib.util.find_spec("ultralytics") is not None

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


YOLO_WORLD_MODEL = "yolov8s-worldv2.pt"
DETECTION_CONFIDENCE = 0.15

# Varsayılan geniş dağarcık — ev/ofis/kişisel eşyalar. YOLO-World'ün metin
# tabanlı (CLIP) sınıflandırıcısı İngilizce kavramlarla daha güvenilir çalışıyor;
# görüntüleme sırasında Türkçeye çevriliyor (bkz. _DISPLAY_NAMES).
DEFAULT_VOCABULARY = [
    "person", "face", "hand",
    "coffee mug", "cup", "glass", "bottle", "water bottle",
    "phone", "smartphone", "laptop", "keyboard", "mouse", "monitor", "headphones",
    "earbuds", "charger", "cable", "power bank",
    "book", "notebook", "pen", "pencil", "paper", "sticky note",
    "wallet", "keys", "watch", "glasses", "sunglasses",
    "bag", "backpack",
    "chair", "table", "desk", "lamp", "clock",
    "can", "food", "fruit", "snack",
    "remote control", "speaker", "microphone", "camera",
    "plant", "mug",
    "pillow", "blanket", "shoe", "jacket", "hat",
    "medicine bottle", "toothbrush",
]

_DISPLAY_NAMES = {
    "person": "insan", "face": "yüz", "hand": "el",
    "coffee mug": "kahve fincanı", "cup": "bardak/fincan", "glass": "bardak",
    "bottle": "şişe", "water bottle": "su şişesi",
    "phone": "telefon", "smartphone": "telefon", "laptop": "dizüstü bilgisayar",
    "keyboard": "klavye", "mouse": "fare", "monitor": "monitör",
    "headphones": "kulaklık", "earbuds": "kulaklık", "charger": "şarj aleti",
    "cable": "kablo", "power bank": "powerbank",
    "book": "kitap", "notebook": "defter", "pen": "kalem", "pencil": "kurşun kalem",
    "paper": "kağıt", "sticky note": "yapışkanlı not",
    "wallet": "cüzdan", "keys": "anahtar", "watch": "saat",
    "glasses": "gözlük", "sunglasses": "güneş gözlüğü",
    "bag": "çanta", "backpack": "sırt çantası",
    "chair": "sandalye", "table": "masa", "desk": "masa", "lamp": "lamba", "clock": "saat",
    "can": "kutu/teneke", "food": "yiyecek", "fruit": "meyve", "snack": "atıştırmalık",
    "remote control": "kumanda", "speaker": "hoparlör", "microphone": "mikrofon",
    "camera": "kamera", "plant": "bitki",
    "mug": "kupa", "pillow": "yastık", "blanket": "battaniye",
    "shoe": "ayakkabı", "jacket": "ceket", "hat": "şapka",
    "medicine bottle": "ilaç şişesi", "toothbrush": "diş fırçası",
}


def display_name(label: str) -> str:
    return _DISPLAY_NAMES.get(label, label)


def _load_model():
    # Ağır zincir (torch/ultralytics/matplotlib, ~273 MB) ilk gerçek tespit
    # çağrısına kadar ertelenir — bkz. yukarıdaki HAS_ULTRALYTICS notu.
    from ultralytics import YOLOWorld

    return YOLOWorld(YOLO_WORLD_MODEL)


# Kullanınca yüklenir, 2 dk kullanılmazsa bellekten çıkar (Faz 0, 2026-10-02 —
# kullanıcı: "çalıştırdığımda çalışsın, yoksa çalışmasın"). Bkz. core/idle_model.py.
_model = IdleModel("YOLO-World", _load_model, idle_seconds=120)


def _apply_vocabulary(model, vocabulary: list[str]) -> None:
    # Dağarcık modele bağlı durum: model bırakılıp yeniden yüklenince sıfırlanır,
    # bu yüzden global değil modelin üstünde tutuluyor.
    if getattr(model, "_chiron_vocabulary", None) != vocabulary:
        model.set_classes(vocabulary)
        model._chiron_vocabulary = list(vocabulary)


def detect_objects_in_jpeg(jpeg_bytes: bytes, extra_vocabulary: list[str] | None = None) -> list[dict]:
    """JPEG bayt verisinde nesne tespiti yapar.

    [{"label", "display_name", "confidence", "box"}] listesi döner; aynı etiketten
    yalnızca en yüksek güvenli olan tutulur, güvene göre azalan sırada.

    `box` — NORMALİZE [x1, y1, x2, y2] (0..1). Normalize olması bilinçli: arayüz
    kareyi kendi kart genişliğinde ölçekleyerek gösteriyor (bkz.
    frontend/components/VisionPanel.tsx), piksel koordinatı orada işe yaramazdı.
    2026-07-30'da eklendi — o güne kadar yalnızca etiket dönüyordu ve arayüzde
    çerçeve çizmek mümkün değildi.

    Ultralytics/PIL kurulu değilse veya bir hata olursa boş liste döner — bu
    fonksiyon asla exception fırlatmaz, çağıran taraf her zaman bir liste alır."""
    if not HAS_ULTRALYTICS or not HAS_PIL:
        return []

    vocabulary = list(DEFAULT_VOCABULARY)
    for extra in (extra_vocabulary or []):
        if extra and extra not in vocabulary:
            vocabulary.append(extra)

    try:
        image = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
        with _model.use() as model:
            _apply_vocabulary(model, vocabulary)
            results = model.predict(image, conf=DETECTION_CONFIDENCE, verbose=False)
            names = model.names
    except Exception:
        return []

    # Etiket başına en iyi tespit: (güven, normalize kutu)
    best_by_label: dict[str, tuple[float, list[float]]] = {}
    try:
        r = results[0]
        for box in r.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            label = names.get(cls_id, str(cls_id)) if isinstance(names, dict) else names[cls_id]
            if conf <= best_by_label.get(label, (0.0, []))[0]:
                continue
            # xyxyn: ultralytics'in kendi verdiği normalize köşe koordinatları —
            # görüntü boyutunu burada ayrıca bilmek gerekmiyor.
            corners = [round(float(value), 4) for value in box.xyxyn[0].tolist()]
            best_by_label[label] = (conf, corners)
    except Exception:
        return []

    detections = [
        {
            "label": label,
            "display_name": display_name(label),
            "confidence": round(conf, 2),
            "box": corners,
        }
        for label, (conf, corners) in best_by_label.items()
    ]
    detections.sort(key=lambda d: d["confidence"], reverse=True)
    return detections


def describe_object_for_learning(api_key: str, jpeg_bytes: bytes, name: str) -> str:
    """Gemini vision'a webcam karesindeki nesneyi (kullanıcının `name` ile
    isimlendirdiği) betimletir — sonuç memory.json'a kaydedilecek zengin bir
    açıklama metnidir. Hata olursa boş string döner."""
    if not api_key:
        return ""
    try:
        client = genai.Client(api_key=api_key)
        prompt = (
            f"Kullanıcı kameradaki bir nesneyi '{name}' olarak adlandırdı. Bu nesneyi "
            "rengi, şekli, boyutu, malzemesi ve ayırt edici özellikleriyle 1-2 cümlede "
            "Türkçe olarak betimle — bu açıklama ileride aynı nesneyi tekrar tanımak "
            "için kullanılacak. SADECE betimlemeyi yaz, başka bir şey ekleme."
        )
        image_part = types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")
        for model_name in ("models/gemini-flash-latest", "models/gemini-2.5-flash-lite"):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[types.Part.from_text(text=prompt), image_part],
                    config=types.GenerateContentConfig(temperature=0.3),
                )
                text = str(getattr(response, "text", "") or "").strip()
                if text:
                    return text
            except Exception:
                continue
        return ""
    except Exception:
        return ""
