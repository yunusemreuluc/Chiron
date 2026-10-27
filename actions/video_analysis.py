"""
Video analizi — bir YouTube linkini veya bilgisayardaki bir video dosyasını Gemini'nin
video-anlama özelliğine (Files API) yükleyip baştan sona "izletip" rapor aldırır.

screen_vision.py ile aynı desenler: model fallback listesi + geçici hata retry'ı,
kasıtlı olarak ortak bir modüle çıkarılmadı (bkz. o dosyadaki not — proje genelinde
kabul edilmiş bir tekrar).
"""

from __future__ import annotations

import importlib.util
import shutil
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

from google import genai
from google.genai import errors, types

from app_config import get_app_config_value
from actions.tool_result import fail, ok
from core.tool_registry import register_tool

# object_recognition.py'deki ile aynı gerekçe (2026-07-29 bellek ölçümü):
# yt_dlp modül seviyesinde import edilince açılışta ~50 MB tutuyordu, oysa
# yalnızca bir YouTube videosu analiz edilirken gerekiyor. Kurulu olup olmadığını
# anlamak için import şart değil — find_spec modülü çalıştırmadan arar.
HAS_YTDLP = importlib.util.find_spec("yt_dlp") is not None


# Video-anlama destekleyen modeller, tercih sırasına göre. "gemini-2.5-flash" ve
# "gemini-2.0-flash" burada BİLEREK yok — ilki bu hesapta "artık yeni kullanıcılara
# açık değil" diye 404 verdi, ikincisi kota/hız limitine takıldı (test sırasında
# gerçekten yaşandı, 2026-07-25). "flash-latest" Google'ın sürekli güncel tuttuğu bir
# takma ad olduğu için model deprecate olsa bile bu liste bozulmaz.
VIDEO_MODELS = (
    "models/gemini-flash-latest",
    "models/gemini-2.5-flash-lite",
    "models/gemini-3.5-flash",
)
SUPPORTED_LOCAL_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".mpg", ".mpeg", ".wmv", ".3gp",
}
MAX_VIDEO_SECONDS = 3600  # Gemini'nin varsayılan ayarlarda pratik üst sınırı ~1 saat
UPLOAD_POLL_INTERVAL = 3.0
UPLOAD_MAX_WAIT_SECONDS = 300.0


def _is_url(source: str) -> bool:
    try:
        parsed = urlparse(source.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def _download_video(url: str) -> tuple[bool, str, str, str]:
    """(ok, video_path_veya_hata, baslik, gecici_klasor) döner. gecici_klasor işlem
    bitince silinmek üzere caller'a bırakılır (indirilen video onun içinde)."""
    if not HAS_YTDLP:
        return False, "Video indirmek için 'yt-dlp' kurulu değil. 'pip install yt-dlp' ile kur.", "", ""

    tmp_dir = tempfile.mkdtemp(prefix="chiron-video-")
    ydl_opts = {
        # ffmpeg bu sistemde kurulu olmayabilir — ayrı ses/görüntü akışlarını
        # birleştirmek (merge) ffmpeg gerektirir, bu yüzden bilinçli olarak zaten
        # tek dosyada ses+görüntü içeren ("muxed") formatları istiyoruz.
        "format": (
            "best[height<=720][ext=mp4][acodec!=none][vcodec!=none]"
            "/best[ext=mp4][acodec!=none][vcodec!=none]/best"
        ),
        "outtmpl": str(Path(tmp_dir) / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    try:
        # Ağır import ilk gerçek indirmeye ertelendi (bkz. HAS_YTDLP notu).
        import yt_dlp

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get("duration") or 0
            if duration and duration > MAX_VIDEO_SECONDS:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                minutes = int(duration // 60)
                return False, (
                    f"Video ~{minutes} dakika, bu şu an desteklenen ~60 dakikalık "
                    "sınırın üzerinde. Daha kısa bir video dener misin?"
                ), "", ""
            ydl.download([url])
            filepath = ydl.prepare_filename(info)
            title = str(info.get("title") or "").strip()
    except Exception as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return False, f"Video indirilemedi: {exc}", "", ""

    if not Path(filepath).exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return False, "Video indirildi ama dosya bulunamadı.", "", ""

    return True, filepath, title, tmp_dir


def _resolve_local_path(source: str) -> tuple[bool, str]:
    path = Path(source.strip().strip('"')).expanduser()
    if not path.exists():
        return False, f"Video dosyası bulunamadı: {path}"
    if path.suffix.lower() not in SUPPORTED_LOCAL_EXTENSIONS:
        return False, f"Desteklenmeyen video uzantısı: {path.suffix or '(yok)'}"
    return True, str(path)


def _upload_and_wait(client: genai.Client, path: str) -> types.File:
    uploaded = client.files.upload(file=path)
    waited = 0.0
    while uploaded.state == types.FileState.PROCESSING:
        if waited >= UPLOAD_MAX_WAIT_SECONDS:
            raise RuntimeError("Video işleme zaman aşımına uğradı, tekrar dene.")
        time.sleep(UPLOAD_POLL_INTERVAL)
        waited += UPLOAD_POLL_INTERVAL
        uploaded = client.files.get(name=uploaded.name)
    if uploaded.state == types.FileState.FAILED:
        raise RuntimeError("Gemini videoyu işleyemedi (bozuk veya desteklenmeyen olabilir).")
    return uploaded


def _video_prompt(question: str, label: str) -> str:
    user_question = (question or "").strip()
    focus = (
        f"Kullanıcının özel sorusu: {user_question}\n\n"
        if user_question
        else ""
    )
    return (
        "Sen Chiron için video izleyip rapor eden bir analistsin. Aşağıdaki videoyu "
        f"baştan sona (görüntü + ses) izle.\nVideo: {label or 'verilen video'}\n\n"
        f"{focus}"
        "Rapor formatı:\n"
        "1. Genel özet (2-4 cümle) — video ne anlatıyor/gösteriyor.\n"
        "2. Önemli noktalar — madde madde, mümkünse yaklaşık zaman damgalarıyla (mm:ss).\n"
        "3. Varsa dikkat çekici/kritik bir detay (hata, uyarı, önemli sonuç vb.) ayrı belirt.\n"
        "4. Kullanıcının özel sorusu varsa onu doğrudan ve net cevapla.\n\n"
        "Uydurma yapma, videoda gerçekten görüp duyduğun şeyleri anlat. Türkçe yanıt ver."
    )


def _extract_response_text(response) -> str:
    text = str(getattr(response, "text", "") or "").strip()
    if text:
        return text
    candidates = getattr(response, "candidates", None) or []
    chunks: list[str] = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            part_text = str(getattr(part, "text", "") or "").strip()
            if part_text:
                chunks.append(part_text)
    return "\n".join(chunk for chunk in chunks if chunk).strip()


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


def _is_quota_error(exc: Exception) -> bool:
    message = str(exc or "").lower()
    markers = ("quota", "rate limit", "resource exhausted", "too many requests",
               "quota exceeded", "limit exceeded", "billing")
    return any(marker in message for marker in markers)


def _friendly_error(exc: Exception) -> str:
    if _is_quota_error(exc):
        return "Gemini video analizi kota veya hız limitine takıldı. Biraz bekleyip tekrar dene."
    if _is_transient_error(exc):
        return "Gemini video servisi şu anda yoğun veya geçici olarak ulaşılamıyor. Biraz sonra tekrar dene."
    return f"Gemini video analizi başarısız oldu: {exc}"


def _analyze_with_gemini(client: genai.Client, video_file: types.File, question: str, label: str) -> str:
    prompt = _video_prompt(question, label)
    retry_delays = (2.0, 4.0, 6.0)
    last_error: Exception | None = None

    for model_name in VIDEO_MODELS:
        for attempt, delay in enumerate(retry_delays, start=1):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[video_file, types.Part.from_text(text=prompt)],
                    config=types.GenerateContentConfig(temperature=0.2),
                )
                merged = _extract_response_text(response)
                if merged:
                    return merged
                raise RuntimeError("Gemini geçerli bir video analizi metni döndürmedi.")
            except Exception as exc:
                last_error = exc
                if attempt < len(retry_delays) and _is_transient_error(exc):
                    time.sleep(delay)
                    continue
                if _is_transient_error(exc):
                    break
                raise RuntimeError(_friendly_error(exc)) from exc

    assert last_error is not None
    raise RuntimeError(_friendly_error(last_error))


@register_tool("analyze_video")
def analyze_video(source: str, question: str = "") -> dict:
    if not source or not source.strip():
        return fail("Analiz edilecek video linki veya dosya yolu verilmedi.")

    api_key = str(get_app_config_value("gemini_api_key", "") or "").strip()
    if not api_key:
        return fail("Gemini API anahtarı eksik olduğu için video analizi yapılamadı.")

    tmp_dir = ""
    label = source.strip()
    video_path = ""

    try:
        if _is_url(source):
            dl_ok, result, title, tmp_dir = _download_video(source.strip())
            if not dl_ok:
                return fail(result)
            video_path = result
            label = title or source.strip()
        else:
            resolve_ok, result = _resolve_local_path(source)
            if not resolve_ok:
                return fail(result)
            video_path = result
            label = Path(video_path).name

        client = genai.Client(api_key=api_key)

        uploaded_file = None
        try:
            uploaded_file = _upload_and_wait(client, video_path)
            analysis = _analyze_with_gemini(client, uploaded_file, question, label)
        finally:
            if uploaded_file is not None:
                try:
                    client.files.delete(name=uploaded_file.name)
                except Exception:
                    pass

        return ok(f"[Video: {label}]\n{analysis}", label=label)

    except Exception as exc:
        return fail(f"Video analizi tamamlanamadı: {exc}")
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
