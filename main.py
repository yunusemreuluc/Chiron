#!/usr/bin/env python3
"""
Aıron — gerçek zamanlı sesli asistan çekirdeği (Gemini Live + araçlar).

BU DOSYA BİR GİRİŞ NOKTASI DEĞİL. Uygulama `desktop.py` ile başlar; oradaki
3D arayüz `AironLive`'ı `core/web_ui.WebUI` adaptörüyle çalıştırır.

2026-07-29'a kadar burada bir `main()` vardı ve Tkinter penceresini (ui.py) açardı;
kullanıcı isteğiyle Tkinter arayüzü tamamen kaldırıldı. `AironLive` DEĞİŞMEDİ —
arayüzüne yalnızca 15 noktadan dokunuyor ve WebUI o yüzeyin birebir karşılığı.
"""

import array
import asyncio
import datetime
import logging
import math
import threading
import time
import re
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

import pyaudio  # type: ignore[reportMissingModuleSource]
from google import genai  # type: ignore[reportMissingImports]
from google.genai import types  # type: ignore[reportMissingImports]

from core.audio_devices import (
    describe_input_observation,
    describe_input_problem,
    downsample_int16,
    open_input_stream,
    probe_input,
    resolve_device_index,
    resolve_input_device,
)
from core.logging_setup import setup_logging
from core.tool_registry import register_tool, dispatch_tool
from actions.tool_result import fail, ok
from app_config import get_app_config_value
from memory.memory_manager import load_memory, update_memory, format_memory_for_prompt
# NOT: Aşağıdaki actions/* import'ları main.py içinde İSİMLE hiç çağrılmıyor —
# hepsi kendi modüllerinde @register_tool(...) ile işaretli (bkz. core/tool_registry.py).
# Import'un TEK amacı o modülü yükleyip dekoratörü çalıştırmak (registry'ye kaydetmek);
# bir linter "kullanılmıyor" diye bunları silerse ilgili araç sessizce kaybolur —
# SİLİNMEMELİ.
from actions.open_app import open_app  # noqa: F401 — @register_tool yan etkisi için
from actions.sys_info  import sys_info  # noqa: F401
from actions.calendar import get_calendar_events, add_calendar_event, delete_calendar_event  # noqa: F401
from actions.reminders import get_reminders, add_reminder  # noqa: F401
from actions.browser   import browser_control  # noqa: F401
from actions.shell     import shell_run  # noqa: F401
from actions.whatsapp  import send_whatsapp_message, save_whatsapp_contact  # noqa: F401
from actions.media     import play_media  # noqa: F401
from actions.weather   import get_weather_summary  # noqa: F401
from actions.ocr import HAS_EASYOCR, lines_to_text, read_text_in_jpeg
from actions.screen_vision import analyze_screen  # noqa: F401
from actions.screen_control import intervene_screen  # noqa: F401
from actions.screen_monitor import (
    check_for_issue,
    get_active_window_title,
    reset_change_tracking,
)
from actions.ambient_context import describe_context, get_context  # noqa: F401 — @register_tool yan etkisi için
from actions.ambient_context import _idle_seconds
from actions.auto_fix import apply_plan, get_auto_fix_mode, plan_fix, set_auto_fix  # noqa: F401
from core.speaking_overlay import overlay as speaking_overlay
from actions.object_recognition import detect_objects_in_jpeg, describe_object_for_learning
from actions.sys_info import check_health_thresholds
from actions.screen_watch import check_watch_condition
from actions.notifications import get_recent_notifications  # noqa: F401 — @register_tool yan etkisi için
from actions.file_search import search_files, summarize_file  # noqa: F401 — @register_tool yan etkisi için
from actions.file_manager import manage_files  # noqa: F401 — @register_tool yan etkisi için
from actions.power_control import execute_power_action
from actions.gemini_automation import gemini_desktop_task  # noqa: F401 — @register_tool yan etkisi için
from actions.video_analysis import analyze_video  # noqa: F401
from actions.youtube_stats import get_youtube_channel_report  # noqa: F401
from memory.memory_manager import delete_memory  # noqa: F401 — @register_tool yan etkisi için
from memory.activity_log import log_event, get_daily_activity  # noqa: F401 — @register_tool yan etkisi için

if TYPE_CHECKING:  # yalnızca tip denetimi için — çalışma zamanında import edilmez
    from core.web_ui import WebUI

setup_logging()
logger = logging.getLogger("airon")

# Otomatik düzeltme, kullanıcı klavyeye dokunmayı bırakalı bu kadar geçmeden
# ekrana tıklamaz — yazmanın ortasında odak çalmak, düzelttiği sorundan daha
# rahatsız edici olurdu. Hata diyaloğu kullanıcıyı zaten durdurduğu için
# pratikte gecikme yaratmıyor (bkz. actions/auto_fix.py).
AUTO_FIX_MIN_IDLE_S = 2.0

# ── Ekran bekçisinin kota bütçesi (2026-08-01) ──────────────────────────────
# Bekçi 25 sn'de bir Gemini görü çağrısı atıyordu: saatte 144, günde 3456.
# Gemini ÜCRETSİZ katmanı günde 1500 istek veriyor — Aıron ~10 saat açık
# kalınca kota, kullanıcı tek kelime etmeden bitiyordu. Kasadaki üç ayrı
# "test ederken kota dolmuştu" notunun gerçek sebebi buydu.
#
# Üç katman var ve SIRALAMA ÖNEMLİ — ucuz olan önce:
#   1. Boşta   : kullanıcı yoksa ekran yakalamaya bile gerek yok
#   2. Değişim : ekran durduysa Gemini'ye sorma (screen_monitor'daki kapı)
#   3. Tavan   : 1 ve 2 işe yaramasa bile (video oynuyorsa değişim kapısı hiç
#                kapanmıyor — ölçüldü) kotayı GARANTİ eder
#
# 90 sn + saatte 20 tavan → en kötü ihtimalle günde 480 çağrı, ücretsiz
# katmanın üçte biri. Geri kalanı senin gerçekten kullandığın araçlara kalıyor.
SCREEN_WATCH_INTERVAL_S = 90.0
SCREEN_WATCH_MAX_CALLS_PER_HOUR = 20
# Bu kadar süredir klavye/fareye dokunulmadıysa ekranda hata aramanın anlamı
# yok — kimse görmüyor. Döndüğünde ekran zaten değişmiş olacağı için değişim
# kapısı da açılır ve kontrol kendiliğinden yapılır.
SCREEN_WATCH_MAX_IDLE_S = 120.0

# ── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).resolve().parent
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"


# ── WebcamStreamer ──────────────────────────────────────────────────────────
class WebcamStreamer:
    """
    Webcam'dan sürekli kare çeker ve en güncel JPEG'i bellekte tutar.
    Queue yerine tek bir 'latest frame' yaklaşımı — eski kare birikimi olmaz.
    """

    JPEG_QUALITY = 72
    MAX_DIM      = 640
    WARMUP       = 6

    def __init__(self):
        self._latest: bytes | None = None
        self._lock   = threading.Lock()
        self._active = False
        self._thread: threading.Thread | None = None

    @property
    def is_active(self) -> bool:
        return self._active

    def get_latest_frame(self) -> bytes | None:
        """Thread-safe, her zaman en güncel kareyi döner."""
        with self._lock:
            return self._latest

    def start(self) -> str:
        with self._lock:
            if self._active:
                return "already_active"
            self._active = True
            self._latest = None
        t = threading.Thread(target=self._run, daemon=True)
        self._thread = t
        t.start()
        return "ok"

    def stop(self):
        with self._lock:
            self._active = False
            self._latest = None

    def _run(self):
        try:
            import cv2
        except ImportError:
            logger.error("[Webcam] opencv-python yüklü değil.")
            with self._lock:
                self._active = False
            return

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            logger.error("[Webcam] Kamera açılamadı.")
            with self._lock:
                self._active = False
            return

        # Isınma — sensörün otomatik pozlaması oturuncaya kadar bekle
        for _ in range(self.WARMUP):
            cap.read()

        enc_params = [cv2.IMWRITE_JPEG_QUALITY, self.JPEG_QUALITY]

        try:
            while True:
                with self._lock:
                    if not self._active:
                        break

                ret, frame = cap.read()
                if not ret:
                    break

                h, w = frame.shape[:2]
                if max(h, w) > self.MAX_DIM:
                    s = self.MAX_DIM / max(h, w)
                    frame = cv2.resize(frame, (int(w * s), int(h * s)))

                frame = cv2.flip(frame, 1)  # yatay ayna — hem UI hem AI tutarlı
                ok, buf = cv2.imencode(".jpg", frame, enc_params)
                if ok:
                    with self._lock:
                        self._latest = buf.tobytes()

                # ~33 FPS yakala → 24 FPS UI her zaman taze kare bulur
                time.sleep(0.03)
        finally:
            cap.release()
            with self._lock:
                self._active = False
                self._latest = None
            logger.info("[Webcam] Kamera serbest bırakıldı.")


CONTROL_TOKEN_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)


class _ConversationReset(Exception):
    """Kullanıcı 'sohbeti sıfırla' dediğinde run() döngüsünü kırıp yeni oturum açtırır."""


def _is_reset_exception(exc: BaseException) -> bool:
    if isinstance(exc, _ConversationReset):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_is_reset_exception(sub) for sub in exc.exceptions)
    return False


# `thinking_config` reddedildiğinde sunucunun döndürdüğü hatada geçen izler.
# Ağ kopması gibi geçici hatalarda muhakemeyi boşuna kapatmamak için dar
# tutuluyor — eşleşmezse normal yeniden bağlanma akışı işler.
_THINKING_REJECTION_MARKERS = (
    "thinking",
    "thought",
    "invalid_argument",
    "unknown field",
    "not supported",
)


def _is_thinking_rejection(exc: BaseException) -> bool:
    """Bağlantı hatası `thinking_config` yüzünden mi?"""
    if isinstance(exc, BaseExceptionGroup):
        return any(_is_thinking_rejection(sub) for sub in exc.exceptions)
    message = str(exc).lower()
    return any(marker in message for marker in _THINKING_REJECTION_MARKERS)

# ── Model ───────────────────────────────────────────────────────────────────
LIVE_MODEL = "models/gemini-2.5-flash-native-audio-latest"

# ── Audio ───────────────────────────────────────────────────────────────────
FORMAT           = pyaudio.paInt16
CHANNELS         = 1
SEND_SAMPLE_RATE = 16000
RECV_SAMPLE_RATE = 24000
CHUNK_SIZE       = 1024

# Dalga formu seviyesi (bkz. AironLive._mic_level). Tam ölçek 16-bit tepe olan
# 32767 DEĞİL: normal konuşma o değerin çok altında kalıyor ve tepeye göre
# normalize edilen bir çubuk hiç kıpırdamıyor gibi görünüyor.
_MIC_LEVEL_STRIDE = 8
_MIC_LEVEL_FULL_SCALE = 9000.0

# Muhakeme akışı: bir düşünce parçası bu uzunluğa ulaşıp cümle sonu
# noktalamasıyla bittiğinde yayınlanır (bkz. AironLive._flush_reasoning).
# Çok küçük tutulursa Timeline yarım cümlelerle dolar.
_REASONING_MIN_CHARS = 40
# Oturum başına bir kez, mikrofonun gerçekten veri üretip üretmediğini ölçmek için
# (bkz. _check_microphone_health). Kısa tutuluyor — bağlantı sonrası ilk yanıtı
# geciktirmemeli; ölü bir akışı anlamak için 2 saniye fazlasıyla yeterli.
MIC_PROBE_SECONDS = 2.0
pya              = pyaudio.PyAudio()

# ── Tool tanımları — paylaşılan modülden ────────────────────────────────────
from tool_defs import TOOL_DECLARATIONS


def get_api_key() -> str:
    return str(get_app_config_value("gemini_api_key", "") or "")


def load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "Sen Aıron'sın — Windows'ta çalışan kişisel AI asistanı. "
            "Türkçe konuş. Kısa ve net yanıtlar ver. "
            "Araçları kullanarak görevleri tamamla, asla taklit etme."
        )


class AironLive:
    def __init__(self, ui: "WebUI"):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self._music_proc    = None
        self._webcam_streamer = WebcamStreamer()
        self._reset_event   = asyncio.Event()
        self._last_issue_signature   = ""
        self._last_issue_notified_at = 0.0
        self._last_health_notified_at: dict[str, float] = {}
        self._active_watches: list[dict] = []
        self._watch_id_counter = 0
        self._pending_power_task: "asyncio.Task | None" = None
        self._pending_power_action = ""
        self._mic_checked = False  # mikrofon sağlık kontrolü süreç başına bir kez
        # Modelin düşünme adımlarını isteyip istemediğimiz. Bir kez reddedilirse
        # süreç boyunca kapalı kalır — bkz. _build_config ve bağlantı hatası dalı.
        self._thinking_supported = True
        # Teşhis bayrağı: `model_turn` parçasının gerçek `thought` değeri
        # bağlantı başına yalnızca BİR KEZ loglanıyor (bkz. _receive_audio).
        self._logged_part_shape = False

        self.ui.on_text_command  = self._on_text_command
        self.ui.on_pause_toggle  = self._on_pause_toggle
        self.ui.on_effects_state_change = self._on_effects_state_change
        self.ui.on_webcam_toggle = self._on_webcam_toggle_ui
        self.ui.on_vision_detect = self._on_vision_detect_ui
        self.ui.on_vision_ocr = self._on_vision_ocr_ui
        self.ui.on_reset_command = self._on_reset_command
        self.ui.on_voice_change  = self._on_voice_change
        self._paused             = False

    def _on_pause_toggle(self, paused: bool):
        self._paused = paused
        if paused:
            self._stop_music()

    def _on_reset_command(self):
        """UI'de kullanıcı onayladıktan sonra çağrılır — mevcut oturumu kapatıp
        yeni, boş bağlamlı bir Gemini Live oturumu başlatır."""
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._reset_event.set)

    async def _watch_reset(self):
        await self._reset_event.wait()
        self._reset_event.clear()
        raise _ConversationReset()

    def _on_voice_change(self, voice: str):
        """Ayarlar panelinden ses değiştirilince çağrılır — uygulamayı kapatıp açmaya
        gerek kalmasın diye oturumu otomatik yeniden başlatır. _build_config() yeni
        sesi (app_config'ten) bir sonraki bağlantıda zaten okuyor, burada sadece
        SIFIRLA butonuyla aynı reconnect mekanizması (_reset_event) tetikleniyor —
        chat panelini temizlemeden, sessizce."""
        self._on_reset_command()

    def _on_effects_state_change(self, enabled: bool):
        if not enabled:
            self._stop_music()

    def _on_webcam_toggle_ui(self, activate: bool):
        if activate:
            status = self._webcam_streamer.start()
            success = status == "ok" or status == "already_active"
            self.ui.set_webcam_active(success)
            if not success:
                self.ui.write_log("ERR: Kamera açılamadı — opencv-python kurulu mu?")
        else:
            self._webcam_streamer.stop()
            self.ui.set_webcam_active(False)

    def automation_snapshot(self) -> dict:
        """Otomasyon panelinin okuduğu anlık durum (2026-07-30).

        `deadline` monotonic saat cinsinden tutuluyor (bkz. _tool_start_watch) —
        o değer süreç dışında hiçbir şey ifade etmiyor, bu yüzden burada KALAN
        SANİYEye çevriliyor. Arayüze mutlak zaman göndermek de olurdu ama
        monotonic saati duvar saatine çevirmek gereksiz bir hata kaynağı.
        """
        now = time.monotonic()
        watches = [
            {
                "id": watch.get("id"),
                "instruction": watch.get("instruction", ""),
                "condition": watch.get("condition", ""),
                "remainingSeconds": max(0, int(watch.get("deadline", now) - now)),
            }
            for watch in self._active_watches
        ]
        briefing = load_memory().get("scheduled_briefing") or None
        return {"watches": watches, "briefing": briefing}

    def _grab_frame_for_panel(self) -> bytes | None:
        """Vision paneli için kamerayı açar ve bir kare bekler (senkron).

        WebUI panel komutlarını kendi thread'inde çağırıyor, yani burada
        bloklamak serbest — ses döngüsüne dokunmuyor. asyncio karşılığı
        `_ensure_webcam_frame`; ikisi ayrı çünkü o araçlar (async) için, bu panel
        (sync) için.

        Kare alınamazsa sebebi log'a yazıp None döner — çağıran taraf boş sonuç
        yayınlayıp paneli "bekliyor"da bırakmamalı.
        """
        if not self._webcam_streamer.is_active:
            status = self._webcam_streamer.start()
            if status not in ("ok", "already_active"):
                self.ui.write_log("ERR: Kamera açılamadı — opencv-python kurulu mu?")
                return None
            self.ui.set_webcam_active(True)

        # Kamera yeni açıldıysa ilk kare henüz gelmemiş olabilir.
        frame = self._webcam_streamer.get_latest_frame()
        waited = 0.0
        while frame is None and waited < 3.0:
            time.sleep(0.3)
            waited += 0.3
            frame = self._webcam_streamer.get_latest_frame()

        if frame is None:
            self.ui.write_log("ERR: Kameradan görüntü alınamadı.")
        return frame

    def _on_vision_detect_ui(self):
        """Vision panelindeki 'nesneleri tara' düğmesi (2026-07-30)."""
        frame = self._grab_frame_for_panel()
        if frame is None:
            self.ui.emit_detections([], source="panel")
            return

        known = load_memory().get("known_objects", {})
        extra_vocab = [str(v.get("display_name", k)) for k, v in known.items() if isinstance(v, dict)]
        detections = detect_objects_in_jpeg(frame, extra_vocab)
        self.ui.emit_detections(detections, source="panel")

    def _on_vision_ocr_ui(self):
        """Vision panelindeki 'yazıyı oku' düğmesi (2026-07-31) — yerel OCR."""
        frame = self._grab_frame_for_panel()
        if frame is None:
            self.ui.emit_text([], source="panel")
            return

        if not HAS_EASYOCR:
            self.ui.write_log("ERR: OCR için easyocr kurulu değil (pip install easyocr).")
            self.ui.emit_text([], source="panel")
            return

        self.ui.emit_text(read_text_in_jpeg(frame), source="panel")

    def _focus_ui_section_for_tool(self, tool_name: str, args: dict):
        if tool_name == "sys_info":
            query = str(args.get("query", "")).strip().lower()
            if query in {"time", "saat", "zaman", "date", "tarih"}:
                self.ui.focus_panel("time", duration_ms=5200)
            else:
                self.ui.focus_panel("system", duration_ms=5200)
        elif tool_name == "get_weather":
            self.ui.focus_panel("weather", duration_ms=5600)

    # ── Registry'ye kayıtlı özel araçlar ─────────────────────────────────────
    # save_memory ve toggle_webcam saf actions/* fonksiyonları değil — ikisi de
    # AironLive'ın kendi durumuna (ui, webcam_streamer) ihtiyaç duyuyor. Yine de
    # aynı @register_tool mekanizmasıyla kaydediliyorlar; dispatch_tool() imzada
    # `self` gördüğünde instance'ı otomatik enjekte ediyor (bkz. core/tool_registry.py).
    @register_tool("save_memory")
    def _tool_save_memory(self, category: str = "notes", key: str = "", value: str = "") -> dict:
        if key and value:
            update_memory({category: {key: {"value": value}}})
            logger.info(f"[Memory] 💾 {category}/{key} = {value}")
            return ok("ok", category=category, key=key)
        return fail("Kaydedilecek kategori/anahtar/değer eksik.")

    @register_tool("toggle_webcam")
    def _tool_toggle_webcam(self, action: str = "start") -> dict:
        action = str(action or "start").strip().lower()
        if action == "start":
            status = self._webcam_streamer.start()
            if status == "ok":
                self.ui.set_webcam_active(True)
                return ok(
                    "Webcam akışı başlatıldı. "
                    "Artık kameranı görüyorum — dilediğin zaman soru sorabilirsin."
                )
            if status == "already_active":
                return ok("Webcam zaten açık, görüntü alıyorum.")
            return fail("Webcam başlatılamadı: opencv-python yüklü değil.")
        self._webcam_streamer.stop()
        self.ui.set_webcam_active(False)
        return ok("Webcam akışı durduruldu.")

    async def _ensure_webcam_frame(self, loop: asyncio.AbstractEventLoop, timeout: float = 3.0) -> bytes | None:
        """Webcam kapalıysa açar, sonra en güncel kareyi kısa bir zaman aşımıyla
        bekler. recognize_objects/learn_object'in ortak ön-koşulu."""
        if not self._webcam_streamer.is_active:
            status = self._webcam_streamer.start()
            if status == "ok":
                self.ui.set_webcam_active(True)

        waited = 0.0
        frame = self._webcam_streamer.get_latest_frame()
        while frame is None and waited < timeout:
            await asyncio.sleep(0.3)
            waited += 0.3
            frame = self._webcam_streamer.get_latest_frame()
        return frame

    @register_tool("recognize_objects")
    async def _tool_recognize_objects(self, query: str = "") -> dict:
        """Webcam görüntüsünde YOLO-World ile (yerel) nesne tespiti yapar
        (YAPILACAKLAR.md #2). Kamera kapalıysa otomatik açar. Kullanıcının önceden
        öğrettiği özel nesne isimleri (memory.json/known_objects) de arama
        dağarcığına eklenir."""
        loop = asyncio.get_event_loop()
        frame = await self._ensure_webcam_frame(loop)
        if frame is None:
            return fail("Kameradan görüntü alınamadı — webcam bağlı ve çalışıyor mu kontrol eder misin?")

        known = load_memory().get("known_objects", {})
        extra_vocab = [str(v.get("display_name", k)) for k, v in known.items() if isinstance(v, dict)]

        detections = await loop.run_in_executor(
            None, lambda: detect_objects_in_jpeg(frame, extra_vocab))

        # Aıron ne gördüyse kullanıcı da görsün: sonuçlar Vision paneline de
        # düşüyor (2026-07-30). Tespit boş olsa bile yayınlanıyor — panel "tarandı,
        # bir şey bulunamadı" ile "hiç taranmadı"yı ayırt edebilmeli.
        self.ui.emit_detections(detections, source="assistant")

        if not detections:
            return ok("Şu an kamerada tanıdığım bir nesne göremiyorum.", objects=[])

        names = [d["display_name"] for d in detections[:8]]
        message = "Kamerada şunları görüyorum: " + ", ".join(names) + "."
        return ok(message, objects=detections)

    @register_tool("read_text")
    async def _tool_read_text(self, query: str = "") -> dict:
        """Kameradaki yazıyı okur — YEREL EasyOCR (2026-07-31).

        Gemini vision'a göndermek yerine yerel okumanın sebebi kota: her okuma
        günlük kotadan yerdi. Burada kotaya hiç dokunulmuyor.
        """
        if not HAS_EASYOCR:
            return fail("Metin okuma için easyocr kurulu değil.")

        loop = asyncio.get_event_loop()
        frame = await self._ensure_webcam_frame(loop)
        if frame is None:
            return fail("Kameradan görüntü alınamadı — webcam bağlı ve çalışıyor mu?")

        # OCR CPU'da ~1 sn sürüyor; ses döngüsünü bloklamamak için executor'da.
        lines = await loop.run_in_executor(None, lambda: read_text_in_jpeg(frame))

        # Aıron ne okuduysa kullanıcı da görsün — panele de düşüyor.
        self.ui.emit_text(lines, source="assistant")

        if not lines:
            return ok("Kamerada okuyabildiğim bir yazı göremiyorum.", text="")

        text = lines_to_text(lines)
        logger.info(f"[OCR] 📖 {len(lines)} satır: {text[:80]}")
        return ok(f"Kamerada şunu okuyorum: {text}", text=text, lines=len(lines))

    @register_tool("learn_object")
    async def _tool_learn_object(self, name: str = "", description: str = "") -> dict:
        """Kameradaki nesneyi kullanıcının verdiği isimle hafızaya kaydeder
        (YAPILACAKLAR.md #2 — 'öğrenen yapı') — bu isim sonraki recognize_objects
        çağrılarında YOLO-World'ün arama dağarcığına eklenir."""
        if not name.strip():
            return fail("Nesneye bir isim vermen lazım.")
        loop = asyncio.get_event_loop()
        frame = await self._ensure_webcam_frame(loop)
        if frame is None:
            return fail("Kameradan görüntü alınamadı — webcam bağlı ve çalışıyor mu kontrol eder misin?")

        api_key = get_api_key()
        learned_description = await loop.run_in_executor(
            None, lambda: describe_object_for_learning(api_key, frame, name))
        final_description = description.strip() or learned_description or f"Kullanıcı bunu '{name}' olarak adlandırdı."

        key = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_") or "nesne"
        update_memory({"known_objects": {key: {"value": final_description, "display_name": name.strip()}}})
        logger.info(f"[ObjectLearn] 🧠 {name} = {final_description}")
        return ok(f"'{name}' hafızama kaydedildi: {final_description}", name=name.strip())

    @register_tool("start_watch")
    def _tool_start_watch(self, instruction: str = "", condition: str = "", timeout_minutes: int = 30) -> dict:
        """Genel 'izle, değişince haber ver' aracı (YAPILACAKLAR.md #7) — hemen döner,
        gerçek kontrol _watch_custom_conditions arka plan görevinde periyodik yapılır."""
        if not instruction.strip() or not condition.strip():
            return fail("Neyi izleyeceğimi ve hangi durumu beklediğimi bilmem lazım.")
        timeout_minutes = max(1, min(180, int(timeout_minutes or 30)))

        self._watch_id_counter += 1
        watch = {
            "id": self._watch_id_counter,
            "instruction": instruction.strip(),
            "condition": condition.strip(),
            "deadline": time.monotonic() + timeout_minutes * 60,
        }
        self._active_watches.append(watch)
        logger.info(f"[AIRON] 👀 İzleme başlatıldı: {watch['instruction']} → {watch['condition']}")
        return ok(
            f"Tamam, '{instruction.strip()}' izliyorum — '{condition.strip()}' olunca "
            f"haber vereceğim (en fazla {timeout_minutes} dakika).",
            watch_id=watch["id"],
        )

    @register_tool("stop_watch")
    def _tool_stop_watch(self, instruction: str = "") -> dict:
        needle = instruction.strip().lower()
        if not needle:
            count = len(self._active_watches)
            self._active_watches.clear()
            if count == 0:
                return ok("Zaten aktif bir izleme yoktu.")
            return ok(f"Tüm izlemeleri ({count} adet) durdurdum.")

        matches = [w for w in self._active_watches if needle in w["instruction"].lower()]
        if not matches:
            return fail(f"'{instruction}' ile eşleşen aktif bir izleme bulamadım.")
        for w in matches:
            self._active_watches.remove(w)
        return ok(f"'{instruction}' izlemesini durdurdum.")

    @register_tool("start_daily_briefing")
    def _tool_start_daily_briefing(self, time_str: str = "") -> dict:
        """Zamanlanmış günlük brifing (YAPILACAKLAR.md #11) — her gün belirtilen saatte
        kendiliğinden bir 'günaydın' brifingi verir. Zaman memory.json/scheduled_briefing'e
        kaydedilir (uygulama yeniden başlasa da hatırlanır); gerçek kontrol
        _watch_daily_briefing arka plan görevinde periyodik yapılır."""
        time_str = time_str.strip()
        if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", time_str):
            return fail("Saati 'SS:DD' (24 saat) formatında ver — örnek: '08:00'.")
        update_memory({"scheduled_briefing": {"config": {"value": time_str, "last_briefed_date": ""}}})
        logger.info(f"[AIRON] 🌅 Günlük brifing ayarlandı: {time_str}")
        return ok(f"Tamam, her gün saat {time_str}'te sana günlük brifing vereceğim.")

    @register_tool("stop_daily_briefing")
    def _tool_stop_daily_briefing(self) -> dict:
        result = delete_memory(category="scheduled_briefing", key="config", confirm=True)
        if not result.get("success"):
            return ok("Zaten ayarlanmış bir günlük brifing yoktu.")
        return ok("Günlük brifingi durdurdum.")

    _POWER_ACTION_LABELS = {
        "shutdown": "bilgisayarı kapatmak",
        "restart": "bilgisayarı yeniden başlatmak",
        "sleep": "bilgisayarı uyku moduna almak",
        "hibernate": "bilgisayarı hazırda bekletmek",
    }

    @register_tool("control_power")
    def _tool_control_power(self, action: str = "", delay_minutes: int = 0, confirm: bool = False) -> dict:
        """Bilgisayarı kapatır/yeniden başlatır/uyku-hazırda beklet moduna alır —
        ÇOK YIKICI bir eylem (kaydedilmemiş iş kaybı riski) olduğu için HER ZAMAN
        iki adımlı onay gerektirir (confirm=false önce açıklar, confirm=true
        gerçekten uygular). Gecikmeli istekler kendi asyncio görevimizle zamanlanır
        (Windows'un shutdown /t mekanizması yerine — tek tip, iptal edilebilir bir
        akış için). action='cancel' onay gerektirmez, her zaman güvenlidir."""
        action = action.strip().lower()

        if action == "cancel":
            if self._pending_power_task and not self._pending_power_task.done():
                self._pending_power_task.cancel()
                self._pending_power_task = None
                prev = self._pending_power_action
                self._pending_power_action = ""
                label = self._POWER_ACTION_LABELS.get(prev, prev or "işlem")
                return ok(f"'{label}' işlemini iptal ettim.")
            return ok("İptal edilecek zamanlanmış bir güç işlemi yoktu.")

        if action not in self._POWER_ACTION_LABELS:
            return fail(f"Bilinmeyen güç eylemi: '{action}'. shutdown/restart/sleep/hibernate/cancel kullan.")

        delay_minutes = max(0, min(480, int(delay_minutes or 0)))
        label = self._POWER_ACTION_LABELS[action]

        if not confirm:
            when = f"{delay_minutes} dakika sonra" if delay_minutes > 0 else "hemen"
            return ok(
                f"{label.capitalize()} istiyorum, {when} — kaydetmediğin işlerin varsa "
                "kaybolabilir. Onaylıyor musun?",
                needs_confirmation=True, action=action, delay_minutes=delay_minutes,
            )

        if self._pending_power_task and not self._pending_power_task.done():
            self._pending_power_task.cancel()

        if delay_minutes <= 0:
            try:
                execute_power_action(action)
            except Exception as exc:
                return fail(f"{label.capitalize()} başarısız oldu: {exc}")
            return ok(f"Tamam, {label} işlemini şimdi başlatıyorum.")

        self._pending_power_action = action
        self._pending_power_task = asyncio.create_task(
            self._run_power_action_after_delay(action, delay_minutes * 60))
        return ok(
            f"Tamam, {delay_minutes} dakika sonra {label} — vazgeçersen 'iptal et' de yeter.",
            action=action, delay_minutes=delay_minutes,
        )

    async def _run_power_action_after_delay(self, action: str, delay_seconds: int):
        try:
            await asyncio.sleep(delay_seconds)
        except asyncio.CancelledError:
            return

        logger.info(f"[AIRON] 🔌 Zamanlanmış güç eylemi çalıştırılıyor: {action}")
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, lambda: execute_power_action(action))
        except Exception:
            logger.exception(f"[AIRON] Güç eylemi başarısız: {action}")
            await self._send_proactive_system_message(
                f"[SİSTEM] Zamanlanmış '{action}' işlemi başarısız oldu. Kullanıcıya haber ver."
            )
        finally:
            self._pending_power_task = None
            self._pending_power_action = ""

    def _on_text_command(self, text: str):
        if self._paused:
            return
        self.ui.write_log(f"Siz: {text}")
        if not self._loop or not self.session:
            self.ui.write_log("ERR: Aıron bağlantısı henüz hazır değil.")
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def _stop_music(self):
        proc = self._music_proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        self._music_proc = None

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        else:
            self.ui.set_state("LISTENING")

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.ui.write_debug(f"{tool_name}: {short}", level="ERROR")
        self.ui.set_state("ERROR")

    @staticmethod
    def _should_play_success_sfx(tool_name: str, args: dict, result: dict) -> bool:
        if not result.get("success"):
            return False

        action_tools = {
            "open_app",
            "add_calendar_event",
            "add_reminder",
            "delete_calendar_event",
            "remove_calendar_event",
        }
        if tool_name in action_tools:
            # Onay bekleyen (needs_confirmation) sonuçlar henüz gerçek bir
            # eylem gerçekleştirmedi — "başarı" sesi çalmak yanıltıcı olurdu.
            return not result.get("data", {}).get("needs_confirmation")

        if tool_name == "send_whatsapp_message":
            return bool(args.get("send_now", False))

        return False

    @staticmethod
    def _clean_transcript_text(text: str) -> tuple[str, bool]:
        raw = str(text or "")
        had_noise = False
        if CONTROL_TOKEN_RE.search(raw):
            had_noise = True
            raw = CONTROL_TOKEN_RE.sub(" ", raw)
        cleaned = []
        for ch in raw:
            if ch in "\n\r\t" or ord(ch) >= 32:
                cleaned.append(ch)
            else:
                had_noise = True
        normalized = " ".join("".join(cleaned).split())
        return normalized.strip(), had_noise

    def _build_config(self) -> types.LiveConnectConfig:
        import datetime
        memory  = load_memory()
        mem_str = format_memory_for_prompt(memory)
        sys_p   = load_system_prompt()
        now     = datetime.datetime.now()
        time_ctx = f"[ŞU ANKİ ZAMAN]\n{now.strftime('%A, %d %B %Y — %H:%M')}\n\n"

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str + "\n\n")
        parts.append(sys_p)

        # Muhakeme akışı (2026-07-31): modelin düşünme adımları Timeline'da
        # görünsün diye isteniyor. `_thinking_supported` bir güvenlik valfi —
        # bu ayarı reddeden bir model/sürümde oturum HİÇ kurulamazdı ve Aıron
        # tamamen susardı (bağlantı sonsuz yeniden deniyor). Reddedilirse
        # aşağıdaki bağlantı hatası dalında kapatılıp hemen tekrar deneniyor.
        thinking = (
            types.ThinkingConfig(include_thoughts=True) if self._thinking_supported else None
        )

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            thinking_config=thinking,
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            speech_config=types.SpeechConfig(
                language_code="tr-TR",
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=str(get_app_config_value("voice", "Charon") or "Charon")
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})
        logger.info(f"[AIRON] 🔧 {name} {args}")
        # Her araç "THINKING" değil: ekranı ele geçirmek (AUTOMATION), belleğe
        # yazmak (MEMORY) ve kameraya bakmak (VISION) çekirdekte ayrı görünüyor.
        # Sınıflandırma core/web_ui.py'de — bkz. state_for_tool.
        self.ui.set_tool_state(name)

        loop = asyncio.get_event_loop()
        had_exception = False

        # UI odak efekti (ör. saat/hava paneli parlatma) — araç dispatch'inden
        # bağımsız, salt sunum katmanı yan etkisi, bu yüzden registry'nin dışında.
        self._focus_ui_section_for_tool(name, args)

        # Timeline (2026-07-30): araç çalışmaya başladı. Dispatch'ten HEMEN ÖNCE
        # yayınlanıyor — uzun süren araçlarda (ekran analizi, nesne tanıma)
        # kullanıcı beklerken panelde "çalışıyor" satırını görmesi gerekiyor.
        self.ui.task_started(name, args)

        try:
            result: dict = await dispatch_tool(name, args, instance=self, loop=loop)
        except Exception as e:
            result = fail(f"Hata: {e}")
            had_exception = True
            logger.exception(f"[AIRON] Arac calistirilirken hata: {name}")
            self.speak_error(name, e)

        tool_failed = not result.get("success", True)
        self.ui.task_finished(name, not tool_failed, str(result.get("message", "")))
        if tool_failed:
            if not had_exception:
                self.ui.set_state("ERROR")
        elif self._should_play_success_sfx(name, args, result):
            self.ui.play_success_sfx()

        if not tool_failed and not self.ui.muted:
            self.ui.set_state("LISTENING")

        logger.info(f"[AIRON] 📤 {name} → {str(result.get('message', ''))[:80]}")
        log_event("tool", f"{name}: {result.get('message', '')}", tool_name=name)
        return types.FunctionResponse(
            id=fc.id, name=name,
            response=result
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _stream_webcam_frames(self):
        """
        Webcam aktifken her 1.5s'de EN GÜNCEL kareyi session'a gönderir.
        Queue'suz 'latest frame' yaklaşımı: model hep şimdiki görüntüyü görür.
        """
        _last_sent: bytes | None = None
        while True:
            if not self._webcam_streamer.is_active:
                await asyncio.sleep(0.2)
                continue

            jpeg = self._webcam_streamer.get_latest_frame()
            if jpeg is None or jpeg is _last_sent:
                await asyncio.sleep(0.2)
                continue

            _last_sent = jpeg
            try:
                await self.session.send_realtime_input(
                    media={"data": jpeg, "mime_type": "image/jpeg"}
                )
            except Exception as e:
                logger.warning(f"[Webcam] Frame gönderilemedi: {e}")

            # 1.5 saniye bekle — model her zaman taze kare alır
            await asyncio.sleep(1.5)

    async def _update_ui_webcam_preview(self):
        """UI önizlemesini ~24 FPS günceller. AI akışından bağımsız."""
        frame_interval = 1.0 / 24.0   # ~0.0417 sn → 24 FPS
        idle_interval = 0.25          # kamera kapalıyken saniyede 4 bakış yeter
        while True:
            if self._webcam_streamer.is_active:
                jpeg = self._webcam_streamer.get_latest_frame()
                if jpeg:
                    self.ui.update_webcam_preview(jpeg)
                await asyncio.sleep(frame_interval)
            else:
                # Faz 0 (2026-10-02): kamera kapalıyken de saniyede 24 kez
                # uyanıyordu — işsiz ama sürekli. Açılınca en fazla 250 ms gecikme.
                await asyncio.sleep(idle_interval)

    def _proactive_checks_allowed(self, block_on_webcam: bool = False) -> bool:
        """Tüm proaktif bekçilerin (ekran, sistem sağlığı, özel izleme) ortak ön
        koşulu — duraklatılmışken, susturulmuşken, Aıron zaten konuşurken veya
        oturum hazır değilken hiçbiri çalışmamalı."""
        # Uzak modda mikrofon teknik olarak kapalı ama kullanıcı "beni rahat
        # bırak" demedi — tam tersine telefondan "bitince haber ver" diyebilmeli.
        # Bekçi mesajları o modda telefona yazı olarak düşüyor.
        if self._paused or (self.ui.muted and not getattr(self.ui, "remote_mode", False)):
            return False
        if block_on_webcam and self._webcam_streamer.is_active:
            return False
        with self._speaking_lock:
            if self._is_speaking:
                return False
        return bool(self.session)

    async def _send_proactive_system_message(self, text: str) -> None:
        """Gemini Live oturumuna, kullanıcı sormadan, 'sistem' çerçeveli bir mesaj
        enjekte eder — proaktif bekçilerin ortak bildirim mekanizması."""
        if not self.session:
            return
        try:
            await self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True,
            )
        except Exception:
            logger.exception("[AIRON] Proaktif mesaj gönderilemedi")

    async def _watch_screen_for_issues(self):
        """Proaktif ekran izleme (YAPILACAKLAR.md #4). Periyodik olarak aktif pencereyi
        tarar; kullanıcının dikkatini gerektiren açık bir durum (hata/uyarı penceresi vb.)
        görürse kendiliğinden sesli haber verir. Aynı sorunu tekrar tekrar bildirmemek
        için basit bir imza+cooldown mekanizması var (bkz. _last_issue_signature).

        KOTA: bu bekçi Aıron'un en pahalı arka plan işi — her kontrol bir Gemini
        görü çağrısı. Üç katmanlı bütçe için modül başındaki SCREEN_WATCH_*
        sabitlerine bak."""
        RENOTIFY_COOLDOWN_SECONDS = 180.0
        loop = asyncio.get_event_loop()
        # Son bir saatteki gerçek Gemini çağrılarının zaman damgaları.
        cagri_zamanlari: deque[float] = deque()
        atlanan = 0  # arka arkaya kaç kontrol atlandı (günlüğü boğmamak için)

        while True:
            await asyncio.sleep(SCREEN_WATCH_INTERVAL_S)

            if not self._proactive_checks_allowed(block_on_webcam=True):
                # Duraklatma/susturma sırasında ekran değişmiş olabilir ama biz
                # bakmadık; elimizdeki referans bayat. Unutalım ki dönüşte ilk
                # kontrol kesin çalışsın.
                reset_change_tracking()
                continue

            # ── Katman 1: kullanıcı masada mı ──
            if _idle_seconds() >= SCREEN_WATCH_MAX_IDLE_S:
                reset_change_tracking()
                continue

            # ── Katman 3: saatlik tavan ──
            simdi = time.monotonic()
            while cagri_zamanlari and simdi - cagri_zamanlari[0] > 3600:
                cagri_zamanlari.popleft()
            if len(cagri_zamanlari) >= SCREEN_WATCH_MAX_CALLS_PER_HOUR:
                atlanan += 1
                if atlanan == 1:
                    logger.info(
                        "[AIRON] Ekran bekçisi saatlik kota tavanına ulaştı "
                        f"({SCREEN_WATCH_MAX_CALLS_PER_HOUR}/saat), bekliyor"
                    )
                continue

            api_key = get_api_key()
            window_title = get_active_window_title()
            try:
                # ── Katman 2: değişim kapısı check_for_issue'nun İÇİNDE ──
                result = await loop.run_in_executor(
                    None, lambda: check_for_issue(api_key, window_title))
            except Exception:
                logger.exception("[AIRON] Proaktif ekran taraması başarısız")
                continue

            # Gemini'ye gerçekten gidildiyse tavana say. "unchanged" ile dönen
            # kontrol yerel kaldı, kota harcamadı — saymamak şart, yoksa tavan
            # tasarrufun kendisini cezalandırırdı.
            if not result.get("skipped"):
                cagri_zamanlari.append(simdi)
                atlanan = 0

            if not result.get("issue_found"):
                continue

            description = str(result.get("description", "")).strip()
            signature = description[:160]
            now = time.monotonic()
            if (
                signature == self._last_issue_signature
                and (now - self._last_issue_notified_at) < RENOTIFY_COOLDOWN_SECONDS
            ):
                continue

            self._last_issue_signature = signature
            self._last_issue_notified_at = now
            logger.info(f"[AIRON] 👁️ Proaktif ekran uyarısı: {signature}")

            await self._handle_detected_issue(description, window_title, api_key, loop)

    async def _handle_detected_issue(
        self, description: str, window_title: str, api_key: str, loop
    ) -> None:
        """Tespit edilen sorunu teşhis eder ve politikaya göre KENDİ düzeltir.

        Kullanıcı isteği (2026-08-01): "hata buluyorsa çözümü de bulsun ve kendi
        yapsın." Öncesinde Aıron yalnızca haber verip tavsiye ediyordu; ekranda
        bir şey yapması için kullanıcının "düzelt" demesi ve sonra bir de onay
        vermesi gerekiyordu.

        Politika `auto_fix_mode` (off/safe/all) — güvenlik kapıları ve neden üç
        tane oldukları actions/auto_fix.py başında.
        """
        mode = get_auto_fix_mode()
        pencere = window_title or "bilinmiyor"

        if mode == "off":
            await self._send_proactive_system_message(
                "[SİSTEM — proaktif ekran izleyicisi, kullanıcı bunu sormadı] "
                f"Arka planda ekranı izlerken şu sorunu fark ettin: {description} "
                f"(pencere: {pencere}). Kullanıcıya kısaca, doğal bir şekilde haber "
                "ver — VE somut bir çözüm veya ilk adım öner. Kullanıcı 'düzelt' "
                "derse intervene_screen'i normal kuralına göre (önce confirm=false, "
                "onay iste) kullan. Otomatik düzeltme KAPALI, kendiliğinden tıklama."
            )
            return

        # Kullanıcı klavyede aktifken tıklamak, yazdığı şeyin ortasında odağı
        # çalmak demek. Hata diyaloğu zaten onu durdurmuş olacağı için kısa bir
        # sessizlik beklemek pratikte gecikme yaratmıyor.
        if _idle_seconds() < AUTO_FIX_MIN_IDLE_S:
            logger.info("[AIRON] Otomatik düzeltme ertelendi — kullanıcı yazıyor")
            return

        plan = await loop.run_in_executor(
            None, lambda: plan_fix(api_key, description, pencere)
        )

        if not plan.get("can_fix_on_screen"):
            tavsiye = plan.get("user_advice") or ""
            await self._send_proactive_system_message(
                "[SİSTEM — proaktif ekran izleyicisi, kullanıcı bunu sormadı] "
                f"Şu sorunu fark ettin: {description} (pencere: {pencere}). "
                f"Teşhisin: {plan.get('diagnosis') or 'net değil'}. Bu ekranda "
                "tıklayarak çözülemiyor. Kullanıcıya kısaca haber ver ve şu somut "
                f"tavsiyeyi kendi cümlelerinle aktar: {tavsiye or 'uygun bir ilk adım öner'}."
            )
            return

        self.ui.task_started("auto_fix", {"sorun": description[:60]})
        sonuc = await loop.run_in_executor(None, lambda: apply_plan(plan, mode))
        yapilan = sonuc.get("applied", [])
        engellenen = sonuc.get("blocked", [])
        basarisiz = sonuc.get("failed", [])
        self.ui.task_finished(
            "auto_fix",
            bool(yapilan) and not basarisiz,
            f"{len(yapilan)} adım uygulandı, {len(engellenen)} engellendi",
        )

        parcalar = [
            "[SİSTEM — proaktif ekran izleyicisi, kullanıcı bunu sormadı] "
            f"Şu sorunu fark ettin: {description} (pencere: {pencere}). "
            f"Teşhisin: {plan.get('diagnosis') or 'net değil'}."
        ]
        if yapilan:
            adimlar = ", ".join(a["target"] for a in yapilan)
            parcalar.append(
                f"Kullanıcıya SORMADAN şunları kendin yaptın: {adimlar}. "
                "Bunu ona bildir — izin istemiş gibi değil, YAPILMIŞ bir şeyi "
                "haber verir gibi söyle ve sorunun düzelip düzelmediğini sor."
            )
        if engellenen:
            ilk = engellenen[0]
            parcalar.append(
                f"Şu adımı GÜVENLİK GEREĞİ yapmadın: '{ilk['target']}' "
                f"({ilk['reason']}). Bunu kullanıcıya açıkla ve yapmamı ister "
                "misin diye sor; onaylarsa intervene_screen ile uygula."
            )
        if basarisiz:
            parcalar.append(
                f"Şu adım denendi ama başarısız oldu: {basarisiz[0].get('target')} "
                f"({basarisiz[0].get('error')}). Uydurma, dürüstçe söyle."
            )
        if not (yapilan or engellenen or basarisiz):
            parcalar.append(
                "Plan çıkardın ama hiçbir adım uygulanamadı. Kullanıcıya sorunu "
                "bildir ve teşhisini aktar."
            )

        await self._send_proactive_system_message(" ".join(parcalar))

    async def _watch_system_health(self):
        """Sistem sağlığı bekçisi (YAPILACAKLAR.md #6). Periyodik olarak pil/disk/
        CPU/RAM eşiklerini kontrol eder, aşım olursa kendiliğinden sesli uyarır.
        Ekran izleyicisinden farklı olarak metrikler yapılandırılmış olduğu için
        (serbest metin değil) her metrik kendi cooldown'unu tutar."""
        POLL_INTERVAL_SECONDS = 60.0
        RENOTIFY_COOLDOWN_SECONDS = 600.0
        loop = asyncio.get_event_loop()

        while True:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

            if not self._proactive_checks_allowed():
                continue

            try:
                issues = await loop.run_in_executor(None, check_health_thresholds)
            except Exception:
                logger.exception("[AIRON] Sistem sağlığı kontrolü başarısız")
                continue

            now = time.monotonic()
            for issue in issues:
                metric = str(issue.get("metric", ""))
                message = str(issue.get("message", "")).strip()
                if not metric or not message:
                    continue
                last_notified = self._last_health_notified_at.get(metric, 0.0)
                if (now - last_notified) < RENOTIFY_COOLDOWN_SECONDS:
                    continue

                self._last_health_notified_at[metric] = now
                logger.info(f"[AIRON] 🩺 Sistem sağlığı uyarısı ({metric}): {message}")

                await self._send_proactive_system_message(
                    "[SİSTEM — proaktif sistem sağlığı bekçisi, kullanıcı bunu sormadı] "
                    f"Şunu fark ettin: {message} Kullanıcıya kısaca, doğal bir şekilde "
                    "haber ver."
                )

    async def _watch_custom_conditions(self):
        """Genel 'izle, değişince haber ver' aracı (YAPILACAKLAR.md #7). Kullanıcının
        start_watch ile kaydettiği izlemeleri periyodik olarak kontrol eder; koşul
        gerçekleşince (veya süre dolunca) kendiliğinden haber verip izlemeyi kaldırır."""
        POLL_INTERVAL_SECONDS = 20.0
        loop = asyncio.get_event_loop()

        while True:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

            if not self._active_watches or not self._proactive_checks_allowed():
                continue

            api_key = get_api_key()
            window_title = get_active_window_title()
            now = time.monotonic()

            for watch in list(self._active_watches):
                if now >= watch["deadline"]:
                    self._active_watches.remove(watch)
                    logger.info(f"[AIRON] ⏱️ İzleme süresi doldu: {watch['instruction']}")
                    await self._send_proactive_system_message(
                        "[SİSTEM — proaktif izleyici, kullanıcı bunu sormadı] "
                        f"'{watch['instruction']}' için '{watch['condition']}' koşulunu "
                        "beklerken süre doldu, koşul gerçekleşmedi. Kullanıcıya kısaca "
                        "haber ver (hâlâ istiyorsa tekrar izlemeye başlatabilirsin)."
                    )
                    continue

                try:
                    result = await loop.run_in_executor(
                        None,
                        lambda w=watch: check_watch_condition(
                            api_key, w["instruction"], w["condition"], window_title),
                    )
                except Exception:
                    logger.exception(f"[AIRON] İzleme kontrolü başarısız: {watch['instruction']}")
                    continue

                if not result.get("condition_met"):
                    continue

                detail = str(result.get("detail", "")).strip()
                self._active_watches.remove(watch)
                logger.info(f"[AIRON] 👀 İzleme koşulu gerçekleşti: {watch['instruction']} — {detail}")

                await self._send_proactive_system_message(
                    "[SİSTEM — proaktif izleyici, kullanıcı bunu sormadı] "
                    f"'{watch['instruction']}' için beklediğin '{watch['condition']}' "
                    f"koşulu gerçekleşti: {detail or 'onaylandı'}. Kullanıcıya kısaca, "
                    "doğal bir şekilde haber ver."
                )

    async def _watch_daily_briefing(self):
        """Zamanlanmış günlük brifing (YAPILACAKLAR.md #11). Dakikada bir saatin
        ayarlanan brifing saatine gelip gelmediğini kontrol eder; gelmişse (ve o gün
        henüz brifing verilmemişse) hava durumunu alıp proaktif bir 'günaydın' mesajı
        gönderir. Takvim/hatırlatıcı/haber verisine gerçek erişim olmadığı (bkz. madde 5)
        Gemini'ye açıkça hatırlatılıyor — uydurma bilgi verilmemesi için."""
        POLL_INTERVAL_SECONDS = 45.0
        loop = asyncio.get_event_loop()

        while True:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

            if not self._proactive_checks_allowed():
                continue

            config = (load_memory().get("scheduled_briefing") or {}).get("config") or {}
            target_time = str(config.get("value", "")).strip()
            if not target_time:
                continue

            now = datetime.datetime.now()
            if now.strftime("%H:%M") != target_time:
                continue
            today_str = now.strftime("%Y-%m-%d")
            if config.get("last_briefed_date") == today_str:
                continue

            update_memory({"scheduled_briefing": {"config": {
                "value": target_time, "last_briefed_date": today_str,
            }}})
            logger.info(f"[AIRON] 🌅 Günlük brifing zamanı geldi: {target_time}")

            try:
                weather_result = await loop.run_in_executor(None, lambda: get_weather_summary())
            except Exception:
                weather_result = {}
            weather_text = (
                weather_result.get("message", "")
                if weather_result.get("success")
                else "hava durumu şu an alınamadı"
            )

            await self._send_proactive_system_message(
                "[SİSTEM — zamanlanmış günlük brifing, kullanıcı bunu sormadı] "
                f"Günlük brifing zamanı ({target_time}) geldi. Bugünkü hava durumu: "
                f"{weather_text}. Kullanıcıya doğal, sıcak bir 'günaydın' brifingi ver — "
                "hava durumunu aktar. Takvim/hatırlatıcı/haberlere GERÇEK erişimin yok "
                "(sadece tarayıcı açabiliyorsun) — bunları ASLA uydurma; istersen kullanıcıya "
                "'takvimine göz atmak ister misin' diye sorabilirsin ama gerçek etkinlik "
                "bilgisi verme."
            )

    async def _check_microphone_health(self, device_index):
        """Mikrofon gerçekten veri üretiyor mu? (bkz. core/audio_devices.py)

        Windows'ta bir mikrofon uç noktası AKTİF ve sesi açık görünürken bile tam
        dijital sessizlik üretebiliyor; PyAudio bunu hata olarak bildirmez. Bu
        durumda Gemini hiç konuşma duymaz, Aıron da hiç yanıt vermez — kullanıcıya
        "Aıron'un sesi gelmiyor" gibi görünen sessiz arıza tam olarak budur.
        Kontrol mikrofon akışı açılmadan ÖNCE yapılır (aynı cihaz iki kez
        açılmasın diye) ve süreç başına YALNIZCA BİR KEZ: bağlantı koptuğunda
        oturum yeniden kurulur, her yeniden denemede 2 saniye dinlemeye geç
        başlamanın anlamı yok — cihazın durumu o arada değişmez."""
        if self._mic_checked:
            return
        self._mic_checked = True

        probe = await asyncio.to_thread(
            probe_input, pya, device_index, SEND_SAMPLE_RATE, MIC_PROBE_SECONDS
        )
        detail = (
            f"karar={probe.verdict} medyan={probe.median:.1f} "
            f"değişim={probe.spread:.1f} hız={probe.rate}"
        )
        problem = describe_input_problem(probe)
        if problem:
            logger.warning("[AIRON] 🎤 Mikrofon sağlık kontrolü başarısız (%s)", detail)
            self.ui.write_log(f"ERR: {problem}")
            self.ui.write_debug(f"Mikrofon sondası: {detail}", level="ERROR")
            return

        # Sessizlik ARIZA DEĞİL (bkz. core/audio_devices.py § SESSİZLİK ARIZA
        # DEĞİLDİR): sessiz odada çalışan bir mikrofon da sıfır okuyor. Bu yüzden
        # sohbete ERR olarak DÜŞMÜYOR — kullanıcıyı olmayan bir arızayla
        # korkutmak, gerçek arızayı kaçırmak kadar zarar veriyor. Yalnızca
        # geliştirici akışında uyarı olarak duruyor.
        observation = describe_input_observation(probe)
        if observation:
            logger.info("[AIRON] 🎤 Mikrofon açılışta sessizdi (%s)", detail)
            self.ui.write_debug(f"Mikrofon sondası: {detail} — {observation}", level="WARN")
        else:
            logger.info("[AIRON] 🎤 Mikrofon sağlıklı (%s)", detail)

    @staticmethod
    def _mic_level(chunk: bytes) -> float:
        """16-bit mono PCM parçasının 0..1 aralığındaki kaba ses seviyesi.

        Her örneği DEĞİL her 8.'sini okuyor: bir seviye göstergesi için 128
        örnek fazlasıyla yeterli ve bu hesap mikrofon döngüsünün içinde,
        saniyede ~30 kez çalışıyor — oradaki her iş sesin gecikmesine biniyor.
        `audioop` kullanılmadı, Python 3.13'te kaldırıldı.
        """
        usable = len(chunk) - (len(chunk) % 2)
        if usable <= 0:
            return 0.0
        samples = array.array("h")
        samples.frombytes(chunk[:usable])
        window = samples[::_MIC_LEVEL_STRIDE]
        if not window:
            return 0.0
        mean_square = sum(value * value for value in window) / len(window)
        return min(1.0, math.sqrt(mean_square) / _MIC_LEVEL_FULL_SCALE)

    async def _listen_audio(self):
        logger.info("[AIRON] 🎤 Mikrofon başladı")
        # Cihaz seçimi: config'te "mic_device" varsa ona uyan cihaz, yoksa sistem
        # varsayılanı. Varsayılan cihaz sessiz kaldığında kullanıcının koda
        # dokunmadan başka bir mikrofona geçebilmesi için.
        device_index = await asyncio.to_thread(
            resolve_input_device, pya, str(get_app_config_value("mic_device", "") or "")
        )
        await self._check_microphone_health(device_index)

        # Akış cihazın kabul ettiği hızda açılıyor, istediğimiz hızda değil:
        # WASAPI paylaşımlı modda 16 kHz'i reddediyor ve bu makinede çalışan tek
        # yol o. Gelen tamponlar Gemini'ye gitmeden 16 kHz'e indiriliyor.
        stream, capture_rate = await asyncio.to_thread(
            open_input_stream, pya, device_index, SEND_SAMPLE_RATE, CHUNK_SIZE
        )
        try:
            while True:
                raw = await asyncio.to_thread(
                    stream.read, CHUNK_SIZE, exception_on_overflow=False)
                # Seviye göstergesi de gönderilen sesten hesaplanıyor, ham
                # tampondan değil: dalga formu Aıron'un GERÇEKTEN duyduğu şeyi
                # göstermeli.
                data = downsample_int16(raw, capture_rate, SEND_SAMPLE_RATE)
                with self._speaking_lock:
                    airon_speaking = self._is_speaking
                listening = not airon_speaking and not self.ui.muted and not self._paused
                # Dalga formu (2026-07-30): sohbet dock'undaki görsel geri
                # bildirim. Susturulmuş/duraklatılmışken sıfır gönderiliyor —
                # mikrofon kapalıyken dalgalanan bir çubuk, kapalı olmadığını
                # söylerdi.
                self.ui.update_mic_level(self._mic_level(data) if listening else 0.0)
                if listening:
                    await self.out_queue.put({"data": data, "mime_type": "audio/pcm"})
        except RuntimeError as e:
            # Oturum kapanırken (sohbet sıfırlama, yeniden bağlanma) event
            # loop'un thread havuzu bu döngüden ÖNCE kapanabiliyor; o zaman
            # `asyncio.to_thread` "cannot schedule new futures after shutdown"
            # fırlatıyor. Mikrofonla hiç ilgisi yok — kapanış yarışı.
            #
            # Eskiden bu da `logger.exception("Mikrofon hatasi")` ile ERROR
            # olarak yazılıyordu ve log'da gerçek bir donanım arızası gibi
            # duruyordu. 2026-08-06'da mikrofon sessizliği araştırılırken tam
            # olarak buna takılıp yanlış yere bakıldı: normal bir yeniden
            # bağlanma, arıza gibi okunuyordu. Sessiz arıza kadar pahalı olan
            # şey, arıza olmayanı arıza diye raporlamaktır.
            if "after shutdown" in str(e):
                logger.info("[AIRON] 🎤 Mikrofon döngüsü kapanışta durdu (normal).")
                return
            logger.exception("[AIRON] Mikrofon hatasi")
            raise
        except Exception:
            logger.exception("[AIRON] Mikrofon hatasi")
            raise
        finally:
            stream.close()

    def _flush_reasoning(self, buffer: list[str], force: bool = False) -> None:
        """Biriken düşünce metnini Timeline'a yayınlar.

        Düşünceler de transcript gibi küçük parçalar hâlinde akıyor. Her parçayı
        tek tek yayınlamak Timeline'ı yarım kelimelerle doldururdu; turn_complete'e
        kadar biriktirmek ise muhakemeyi CEVAPTAN SONRA gösterirdi — oysa değeri
        tam olarak cevaptan önce görünmesinde. Orta yol: cümle bittiğinde yayınla.
        """
        text = "".join(buffer).strip()
        if not text:
            buffer.clear()
            return
        if not force and not (len(text) >= _REASONING_MIN_CHARS and text[-1] in ".!?…"):
            return
        buffer.clear()
        self.ui.emit_reasoning(text)

    async def _receive_audio(self):
        logger.info("[AIRON] 👂 Alım başladı")
        self._logged_part_shape = False
        out_buf, in_buf, thought_buf = [], [], []
        output_noise = False
        output_noise_samples = []
        try:
            while True:
                async for response in self.session.receive():
                    if response.data:
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        # Muhakeme (2026-07-31): modelin düşünme adımları
                        # `model_turn.parts` içinde `thought=True` işaretli
                        # parçalar olarak geliyor — normal metin parçalarıyla
                        # aynı listede, bayrakla ayrışıyorlar.
                        if sc.model_turn and sc.model_turn.parts:
                            for part in sc.model_turn.parts:
                                thought_flag = getattr(part, "thought", None)
                                piece = str(getattr(part, "text", "") or "")
                                # TEŞHİS (2026-08-06): muhakeme satırı canlı
                                # oturumda hiç görünmedi ve log iki ihtimali
                                # ayırt etmiyordu — model düşünce göndermiyor mu,
                                # yoksa `thought` alanı hep False mu geliyor?
                                # SDK'nın "non-data parts: ['text','thought']"
                                # uyarısı yalnızca ALANIN VARLIĞINI söylüyor,
                                # değerini değil. Bağlantı başına bir kez, ilk
                                # metin taşıyan parçanın gerçek bayrağını yaz.
                                if piece and not self._logged_part_shape:
                                    self._logged_part_shape = True
                                    logger.info(
                                        "[AIRON] 🧠 model_turn parçası: thought=%r (%d karakter)",
                                        thought_flag,
                                        len(piece),
                                    )
                                if thought_flag and piece:
                                    thought_buf.append(piece)
                            self._flush_reasoning(thought_buf)

                        if sc.output_transcription and sc.output_transcription.text:
                            self.set_speaking(True)
                            raw_txt = sc.output_transcription.text.strip()
                            if raw_txt:
                                txt, had_noise = self._clean_transcript_text(raw_txt)
                                if had_noise:
                                    output_noise = True
                                    if len(output_noise_samples) < 4:
                                        output_noise_samples.append(raw_txt)
                                if txt:
                                    out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = sc.input_transcription.text.strip()
                            if txt:
                                in_buf.append(txt)
                                self.ui.mark_user_activity(True)

                        if sc.turn_complete:
                            # Yarım kalan düşünce varsa tur bitmeden yayınla —
                            # cümle sınırını bekleyip kaybetmeyelim.
                            self._flush_reasoning(thought_buf, force=True)

                            # Sentinel: ses kuyrugundaki tum chunk'lar calindiktan
                            # sonra SPEAKING -> LISTENING gecisi yapilsin (yanki onlenir).
                            self.audio_in_queue.put_nowait(None)

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"Siz: {full_in}")
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Aıron: {full_out}")
                                if output_noise_samples:
                                    self.ui.write_debug(
                                        "Kısmen filtrelenen ses transcripti: " + " | ".join(output_noise_samples),
                                        level="WARN",
                                    )
                            elif output_noise:
                                self.ui.write_log("ERR: Aıron sesli yanıtını çözümlerken bir hata oluştu.")
                                if output_noise_samples:
                                    self.ui.write_debug(
                                        "Filtrelenen ham transcript: " + " | ".join(output_noise_samples),
                                        level="WARN",
                                    )
                                self.ui.set_state("ERROR")

                            if full_in and full_out:
                                log_event("conversation", f"Siz: {full_in} | Aıron: {full_out}")
                            elif full_in:
                                log_event("conversation", f"Siz: {full_in}")
                            elif full_out:
                                # full_in bos ama full_out var -> kullanicidan gelen
                                # gercek konusma degil, proaktif bir bekci mesaji
                                # (ekran/sistem sagligi uyarisi, gunluk brifing vb.)
                                log_event("conversation", f"Aıron (kendiliğinden): {full_out}")

                            out_buf = []
                            output_noise = False
                            output_noise_samples = []

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            logger.info(f"[AIRON] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses)

        except Exception as e:
            logger.exception("[AIRON] Alim hatasi")
            raise

    async def _play_audio(self):
        logger.info("[AIRON] 🔊 Ses çalma başladı")
        # Cihaz seçimi (config: "speaker_device"). Windows varsayılan çıkışı
        # kulaklık jakına düşmüşken kullanıcı hoparlörden dinliyorsa Aıron'un sesi
        # "gelmiyor" gibi görünür — bu ayar kodu değiştirmeden hedefi sabitler.
        device_index = await asyncio.to_thread(
            resolve_device_index,
            pya,
            "output",
            str(get_app_config_value("speaker_device", "") or ""),
        )
        open_kwargs = {"output_device_index": device_index} if device_index is not None else {}
        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT, channels=CHANNELS,
            rate=RECV_SAMPLE_RATE, output=True,
            **open_kwargs,
        )
        try:
            while True:
                chunk = await self.audio_in_queue.get()
                if chunk is None:
                    # turn_complete sentinel — tum ses calindi, dinlemeye gec
                    self.set_speaking(False)
                    speaking_overlay.set_speaking(False)
                    continue
                # Uzak mod (bkz. core/web_ui.py): kullanıcı evde değil, cevap
                # telefona YAZI olarak gidiyor (output_transcription → log).
                # Ses parçası çalınmadan düşürülüyor; transkript bundan
                # etkilenmiyor, çünkü modelin çıktısından geliyor, hoparlörden değil.
                if getattr(self.ui, "speaker_muted", False):
                    continue
                self.set_speaking(True)
                # Tepsi göstergesi GERÇEK sesten besleniyor (bkz.
                # core/speaking_overlay.py). Aynı parçadan hesaplanıyor, ekstra
                # bir okuma yok; `_mic_level` mikrofonla aynı 16-bit mono PCM
                # biçimini bekliyor ve çıktı da o biçimde.
                speaking_overlay.set_speaking(True)
                speaking_overlay.push_level(self._mic_level(chunk))
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            logger.exception("[AIRON] Ses calma hatasi")
            raise
        finally:
            self.set_speaking(False)
            stream.close()

    async def run(self):
        connect_attempts = 0
        while True:
            # Duraklatılmışsa bağlanma, bekle
            if self._paused:
                await asyncio.sleep(1)
                continue

            try:
                # Client'ı her bağlanışta yeniden oluştur ve anahtarı tazeden oku.
                # Böylece yeni girilen API anahtarı anında geçerli olur; ilk
                # deneme başarısız olsa bile otomatik tekrar (3sn) kendini onarır.
                client = genai.Client(
                    api_key=get_api_key(),
                    http_options={"api_version": "v1alpha"}
                )
                logger.info("[AIRON] 🔌 Bağlanıyor...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session        = session
                    self._loop          = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue      = asyncio.Queue(maxsize=10)

                    logger.info("[AIRON] ✅ Bağlandı.")
                    connect_attempts = 0          # başarılı bağlantı → sayaç sıfırla
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: Aıron hazır. Dinliyorum...")

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._stream_webcam_frames())
                    tg.create_task(self._update_ui_webcam_preview())
                    tg.create_task(self._watch_reset())
                    tg.create_task(self._watch_screen_for_issues())
                    tg.create_task(self._watch_system_health())
                    tg.create_task(self._watch_custom_conditions())
                    tg.create_task(self._watch_daily_briefing())

            except Exception as e:
                self.set_speaking(False)
                # Webcam akışını durdur — yeni session'da yeniden başlayacak
                if self._webcam_streamer.is_active:
                    self._webcam_streamer.stop()
                    self.ui.set_webcam_active(False)

                if _is_reset_exception(e):
                    # Kullanıcı sohbeti sıfırladı — sessizce, hemen yeni bir oturum aç.
                    logger.info("[AIRON] ♻️ Sohbet sıfırlandı, yeni oturum açılıyor...")
                    self.ui.write_debug("Sohbet sıfırlandı, yeni oturum açılıyor.", level="INFO")
                    connect_attempts = 0
                    await asyncio.sleep(0.3)
                    continue

                # Güvenlik valfi: model `thinking_config`i kabul etmiyorsa onu
                # kapatıp HEMEN tekrar dene. Aksi hâlde bağlantı her seferinde
                # aynı sebeple düşer ve Aıron hiç açılmaz — muhakeme akışı güzel
                # ama sesli asistanın çalışması pazarlık konusu değil.
                if self._thinking_supported and _is_thinking_rejection(e):
                    self._thinking_supported = False
                    logger.warning("[AIRON] 🧠 Model düşünme akışını kabul etmedi — kapatıldı.")
                    self.ui.write_debug(
                        "Model `thinking_config` kabul etmedi; muhakeme akışı bu oturumda kapalı.",
                        level="WARN",
                    )
                    continue

                logger.exception(f"[AIRON] Baglanti hatasi: {e}")
                connect_attempts += 1
                # İlk birkaç deneme sessiz: yeni girilen API anahtarı Google
                # tarafında saniyeler içinde aktifleşebilir. Kullanıcıya hemen
                # "hatalı anahtar" göstermeyip kısa aralıkla otomatik tekrar dene.
                if connect_attempts <= 3:
                    self.ui.set_state("INITIALISING")
                    logger.info(f"[AIRON] 🔄 Bağlanmayı tekrar deniyor ({connect_attempts}/3)...")
                    await asyncio.sleep(2)
                else:
                    self.ui.write_log(
                        f"ERR: Aıron baglanamiyor — API anahtarini ve internet "
                        f"baglantisini kontrol et. ({e})"
                    )
                    self.ui.set_state("ERROR")
                    logger.warning("[AIRON] 🔄 5 saniyede yeniden bağlanıyor...")
                    await asyncio.sleep(5)
