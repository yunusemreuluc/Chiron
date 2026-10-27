"""
Proaktif ekran izleme (YAPILACAKLAR.md #4) — arka planda periyodik olarak aktif
pencereyi yakalayıp Gemini vision'a "kullanıcının dikkatini gerektiren açık bir
sorun (hata/uyarı penceresi vb.) var mı" diye sorar.

Bu bir "tool" DEĞİL — tool_defs.py'de yok, Gemini tarafından çağrılmaz. main.py'nin
kendi arka plan görevi (ChironLive._watch_screen_for_issues) bunu periyodik çağırıp
sonucu proaktif bir konuşma tetikleyicisine çevirir (bkz. main.py).

screen_vision.py/screen_control.py ile aynı desenler (mss capture + Gemini vision +
model fallback) — proje genelinde kabul edilmiş şekilde kasıtlı olarak ortak modüle
çıkarılmadı (bkz. o dosyalardaki aynı not).
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


# "gemini-2.5-flash" BİLEREK yok — bu hesapta 404 veriyor (bkz. screen_control.py'deki not).
MONITOR_MODELS = (
    "models/gemini-flash-latest",
    "models/gemini-2.5-flash-lite",
)
MONITOR_MAX_DIMENSION = 1200  # sadece "sorun var mı" tespiti — analyze_screen'den küçük

# ── Değişim kapısı (2026-08-01) ─────────────────────────────────────────────
# Bekçi 25 sn'de bir Gemini'ye görü çağrısı atıyordu: saatte 144, günde 3456.
# Gemini ÜCRETSİZ katmanı günde 1500 istek veriyor — yani Chiron ~10 saat açık
# kalınca kota, kullanıcı tek kelime etmeden bitiyordu. Kasadaki "test ederken
# kota dolmuştu" notlarının (gemini_desktop_task, search_files, activity_log)
# gerçek sebebi test edilen araç değil, arka planda dönen bu bekçiydi.
#
# Çözümün özü: EKRAN DEĞİŞMEDİYSE SORMA. Aynı piksellere ikinci kez bakmanın
# bilgi değeri sıfır; kullanıcı bir belgeyi 10 dakika okurken 24 çağrı boşa
# gidiyordu.
#
# Karşılaştırma TAM EŞLEŞME DEĞİL: gerçek ekranlarda saat saniyesi, imleç
# yanıp sönmesi, ufak animasyonlar sürekli birkaç piksel oynatıyor. Tam karma
# kullanılsaydı kapı hiç kapanmaz, hiçbir tasarruf olmazdı. Bunun yerine
# görüntü küçük bir gri tonlamalı küçük resme indirgenip ORTALAMA MUTLAK FARK
# ölçülüyor — saat rakamı toplamda gürültü kalır, açılan bir hata diyaloğu
# eşiği rahatça geçer.
_DIFF_SIZE = (96, 96)

# ÖLÇÜM VARSAYIMI ÇÜRÜTTÜ (2026-08-01). "Ekran sabitken fark küçüktür"
# sanılıyordu; gerçek masaüstünde ardışık farklar 4.5 / 22 / 55 / 71 ölçüldü —
# %30'luk bir hata diyaloğunun açılmasından (13.6) bile büyük. Sebep: ekranda
# video/animasyon olabiliyor ve yakalama tüm monitörü alıyor.
#
# Sonuç: karma kapısı TEK BAŞINA yeterli DEĞİL. Video oynarken hiç kapanmaz.
# Bu yüzden mimari üç katmanlı:
#   1. Boşta kapısı  — kullanıcı masada değilse hiç bakma (en büyük tasarruf)
#   2. Değişim kapısı — ekran duruyorsa sorma (okuma/yazma sırasında etkili)
#   3. Saatlik tavan  — 1 ve 2 işe yaramasa bile kotayı GARANTİ eder (main.py)
#
# Eşik ölçülen diyalog farklarına göre seçildi: %12'lik bir diyalog 1.38,
# %20'lik 5.0 fark üretiyor. 1.0 küçük diyalogları bile yakalar. Yakalayamadığı
# %6'lık bildirimler (0.18) zaten "kullanıcının fark etmesi gereken açık bir
# durum" tanımına girmiyor.
DEFAULT_CHANGE_THRESHOLD = 1.0
_previous_signature: list[int] | None = None


def _signature(image_path: Path) -> list[int] | None:
    """Görüntünün küçük gri tonlamalı imzası — karşılaştırma için."""
    if not HAS_PIL:
        return None
    try:
        with Image.open(image_path) as img:
            small = img.convert("L").resize(_DIFF_SIZE, Image.Resampling.BILINEAR)
            return list(small.getdata())
    except Exception:
        return None


def screen_difference(image_path: Path) -> float | None:
    """Bir öncekine göre ortalama mutlak fark (0-255). İlk çağrıda None.

    Yan etkili: her çağrıda referansı günceller. Referansın DEĞİŞMEDİĞİNDE de
    güncellenmesi kasıtlı — böylece yavaş kayma (ör. kademeli soluklaşan bir
    animasyon) sonsuza kadar birikip sahte bir "değişti" üretmiyor.
    """
    global _previous_signature
    imza = _signature(image_path)
    if imza is None:
        return None
    onceki, _previous_signature = _previous_signature, imza
    if onceki is None or len(onceki) != len(imza):
        return None
    return sum(abs(a - b) for a, b in zip(imza, onceki)) / len(imza)


def reset_change_tracking() -> None:
    """Referansı unut — bir sonraki kontrol kesin çalışsın.

    Duraklatma/susturma sonrası kullanılıyor: o aralıkta ekran değişmiş
    olabilir ama biz bakmadık, dolayısıyla elimizdeki referans bayat.
    """
    global _previous_signature
    _previous_signature = None


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
        if max(img.size) > MONITOR_MAX_DIMENSION:
            img.thumbnail((MONITOR_MAX_DIMENSION, MONITOR_MAX_DIMENSION), Image.Resampling.LANCZOS)
        handle = tempfile.NamedTemporaryFile(prefix="chiron-monitor-", suffix=".png", delete=False)
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


def _check_prompt(window_title: str) -> str:
    label = window_title or "aktif pencere"
    return (
        "Sen arka planda SESSİZCE çalışan bir ekran izleyicisin — kullanıcı sana "
        "hiçbir şey sormadı. Aşağıdaki ekran görüntüsü şu pencereye ait: "
        f"'{label}'.\n\n"
        "SADECE kullanıcının GERÇEKTEN fark etmesi gereken açık bir durum varsa "
        "(hata mesajı diyaloğu, çökme/crash ekranı, kritik güvenlik uyarısı, "
        "programın yanıt vermediğini gösteren bir uyarı vb.) issue_found:true yap. "
        "Sıradan/normal her şeyi (yükleniyor ekranı, boş sayfa, sıradan içerik, "
        "küçük bilgi ikonları, normal bildirimler) ASLA sorun olarak işaretleme — "
        "ÇOK TUTUCU ol; sık yanlış alarm kullanıcıyı yorar ve güvenini kırar. "
        "Emin değilsen issue_found:false yap.\n\n"
        "issue_found:true ise, description alanına SADECE kısa bir özet değil, "
        "ekranda görünen TAM hata metnini/kodunu/mesajını (varsa) birebir de ekle — "
        "bu bilgi daha sonra çözüm önermek için kullanılacak.\n\n"
        "SADECE aşağıdaki JSON formatında yanıt ver, başka hiçbir metin veya markdown "
        "ekleme:\n"
        '{"issue_found": true veya false, "description": "kısa Türkçe özet + varsa tam hata metni/kodu"}'
    )


def check_for_issue(
    api_key: str,
    window_title: str,
    change_threshold: float = DEFAULT_CHANGE_THRESHOLD,
) -> dict:
    """{"issue_found": bool, "description": str, "skipped": str} döner.

    Teknik bir sorun olursa (API/anahtar/yakalama hatası) sessizce
    issue_found=False ile geçer — bu fonksiyon kullanıcıyla ASLA doğrudan
    konuşmaz, main.py'ye sinyal verir.

    `skipped` alanı Gemini'ye HİÇ gidilmediğini söyler ("unchanged"). Bu bir
    hata değil, tasarruf; çağıran taraf bunu kota günlüğü için okuyabilir.
    Ekran yakalama yerel ve ucuz (~30 ms), pahalı olan görü çağrısı — o yüzden
    kapı yakalamadan SONRA, çağrıdan ÖNCE.
    """
    if not api_key:
        return {"issue_found": False, "description": "", "skipped": "no_key"}

    image_path = _capture_active_window()
    if image_path is None:
        return {"issue_found": False, "description": "", "skipped": "capture_failed"}

    fark = screen_difference(image_path)
    if fark is not None and fark < change_threshold:
        try:
            image_path.unlink()
        except Exception:
            pass
        return {"issue_found": False, "description": "", "skipped": "unchanged"}

    try:
        image_part = types.Part.from_bytes(data=image_path.read_bytes(), mime_type="image/png")
        client = genai.Client(api_key=api_key)
        prompt = _check_prompt(window_title)
        for model_name in MONITOR_MODELS:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[types.Part.from_text(text=prompt), image_part],
                    config=types.GenerateContentConfig(temperature=0.1),
                )
                parsed = _extract_json(str(getattr(response, "text", "") or ""))
                if parsed is not None:
                    # skipped="" — Gemini GERÇEKTEN çağrıldı. Kota günlüğünde
                    # "baktım, bir şey yok" ile "hiç bakmadım" ayrılabilsin.
                    return {
                        "issue_found": bool(parsed.get("issue_found")),
                        "description": str(parsed.get("description") or "").strip(),
                        "skipped": "",
                    }
            except Exception:
                continue
        return {"issue_found": False, "description": "", "skipped": ""}
    except Exception:
        return {"issue_found": False, "description": "", "skipped": ""}
    finally:
        try:
            image_path.unlink()
        except Exception:
            pass
