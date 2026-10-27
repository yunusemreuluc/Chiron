"""
Genel "izle, değişince haber ver" aracı (YAPILACAKLAR.md #7).

`intervene_screen`'deki önce/sonra ekran karşılaştırma mantığının genelleştirilmiş
hali — kullanıcı belirli bir şeyi (bir pencere, bir ilerleme çubuğu, bir buton) ve
beklediği bir durumu tarif eder ("indirme yüzde 100 olunca haber ver"), main.py'nin
arka plan görevi (_watch_custom_conditions) bunu periyodik olarak Gemini vision'a
sorup gerçekleşince kullanıcıya proaktif haber verir.

Bu bir "tool" değil (Gemini tarafından çağrılmaz) — main.py'deki start_watch/
stop_watch araçları kullanıcı isteğini kaydeder, bu modül sadece "gerçekleşti mi"
kontrolünü yapar. screen_monitor.py/screen_control.py ile aynı desenler (mss capture
+ Gemini vision + model fallback) — proje genelinde kabul edilmiş şekilde kasıtlı
olarak ortak modüle çıkarılmadı.
"""

from __future__ import annotations

import ctypes
import json
import re
import tempfile
from pathlib import Path

from google import genai
from google.genai import types

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


WATCH_MODELS = (
    "models/gemini-flash-latest",
    "models/gemini-2.5-flash-lite",
)
WATCH_MAX_DIMENSION = 1200


def get_active_window_title() -> str:
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value.strip()
    except Exception:
        return ""


def _capture_active_window() -> Path | None:
    if not HAS_MSS or not HAS_PIL:
        return None
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            shot = sct.grab(monitor)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        if max(img.size) > WATCH_MAX_DIMENSION:
            img.thumbnail((WATCH_MAX_DIMENSION, WATCH_MAX_DIMENSION), Image.Resampling.LANCZOS)
        handle = tempfile.NamedTemporaryFile(prefix="chiron-watch-", suffix=".png", delete=False)
        tmp_path = Path(handle.name)
        handle.close()
        img.save(str(tmp_path), format="PNG", optimize=True)
        return tmp_path
    except Exception:
        return None


def _extract_json(text: str) -> dict | None:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return None
    return None


def _watch_prompt(instruction: str, condition: str, window_title: str) -> str:
    label = window_title or "aktif pencere"
    return (
        "Sen kullanıcı adına ekranı arka planda izleyen bir gözlemcisin. Kullanıcı "
        f"şunu izlemeni istedi: \"{instruction}\" (şu an ekranda: '{label}'). "
        f"Beklediği/haber verilmesini istediği durum: \"{condition}\".\n\n"
        "Bu ekran görüntüsüne bakarak bu durumun ŞU AN GERÇEKLEŞMİŞ olup olmadığını "
        "değerlendir. Emin değilsen veya izlenecek şey ekranda hiç görünmüyorsa "
        "condition_met:false yap — yanlış pozitif, kullanıcıyı gereksiz yere rahatsız eder.\n\n"
        "SADECE aşağıdaki JSON formatında yanıt ver, başka hiçbir metin veya markdown "
        "ekleme:\n"
        '{"condition_met": true veya false, "detail": "kısa Türkçe açıklama"}'
    )


def check_watch_condition(api_key: str, instruction: str, condition: str, window_title: str) -> dict:
    """{"condition_met": bool, "detail": str} döner. Teknik bir sorun olursa
    (API/anahtar/yakalama hatası) sessizce condition_met=False ile geçer — bu
    fonksiyon kullanıcıyla ASLA doğrudan konuşmaz, main.py'ye sinyal verir."""
    if not api_key:
        return {"condition_met": False, "detail": ""}

    image_path = _capture_active_window()
    if image_path is None:
        return {"condition_met": False, "detail": ""}

    try:
        image_part = types.Part.from_bytes(data=image_path.read_bytes(), mime_type="image/png")
        client = genai.Client(api_key=api_key)
        prompt = _watch_prompt(instruction, condition, window_title)
        for model_name in WATCH_MODELS:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[types.Part.from_text(text=prompt), image_part],
                    config=types.GenerateContentConfig(temperature=0.1),
                )
                parsed = _extract_json(str(getattr(response, "text", "") or ""))
                if parsed is not None:
                    return {
                        "condition_met": bool(parsed.get("condition_met")),
                        "detail": str(parsed.get("detail") or "").strip(),
                    }
            except Exception:
                continue
        return {"condition_met": False, "detail": ""}
    except Exception:
        return {"condition_met": False, "detail": ""}
    finally:
        try:
            image_path.unlink()
        except Exception:
            pass
