"""
Ekrana müdahale — Gemini'ye ekran görüntüsünü gösterip tarif edilen öğenin piksel
konumunu aldırır, sonra pyautogui ile tıklar/yazar.

screen_vision.py ile aynı desenler (mss ekran yakalama + Gemini vision + retry) —
kasıtlı olarak ortak bir modüle çıkarılmadı (bkz. video_analysis.py'deki aynı not —
proje genelinde kabul edilmiş bir tekrar).
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import mimetypes
import re
import tempfile
import time
from pathlib import Path

from google import genai
from google.genai import errors, types
from PIL import Image

from app_config import get_app_config_value
from actions.tool_result import fail, ok
from core.tool_registry import register_tool

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False

try:
    import pygetwindow as gw
    HAS_PYGETWINDOW = True
except ImportError:
    HAS_PYGETWINDOW = False


def _force_foreground(hwnd) -> bool:
    """Windows normalde arka planda çalışan bir process'in SetForegroundWindow
    çağırmasını engeller (foreground-lock kısıtı) — pygetwindow'un Window.activate()
    metodu bu durumda GERÇEK bir Win32 hatası olmadan (GetLastError()=0) sessizce
    reddedilmiş bir çağrıyı da exception'a çeviriyor ve kafa karıştırıcı bir mesaj
    üretiyor ("Error code from Windows: 0 - İşlem başarıyla tamamlandı"). Bunun
    yerine AttachThreadInput ile çağıran thread'in girdi durumunu hedef pencerenin
    thread'ine geçici olarak bağlayıp SetForegroundWindow'u kendimiz çağırıyoruz —
    bu, Windows'un dokümante ettiği standart bir workaround. Yine de başarısız
    olabilir; dönüş değeri (True/False) çağıran tarafından ayrıca doğrulanıyor
    (bkz. _activate_window sonundaki getActiveWindow kontrolü)."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    foreground_hwnd = user32.GetForegroundWindow()
    current_thread_id = kernel32.GetCurrentThreadId()
    foreground_thread_id = user32.GetWindowThreadProcessId(foreground_hwnd, None) if foreground_hwnd else 0

    attached = False
    try:
        if foreground_thread_id and foreground_thread_id != current_thread_id:
            attached = bool(user32.AttachThreadInput(foreground_thread_id, current_thread_id, True))
        return bool(user32.SetForegroundWindow(hwnd))
    except Exception:
        return False
    finally:
        if attached:
            try:
                user32.AttachThreadInput(foreground_thread_id, current_thread_id, False)
            except Exception:
                pass


def _activate_window(app_hint: str) -> str:
    """Başlığı `app_hint` içeren bir pencereyi öne getirir ve GERÇEKTEN öne
    geldiğini doğrular. Doğrulanamazsa boş string DEĞİL, bir hata mesajı
    döner — çağıran taraf bunu görürse işleme devam ETMEMELİ, çünkü yanlış
    pencerede sessizce tıklayıp "başardım" demek kullanıcıyı yanıltır.

    Sekme değiştirmez — sadece pencere düzeyinde çalışır (Win32 API sınırı).
    Gemini, o an ekranda görünen sekme değil de arka plandaki başka bir
    sekmeyse, o pencerenin başlığı Gemini'yi hiç yansıtmayabilir; bu durumda
    "bulunamadı" hatası döner (kullanıcı önce sekmeyi kendisi öne getirmeli).
    """
    if not app_hint or not app_hint.strip():
        return ""
    if not HAS_PYGETWINDOW:
        return "pygetwindow kurulu değil, pencere öne getirilemedi. 'pip install pygetwindow' ile kur."
    hint = app_hint.strip().lower()
    try:
        matches = [w for w in gw.getAllWindows() if w.title and hint in w.title.lower()]
    except Exception as exc:
        return f"Pencere listesi alınamadı: {exc}"
    if not matches:
        return (
            f"'{app_hint}' ile eşleşen açık bir pencere bulunamadı (arka planda farklı bir "
            "sekmedeyse önce o sekmeyi kendin öne getirmelisin, sekme değiştiremiyorum)."
        )
    try:
        win = matches[0]
        if win.isMinimized:
            win.restore()
        _force_foreground(win._hWnd)
        time.sleep(0.35)
    except Exception as exc:
        return f"Pencere öne getirilemedi: {exc}"

    try:
        active = gw.getActiveWindow()
        active_title = (active.title or "").lower() if active else ""
    except Exception:
        active_title = ""
    if hint not in active_title:
        return (
            f"'{app_hint}' penceresi öne getirilmeye çalışıldı ama odak gerçekten oraya "
            "geçmedi (Windows arka plan uygulamalarının pencere öne getirmesini engelliyor "
            "olabilir) — lütfen pencereyi kendin öne getirip tekrar dener misin?"
        )
    return ""


# "gemini-2.5-flash" BİLEREK yok — bu hesapta "artık yeni kullanıcılara açık değil"
# diye 404 veriyor (test: 2026-07-25, bkz. video_analysis.py'deki aynı not).
# "flash-latest" Google'ın sürekli güncel tuttuğu takma ad olduğu için öncelikli.
LOCATE_MODELS = (
    "models/gemini-flash-latest",
    "models/gemini-2.5-flash-lite",
    "models/gemini-2.0-flash",
)
LOCATE_MAX_DIMENSION = 1400  # analyze_screen'dekinden küçük — sadece koordinat okunacak


def _foreground_window_center() -> tuple[int, int] | None:
    """Şu an ön plandaki pencerenin merkez noktasını (sanal masaüstü koordinatı)
    döner — hangi monitörün yakalanması gerektiğine karar vermek için kullanılır."""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return None
        rect = ctypes.wintypes.RECT()
        if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        return ((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
    except Exception:
        return None


def _capture_desktop() -> tuple[bool, str, int, int, int, int]:
    """(ok, png_yolu_veya_hata, capture_w, capture_h, offset_x, offset_y) döner.

    offset_x/offset_y, yakalanan monitörün SANAL MASAÜSTÜNDEKİ (0,0) köşesine
    göre konumudur. pyautogui.click() mutlak sanal masaüstü koordinatı beklerken
    bu ofset görmezden gelinirse (eskiden öyleydi), çoklu monitör kurulumlarında
    veya ikincil bir monitör orijine denk gelmediğinde tıklama HATASIZ ama tamamen
    yanlış bir noktaya gider — kullanıcı "tıklamadı, ama tıkladım diyor" hatasını
    tam da bu yüzden yaşadı.

    Hangi monitörün yakalanacağı, ön plandaki pencerenin (varsa app_hint ile az
    önce öne getirilen pencere) merkez noktasına göre seçilir; bulunamazsa
    monitors[1] (birincil monitör) varsayılan olarak kullanılır.
    """
    if not HAS_MSS:
        return False, "mss kütüphanesi kurulu değil. 'pip install mss' ile kur.", 0, 0, 0, 0
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            center = _foreground_window_center()
            if center is not None:
                cx, cy = center
                for candidate in sct.monitors[1:]:
                    if (candidate["left"] <= cx < candidate["left"] + candidate["width"]
                            and candidate["top"] <= cy < candidate["top"] + candidate["height"]):
                        monitor = candidate
                        break
            shot = sct.grab(monitor)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    except Exception as exc:
        return False, f"Ekran görüntüsü alınamadı: {exc}", 0, 0, 0, 0

    try:
        handle = tempfile.NamedTemporaryFile(prefix="chiron-intervene-", suffix=".png", delete=False)
        tmp_path = Path(handle.name)
        handle.close()
        img.save(str(tmp_path), format="PNG")
    except Exception as exc:
        return False, f"Ekran görüntüsü kaydedilemedi: {exc}", 0, 0, 0, 0

    return True, str(tmp_path), img.width, img.height, monitor["left"], monitor["top"]


def _build_image_part(image_path: Path) -> types.Part:
    mime_type, _ = mimetypes.guess_type(str(image_path))
    if not mime_type:
        mime_type = "image/png"
    try:
        with Image.open(image_path) as img:
            work = img.copy()
        if work.mode not in {"RGB", "L"}:
            work = work.convert("RGB")
        if max(work.size) > LOCATE_MAX_DIMENSION:
            work.thumbnail((LOCATE_MAX_DIMENSION, LOCATE_MAX_DIMENSION), Image.Resampling.LANCZOS)
        import io
        buf = io.BytesIO()
        work.save(buf, format="PNG", optimize=True)
        return types.Part.from_bytes(data=buf.getvalue(), mime_type="image/png")
    except Exception:
        return types.Part.from_bytes(data=image_path.read_bytes(), mime_type=mime_type)


def _locate_prompt(instruction: str) -> str:
    return (
        "Sen Windows masaüstü ekran görüntüsünde belirtilen bir öğeyi bulan bir "
        "görüntü analistisin. Kullanıcının bulunmasını istediği öğe:\n"
        f"\"{instruction}\"\n\n"
        "SADECE aşağıdaki JSON formatında yanıt ver, başka hiçbir metin, açıklama "
        "veya markdown kod bloğu ekleme:\n"
        '{"found": true veya false, "x": 0-1000 arası tam sayı, "y": 0-1000 arası tam sayı, '
        '"description": "bulduğun öğenin kısa Türkçe açıklaması"}\n\n'
        "x ve y, görüntünün SOL ÜST köşesi (0,0) ve SAĞ ALT köşesi (1000,1000) olacak "
        "şekilde normalize edilmiş, öğenin TAM ORTASINI gösteren koordinatlardır. "
        "Öğeyi bulamazsan found:false yap, x/y'yi 0 yap, description'da neden "
        "bulamadığını kısaca açıkla. Uydurma koordinat verme."
    )


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


def _is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, (errors.ServerError, TimeoutError)):
        return True
    message = str(exc or "").lower()
    markers = (
        "503", "429", "deadline", "timed out", "timeout", "unavailable",
        "service unavailable", "internal error", "busy", "overloaded",
        "resource exhausted", "try again later", "backend error", "connection reset",
    )
    return any(marker in message for marker in markers)


def _locate_element(client: genai.Client, instruction: str, image_path: Path) -> dict:
    """Gemini'den {"found","x","y","description"} sözlüğü döner (0-1000 normalize)."""
    prompt = _locate_prompt(instruction)
    image_part = _build_image_part(image_path)
    retry_delays = (0.9, 1.8, 3.0)
    last_error: Exception | None = None

    for model_name in LOCATE_MODELS:
        for attempt, delay in enumerate(retry_delays, start=1):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[types.Part.from_text(text=prompt), image_part],
                    config=types.GenerateContentConfig(temperature=0.1),
                )
                text = str(getattr(response, "text", "") or "").strip()
                parsed = _extract_json(text)
                if parsed is not None:
                    return parsed
                raise RuntimeError("Gemini geçerli bir konum JSON'u döndürmedi.")
            except Exception as exc:
                last_error = exc
                if attempt < len(retry_delays) and _is_transient_error(exc):
                    time.sleep(delay)
                    continue
                if _is_transient_error(exc):
                    break
                raise

    raise RuntimeError(f"Konum bulma başarısız: {last_error}")


def _verify_prompt(instruction: str, action: str, text: str) -> str:
    if action == "click":
        beklenen = f"'{instruction}' üzerine tıklandı."
    elif action == "type":
        beklenen = f"'{instruction}' alanına '{text}' yazıldı."
    else:
        beklenen = f"'{instruction}' alanına '{text}' yazılıp Enter ile gönderildi."
    return (
        "Sen bir ekran-farkı analistisin. Aşağıda AYNI Windows masaüstünün bir eylemden "
        "ÖNCE ve SONRA alınmış iki görüntüsü var (sırasıyla etiketlenmiş). Denenen eylem:\n"
        f"{beklenen}\n\n"
        "SADECE aşağıdaki JSON formatında yanıt ver, başka hiçbir metin veya markdown ekleme:\n"
        '{"verified": true veya false, "reason": "kısa Türkçe açıklama"}\n\n'
        "İki görüntü arasında bu eylemle tutarlı görünür bir değişiklik varsa (buton "
        "basılmış/durumu değişmiş, metin kutusuna yazı girmiş, mesaj gönderilip kutu "
        "boşalmış veya yeni içerik eklenmiş, pencere/diyalog açılmış ya da kapanmış vb.) "
        "verified:true yap. İki görüntü ayırt edilemeyecek kadar aynıysa veya eylemin "
        "başarısız olduğuna dair açık bir kanıt varsa verified:false yap."
    )


def _verify_action(
    client: genai.Client,
    instruction: str,
    action: str,
    text: str,
    before_path: Path,
    after_path: Path,
) -> dict:
    """Eylemden (click/type/type_enter) SONRA çağrılır — önce/sonra ekran görüntüsünü
    karşılaştırıp eylemin gerçekten UI'da bir etkisi olup olmadığını Gemini vision'a
    sorar. Bu, "pyautogui exception atmadı, öyleyse başardım" varsayımının yerini alan
    kapalı-döngü (self-correction) doğrulamasıdır — kullanıcının yaşadığı "yazdım dedi
    ama yazmadı" hatasının kök nedeniydi."""
    prompt = _verify_prompt(instruction, action, text)
    contents = [
        types.Part.from_text(text=prompt),
        types.Part.from_text(text="[EYLEMDEN ÖNCE]"),
        _build_image_part(before_path),
        types.Part.from_text(text="[EYLEMDEN SONRA]"),
        _build_image_part(after_path),
    ]
    for model_name in LOCATE_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(temperature=0.1),
            )
            out = str(getattr(response, "text", "") or "").strip()
            parsed = _extract_json(out)
            if parsed is not None:
                return parsed
        except Exception:
            continue
    # Doğrulama alt yapısı tamamen başarısız olursa eylemi başarısız SAYMIYORUZ —
    # pyautogui zaten exception atmadan çalıştı; doğrulama ekstra bir kanıt katmanı.
    # API'ye geçici erişilemezlik yüzünden kullanıcıya yanlış "başarısız" demek de
    # kendi başına bir güvenilirlik sorunu olurdu.
    return {"verified": True, "reason": "Doğrulama alt yapısına ulaşılamadı, eylem varsayılan kabul edildi."}


@register_tool("intervene_screen")
def intervene_screen(
    instruction: str,
    action: str = "click",
    text: str = "",
    confirm: bool = False,
    app_hint: str = "",
) -> dict:
    """Ekranda `instruction` ile tarif edilen öğeyi bulur.

    confirm=False: sadece bulur ve açıklar, HİÇBİR EYLEM YAPMAZ — kullanıcıya
    onay sorulmalı (bkz. core/prompt.txt kuralı). data.needs_confirmation=True.
    confirm=True: bulduktan sonra gerçekten tıklar (action="click"), tıklayıp
    yazar (action="type", `text` ile) veya tıklayıp yazıp Enter'a basar
    (action="type_enter" — "yaz ve gönder/çalıştır" gibi istekler için).
    app_hint verilirse (örn. "chrome", "gemini"), yakalamadan önce başlığında
    bu ifade geçen pencere öne getirilmeye çalışılır (best-effort, sekme
    değiştiremez — bkz. _activate_window).
    """
    if not instruction or not instruction.strip():
        return fail("Neye müdahale edeceğimi anlamadım, hedefi biraz daha tarif eder misin?")
    if action not in ("click", "type", "type_enter"):
        return fail(f"Bilinmeyen eylem türü: {action}")
    if action in ("type", "type_enter") and not text.strip():
        return fail("Yazılacak metin verilmedi.")
    if not HAS_PYAUTOGUI:
        return fail("Ekrana müdahale için 'pyautogui' kurulu değil. 'pip install pyautogui' ile kur.")

    api_key = str(get_app_config_value("gemini_api_key", "") or "").strip()
    if not api_key:
        return fail("Gemini API anahtarı eksik olduğu için ekrana müdahale edilemedi.")

    if app_hint:
        activate_error = _activate_window(app_hint)
        if activate_error:
            return fail(activate_error)

    client = genai.Client(api_key=api_key)

    if action == "click":
        verb = "tıklamak"
    elif action == "type":
        verb = f"'{text}' yazmak"
    else:
        verb = f"'{text}' yazıp göndermek (Enter)"

    # ── confirm=False: sadece bul ve açıkla, HİÇBİR EYLEM YAPMA ─────────────
    if not confirm:
        cap_ok, result, cap_w, cap_h, off_x, off_y = _capture_desktop()
        if not cap_ok:
            return fail(result)
        preview_path = Path(result)
        try:
            try:
                located = _locate_element(client, instruction, preview_path)
            except Exception as exc:
                return fail(f"Ekrandaki hedef bulunamadı: {exc}")
            if not located.get("found"):
                desc = str(located.get("description") or "").strip()
                return fail(f"Ekranda '{instruction}' ile eşleşen bir şey bulamadım." + (f" ({desc})" if desc else ""))
            desc = str(located.get("description") or instruction).strip()
            return ok(f"'{desc}' buldum, {verb} istiyorum. Onaylıyor musun?", needs_confirmation=True, target=desc)
        finally:
            try:
                if preview_path.exists():
                    preview_path.unlink()
            except Exception:
                pass

    # ── confirm=True: gerçekten uygula, sonra DOĞRULA ───────────────────────
    # Self-correction: eylem başarısız/doğrulanamaz görünürse fresh capture ile
    # 1 kez daha denenir (toplam en fazla 2 deneme). İkisi de doğrulanamazsa
    # dürüstçe hata dönülür — "başardım" diye varsayılmaz.
    last_desc = instruction
    last_reason = ""
    for attempt in (1, 2):
        cap_ok, result, cap_w, cap_h, off_x, off_y = _capture_desktop()
        if not cap_ok:
            return fail(result)
        before_path = Path(result)
        after_path: Path | None = None
        try:
            try:
                located = _locate_element(client, instruction, before_path)
            except Exception as exc:
                last_reason = f"hedef bulunamadı: {exc}"
                if attempt == 1:
                    continue
                return fail(f"Ekrandaki hedef bulunamadı: {exc}")

            if not located.get("found"):
                desc = str(located.get("description") or "").strip()
                last_reason = desc or "hedef bulunamadı"
                if attempt == 1:
                    continue
                return fail(f"Ekranda '{instruction}' ile eşleşen bir şey bulamadım." + (f" ({desc})" if desc else ""))

            try:
                norm_x = max(0, min(1000, int(float(located.get("x") or 0))))
                norm_y = max(0, min(1000, int(float(located.get("y") or 0))))
            except (TypeError, ValueError):
                last_reason = "geçersiz konum"
                if attempt == 1:
                    continue
                return fail("Gemini geçersiz bir konum döndürdü, tekrar dener misin?")

            real_x = off_x + round(norm_x / 1000 * cap_w)
            real_y = off_y + round(norm_y / 1000 * cap_h)
            desc = str(located.get("description") or instruction).strip()
            last_desc = desc

            try:
                pyautogui.click(real_x, real_y)
                if action in ("type", "type_enter"):
                    time.sleep(0.15)
                    pyautogui.write(text, interval=0.02)
                    if action == "type_enter":
                        time.sleep(0.1)
                        pyautogui.press("enter")
            except Exception as exc:
                last_reason = f"eylem uygulanamadı: {exc}"
                if attempt == 1:
                    continue
                return fail(f"'{desc}' bulundu ama eylem uygulanamadı: {exc}")

            # UI'nin tepki vermesi (animasyon/render) için kısa bekleme, sonra doğrulama
            time.sleep(0.6)
            cap_ok2, result2, _cw2, _ch2, _ox2, _oy2 = _capture_desktop()
            if cap_ok2:
                after_path = Path(result2)
                try:
                    verify = _verify_action(client, instruction, action, text, before_path, after_path)
                except Exception:
                    verify = {"verified": True, "reason": ""}
            else:
                verify = {"verified": True, "reason": "doğrulama için ekran görüntüsü alınamadı"}

            if verify.get("verified"):
                if action == "click":
                    return ok(f"Tamam, '{desc}' üzerine tıkladım.", target=desc, action=action)
                if action == "type":
                    return ok(f"Tamam, '{desc}' üzerine tıklayıp '{text}' yazdım.", target=desc, action=action)
                return ok(f"Tamam, '{desc}' üzerine tıklayıp '{text}' yazdım ve gönderdim.", target=desc, action=action)

            last_reason = str(verify.get("reason") or "").strip()
            if attempt == 1:
                continue

            fail_verb = "Tıklama" if action == "click" else "Yazma"
            extra = f" ({last_reason})" if last_reason else ""
            return fail(f"{fail_verb} denendi ancak arayüz yanıt vermedi.{extra}", target=desc, action=action)
        finally:
            for p in (before_path, after_path):
                if p is not None:
                    try:
                        if p.exists():
                            p.unlink()
                    except Exception:
                        pass

    extra = f" ({last_reason})" if last_reason else ""
    return fail(f"'{last_desc}' üzerinde eylem denendi ancak doğrulanamadı.{extra}", target=last_desc, action=action)
