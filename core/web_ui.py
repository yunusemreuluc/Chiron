"""
WebUI — ChironLive ile 3D arayüz arasındaki adaptör.

NEDEN (2026-07-29, kullanıcı isteği): "sesli asistanla devam edelim, 3D arayüzü
ona monte edelim". Ses döngüsü (main.py → ChironLive) arayüzüne 15 noktadan
dokunuyordu — 9 metot çağrısı + 6 geri çağırma yuvası. Bu sınıf tam olarak o
yüzeyi taklit ediyor, ama ekrana çizmek yerine olayları WebSocket'e yayınlıyor.

Sonuç: ChironLive'ın TEK SATIRI değişmeden 3D arayüzle çalışıyor. Ses döngüsünün
arayüzden bağımsızlığı, onu yeniden yazarak değil, bağımlılığın karşı tarafını
değiştirerek sağlandı — sesin çalıştığı bilinen kod yoluna hiç dokunulmadı.

    ChironLive  ──(ui.set_state / write_log / ...)──>  WebUI  ──WS──>  3D arayüz
    ChironLive  <──(on_text_command / on_pause_toggle)── WebUI  <──HTTP── 3D arayüz

Tasarım kuralı: buradaki hiçbir çağrı ses döngüsünü BLOKLAMAMALI ve asla
patlamamalı. Arayüz kapalı, backend ölü ya da tarayıcı bağlı değilken bile
Chiron konuşmaya devam etmeli — olaylar sessizce düşer.
"""

from __future__ import annotations

import base64
import logging
import threading
import time
from collections import deque
from typing import Any, Callable

from app_config import get_app_config_value
from backend.core import commands
from backend.models.events import WSEvent
from backend.websocket.manager import manager

logger = logging.getLogger("chiron")

# main.py'nin durum isimleri → frontend/stores/aiStateStore.ts değerleri.
STATE_MAP = {
    "LISTENING": "listening",
    "THINKING": "thinking",
    "SPEAKING": "speaking",
    "VISION": "vision",
    "AUTOMATION": "automation",
    "MEMORY": "memory",
}

# ── Araç → çekirdek durumu (2026-07-31, bkz. Notes/Arayuz.md § Beş tepki) ────────────
# Notes/Tasarim-Kurallari.md § Enerji çekirdeği beş tepki istiyor: Ses, Düşünme,
# Görü, Otomasyon, Hafıza. Gerçekte üçü çalışıyordu: HER araç çağrısı "THINKING"
# yayınlıyordu, yani Chiron'un ekranı ele geçirmesiyle hava durumuna bakması
# sahnede birebir aynı görünüyordu. "VISION" ise STATE_MAP'te duruyor ama
# main.py hiçbir zaman göndermiyordu — ölü bir daldı.
#
# BEYAZ LİSTE, kara liste değil: burada adı geçmeyen araç "THINKING"e düşüyor.
# Yeni bir araç eklenip buraya yazılmazsa davranışı BUGÜNKÜYLE aynı olur —
# sessizce yanlış bir durum göstermez, sadece daha az özel olur. Kapsamlı eşleme
# zorunlu tutulsaydı araç eklemenin maliyeti beşinci bir dosya olurdu
# (bkz. CLAUDE.md § Adding a new tool — dört yer, fazlası değil).

# Chiron kendi belleğine yazıyor ya da ondan okuyor.
_MEMORY_TOOLS = frozenset({
    "save_memory",
    "delete_memory",
    "get_daily_activity",
    "learn_object",  # "şunu tanı" — sonraki oturumlar için kalıcı kayıt
    "save_whatsapp_contact",
})

# Chiron makineye ya da dış dünyaya DOKUNUYOR (okumakla yetinmiyor). Ayrım okuma/
# yazma: `get_calendar_events` düşünme, `add_calendar_event` otomasyon.
_AUTOMATION_TOOLS = frozenset({
    "gemini_desktop_task",
    "intervene_screen",
    "shell_run",
    "open_app",
    "browser_control",
    "play_media",
    "control_power",
    "toggle_webcam",
    "send_whatsapp_message",
    "add_reminder",
    "add_calendar_event",
    "delete_calendar_event",
    "start_watch",
    "stop_watch",
    "start_daily_briefing",
    "stop_daily_briefing",
})

# Chiron BAKIYOR — kameradan ya da ekrandan.
_VISION_TOOLS = frozenset({
    "analyze_screen",
    "recognize_objects",
    "read_text",
    "analyze_video",
})


def state_for_tool(name: str) -> str:
    """Çalışmak üzere olan aracın çekirdekte hangi durum olarak görüneceği."""
    if name in _MEMORY_TOOLS:
        return "MEMORY"
    if name in _AUTOMATION_TOOLS:
        return "AUTOMATION"
    if name in _VISION_TOOLS:
        return "VISION"
    return "THINKING"

# Webcam önizlemesi main.py'de ~24 FPS güncelleniyor. Her kareyi base64'e çevirip
# WebSocket'ten yollamak bant genişliğini ve CPU'yu boşuna yakar — önizleme için
# 8 FPS fazlasıyla yeterli (3D sahnenin kendi 60 FPS'i etkilenmemeli).
WEBCAM_PREVIEW_FPS = 8.0

# Mikrofon seviyesi yayın hızı — dalga formu için 12 FPS akıcı görünüyor.
MIC_LEVEL_FPS = 12.0

# Timeline'da bir görevin yanında gösterilecek argüman özeti için üst sınırlar.
# Araç argümanları bazen çok uzun olabiliyor (ör. shell_run komutu, uzun metin) —
# ham hâliyle yayınlamak hem soketi hem paneli gereksiz doldurur.
MAX_ARG_VALUE_CHARS = 48
MAX_SUMMARIZED_ARGS = 3

# Telefonun yeniden bağlanınca tamamladığı sohbet geçmişi (bkz.
# backend/api/remote.py /history). Arayüzdeki MAX_LINES (200) kadar değil:
# telefon yalnızca kaçırdığı son birkaç turu görmek istiyor.
LOG_HISTORY_LINES = 80


def _summarize_args(args: dict[str, Any] | None) -> str:
    """Araç argümanlarını Timeline'da tek satıra sığacak şekilde özetler."""
    if not args:
        return ""
    parts: list[str] = []
    for key, value in list(args.items())[:MAX_SUMMARIZED_ARGS]:
        text = str(value)
        if len(text) > MAX_ARG_VALUE_CHARS:
            text = text[: MAX_ARG_VALUE_CHARS - 1] + "…"
        parts.append(f"{key}={text}")
    return ", ".join(parts)


class WebUI:
    """ChironLive'ın arayüzden beklediği yüzey."""

    def __init__(self) -> None:
        # ── ChironLive'ın okuduğu durum bayrakları ────────────────────────────
        # Kullanıcının kendi mikrofon tercihi. ChironLive'ın okuduğu `muted` ise
        # bir özellik: tercih VEYA uzak mod (bkz. `muted`).
        self._user_muted = False
        self.paused = False
        # Uzak mod (2026-09-15, telefon erişimi): kullanıcı evde değil. Hoparlör
        # ve mikrofon birlikte kapanıyor — boş evde Chiron yüksek sesle cevap
        # vermesin, ortam sesini de komut sanmasın. `speaker_muted`'ı
        # ChironLive._play_audio okuyor. Uzak moddan çıkınca mikrofon, uzak moda
        # girmeden ÖNCEKİ hâline dönüyor (kullanıcı zaten kapatmışsa kapalı kalır).
        self.remote_mode = False
        self.speaker_muted = False
        self._log_history: deque[dict[str, Any]] = deque(maxlen=LOG_HISTORY_LINES)
        self._log_lock = threading.Lock()
        # Telefondaki Chiron'un `query_desktop_chiron` aracı (2026-09-15). Soru
        # canlı oturuma normal bir metin gibi gidiyor; cevap ise "Chiron:" log
        # satırı olarak dönüyor. Bekleyen varsa o satır ona teslim ediliyor.
        self._answer_waiter: dict[str, Any] | None = None
        self._answer_lock = threading.Lock()

        # ── ChironLive'ın doldurduğu geri çağırma yuvaları ────────────────────
        # (ChironLive.__init__ bunlara kendi metotlarını atıyor.)
        self.on_text_command: Callable[[str], None] | None = None
        self.on_pause_toggle: Callable[[bool], None] | None = None
        self.on_effects_state_change: Callable[[bool], None] | None = None
        self.on_webcam_toggle: Callable[[bool], None] | None = None
        self.on_reset_command: Callable[[], None] | None = None
        self.on_voice_change: Callable[[str], None] | None = None
        # Vision panelinin "tara" düğmesi (2026-07-30). ChironLive dolduruyor;
        # yerel YOLO-World tespitini çalıştırıp sonucu emit_detections ile geri
        # yayınlıyor.
        self.on_vision_detect: Callable[[], None] | None = None
        # Vision panelinin "yazıyı oku" düğmesi (2026-07-31) — yerel EasyOCR.
        self.on_vision_ocr: Callable[[], None] | None = None

        self._state = "INITIALISING"
        self._last_webcam_frame_at = 0.0
        self._last_mic_level_at = 0.0
        # Kamera açık mı — arayüz açılışta bunu sorabilmeli (WS olayını kaçırmış
        # olabilir, ör. paneli sonradan açtı).
        self.webcam_active = False
        # ChironLive örneği — hazır olup olmadığını (canlı oturum var mı) sormak
        # için. Arayüz, oturum kurulmadan komut gönderirse komut sessizce düşüyor;
        # bunu kullanıcıya "bağlanıyor" olarak göstermek için gerekli.
        self._assistant: Any = None

        self._register_commands()

    @property
    def muted(self) -> bool:
        """Mikrofon fiilen kapalı mı — ChironLive bunu okuyor.

        Tercih ve uzak mod AYRI tutuluyor (Astra incelemesi, 2026-09-15): önceden
        uzak mod girişte `muted`'ı ezip çıkışta eski değeri geri yazıyordu. Uzak
        moddayken verilen susturma kararı çıkışta kayboluyor, uzak moddayken
        mikrofonu açmak ise sonraki telefon mesajında kapanmıyordu.
        """
        return self._user_muted or self.remote_mode

    def bind_assistant(self, assistant: Any) -> None:
        self._assistant = assistant
        self._emit_status()

    def is_ready(self) -> bool:
        """Gemini Live oturumu kuruldu mu? Kurulmadan gönderilen komut kaybolur."""
        return bool(getattr(self._assistant, "session", None))

    # ── Olay yayını ─────────────────────────────────────────────────────────
    def _emit(self, event: str, data: dict[str, Any] | None = None) -> None:
        try:
            manager.broadcast_threadsafe(WSEvent(event=event, data=data or {}))
        except Exception:
            # Arayüz katmanındaki hiçbir arıza ses döngüsünü etkilememeli.
            logger.debug("WebUI olayı yayınlanamadı: %s", event, exc_info=True)

    # ── Arayüzden gelen komutlar ────────────────────────────────────────────
    def _register_commands(self) -> None:
        commands.register("text", self._handle_text)
        commands.register("mute", self._handle_mute)
        commands.register("pause", self._handle_pause)
        commands.register("reset", self._handle_reset)
        commands.register("voice", self._handle_voice)
        commands.register("remote_mode", self._handle_remote_mode)
        commands.register("ask", self._handle_ask)
        # Vision paneli (2026-07-30). `on_webcam_toggle` yuvası 2026-07-29'dan
        # beri vardı ve ChironLive onu dolduruyordu, ama komut olarak HİÇ
        # kaydedilmemişti — yani kamerayı yalnızca Chiron kendi aracıyla
        # (toggle_webcam) açabiliyordu, kullanıcı arayüzden açamıyordu.
        commands.register("webcam", self._handle_webcam)
        commands.register("vision_detect", self._handle_vision_detect)
        commands.register("vision_ocr", self._handle_vision_ocr)
        commands.register_readiness(self.is_ready)
        # Otomasyon paneli (2026-07-30) — aktif izlemelerin tek kaynağı
        # ChironLive'ın belleği; API onu buradan okuyor.
        commands.register_provider("automation", self._automation_snapshot)
        commands.register_provider("log_history", self._log_history_snapshot)
        commands.register_provider("assistant_status", self._status_snapshot)
        commands.register("ask_cancel", lambda _payload: self.cancel_ask())

    def _handle_text(self, payload: dict) -> None:
        text = str(payload.get("text", "")).strip()
        if not text or not self.on_text_command:
            return
        # NOT: "Siz: ..." satırını BURADA yazmıyoruz — ChironLive._on_text_command
        # zaten yazıyor. İkisi birden yazınca satır sohbette iki kez görünüyordu.
        # ChironLive.on_text_command içeride asyncio'ya köprü kuruyor; yine de
        # HTTP isteğini bekletmemek için ayrı thread'de çağrılıyor.
        threading.Thread(target=self.on_text_command, args=(text,), daemon=True).start()

    def _handle_mute(self, payload: dict) -> None:
        self._user_muted = bool(payload.get("value", False))
        if not self._user_muted and self.remote_mode:
            # Uzak modda mikrofon fiilen kapalı; PC'den "aç" diyen biri masada
            # demektir — sessizce hiçbir şey olmaması yerine uzak moddan çık.
            self._set_remote_mode(False)
            return
        self.write_log("SYS: Mikrofon kapatıldı." if self._user_muted else "SYS: Mikrofon açık.")
        self._emit_status()

    def _handle_remote_mode(self, payload: dict) -> None:
        """Uzak modu aç/kapat.

        `quiet_if_unchanged`: voice.py her metin komutunda isteğin nereden
        geldiğine göre bu komutu gönderiyor — durum zaten doğruysa sohbete her
        seferinde "uzak mod açık" satırı düşmesin.
        """
        enabled = bool(payload.get("value", False))
        if enabled == self.remote_mode:
            if not payload.get("quiet_if_unchanged"):
                self._emit_status()
            return

        self._set_remote_mode(enabled)

    def _set_remote_mode(self, enabled: bool) -> None:
        self.remote_mode = enabled
        self.speaker_muted = enabled
        if enabled:
            self.write_log("SYS: Uzak mod açık — PC hoparlörü ve mikrofonu kapalı, cevaplar yazılı.")
        else:
            self.write_log(
                "SYS: Uzak mod kapandı — PC hoparlörü açık"
                + (", mikrofon senin tercihinle kapalı." if self._user_muted else ".")
            )
        self._emit_status()

    def _handle_ask(self, payload: dict) -> None:
        """Soruyu gönderir ve SONRAKİ Chiron cevabını `on_answer`'a teslim eder.

        Tek bekleyen: backend/api/remote.py soruları kilitle sıraya koyuyor.
        Aynı anda iki soru olsaydı hangi cevabın hangisine ait olduğu log
        satırından anlaşılamazdı.
        """
        text = str(payload.get("text", "")).strip()
        on_answer = payload.get("on_answer")
        if not text or not callable(on_answer) or not self.on_text_command:
            return
        if self.paused:
            on_answer("Chiron PC'de duraklatılmış, soruyu işleyemiyor.", False)
            return
        if not self.remote_mode:
            self._set_remote_mode(True)
        # Bekleyen, kendi sorusunun "Siz:" satırı log'a düşene kadar SİLAHSIZ.
        # Astra incelemesi (2026-09-15): önceki sürüm kayıt anından sonraki İLK
        # "Chiron:" satırını alıyordu — zaman aşımına uğramış önceki sorunun geç
        # cevabı ya da bir proaktif bekçi mesajı yanlış soruya teslim ediliyordu.
        with self._answer_lock:
            self._answer_waiter = {"text": text, "armed": False, "callback": on_answer}
        threading.Thread(target=self.on_text_command, args=(text,), daemon=True).start()

    def cancel_ask(self) -> None:
        with self._answer_lock:
            self._answer_waiter = None

    def _log_history_snapshot(self) -> list[dict[str, Any]]:
        with self._log_lock:
            return list(self._log_history)

    def _handle_pause(self, payload: dict) -> None:
        self.paused = bool(payload.get("value", False))
        if self.on_pause_toggle:
            self.on_pause_toggle(self.paused)
        self.write_log("SYS: Duraklatıldı." if self.paused else "SYS: Devam ediliyor.")
        self._emit_status()

    def _handle_voice(self, payload: dict) -> None:
        """Ayarlar panelinden ses değişti. Yeni ses config'e zaten yazıldı
        (backend/api/settings.py); burada oturumun sessizce yeniden kurulması
        tetikleniyor ki değişiklik anında duyulsun."""
        voice = str(payload.get("voice", "")).strip()
        if not voice or not self.on_voice_change:
            return
        self.write_log(f"SYS: Ses '{voice}' olarak değiştirildi, oturum yenileniyor.")
        threading.Thread(target=self.on_voice_change, args=(voice,), daemon=True).start()

    def _handle_webcam(self, payload: dict) -> None:
        """Vision panelinden kamera aç/kapat."""
        if not self.on_webcam_toggle:
            return
        enabled = bool(payload.get("enabled", False))
        # Kamera açmak birkaç yüz ms sürebiliyor (OpenCV cihazı açıyor) — HTTP
        # isteğini bekletmemek için ayrı thread'de.
        threading.Thread(target=self.on_webcam_toggle, args=(enabled,), daemon=True).start()

    def _handle_vision_detect(self, payload: dict) -> None:
        """Vision panelinden 'tara': tek karelik yerel nesne tespiti.

        Neden istek üzerine ve sürekli değil: YOLO-World ağır bir model (torch
        zinciri ~273 MB) ve her kare için çıkarım yapmak 60 FPS hedefini de pili
        de bitirirdi. Kullanıcı taramayı istediğinde çalışıyor.
        """
        if not self.on_vision_detect:
            return
        threading.Thread(target=self.on_vision_detect, daemon=True).start()

    def _handle_vision_ocr(self, payload: dict) -> None:
        """Vision panelinden 'yazıyı oku': tek karelik yerel OCR.

        Tespit gibi istek üzerine çalışıyor: EasyOCR bir kareyi CPU'da ~1 saniyede
        okuyor, bunu sürekli yapmak hem pili hem 60 FPS hedefini bitirirdi.
        """
        if not self.on_vision_ocr:
            return
        threading.Thread(target=self.on_vision_ocr, daemon=True).start()

    def _handle_reset(self, payload: dict) -> None:
        self.write_log("SYS: Sohbet sıfırlandı. Yeni bir oturum başlatılıyor...")
        if self.on_reset_command:
            threading.Thread(target=self.on_reset_command, daemon=True).start()

    def _automation_snapshot(self) -> dict:
        """ChironLive'ın otomasyon durumunu okur (aktif izlemeler, brifing).

        Asistan henüz bağlanmadıysa boş bir durum dönüyor — None dönmek
        "sesli asistan yok" anlamına gelirdi, oysa burada asistan VAR, sadece
        henüz ayağa kalkmadı."""
        snapshot = getattr(self._assistant, "automation_snapshot", None)
        if not callable(snapshot):
            return {"watches": [], "briefing": None}
        return snapshot()

    def _status_snapshot(self) -> dict[str, Any]:
        return {
            "muted": self.muted,
            "paused": self.paused,
            "ready": self.is_ready(),
            "remote": self.remote_mode,
        }

    def _emit_status(self) -> None:
        self._emit("assistant_status", self._status_snapshot())

    # ── ChironUI yüzeyi — ChironLive'ın çağırdıkları ──────────────────────────
    def set_state(self, state: str) -> None:
        previous, self._state = self._state, state
        # ERROR/MUTED/PAUSED gibi durumların 3D sahnede karşılığı yok; sahne
        # "idle"a düşer ama olayın kendisi (hata satırı) log'dan zaten görünür.
        self._emit("energy_state", {"state": STATE_MAP.get(state, "idle")})

        # Oturum kurulduğu an (INITIALISING/THINKING → LISTENING) arayüzün yazma
        # kutusu açılmalı; bunu ayrıca bildirmezsek arayüz "bağlanıyor"da kalırdı.
        if state == "LISTENING" and previous != "LISTENING":
            self._emit_status()

    def set_tool_state(self, name: str) -> None:
        """Bir araç çalışmaya başlarken çekirdeği o işin durumuna alır.

        Modül düzeyindeki `state_for_tool` üzerinden geçiyor ama main.py oradan
        değil BURADAN çağırıyor: `core.web_ui` yalnızca TYPE_CHECKING altında
        import ediliyor (fastapi + websocket zincirini açılışta yüklememek için,
        bkz. Notes/Kurulum-ve-Baslatma.md — 340→139 MB). Serbest fonksiyonu
        doğrudan import etmek o kazancı geri verirdi; `self.ui` zaten elde.
        """
        self.set_state(state_for_tool(name))

    def write_log(self, text: str) -> None:
        """Sohbet satırı. Metnin KENDİSİ durumu da belirler: "Siz:" ile başlayan
        satır düşünmeyi, "ERR:" hata durumunu tetikler. Bu sözleşme eski Tkinter
        arayüzünden devralındı — `ChironLive` log satırlarını hâlâ bu öneklerle
        yazıyor, o yüzden ayrıştırma burada yaşıyor (bkz. conversationStore.ts)."""
        entry = {"text": text, "at": time.time()}
        # Geçmişe yayından ÖNCE yazılıyor: telefon /history'yi tam yayın anında
        # sorarsa satır ya geçmişte ya canlı akışta olsun, ikisinde birden
        # yoksa kaybolmasın (telefon ikisini `at`+metin ile birleştiriyor).
        with self._log_lock:
            self._log_history.append(entry)
        self._emit("log", entry)

        self._deliver_answer(text)

    def _deliver_answer(self, text: str) -> None:
        """Bekleyen `/ask` sorusu varsa cevabını teslim eder.

        Sıra: önce sorunun kendi "Siz: <soru>" satırı görülmeli (silahlanma),
        ANCAK ondan sonraki ilk "Chiron:" satırı cevap sayılır. ERR satırları
        bekleyeni çözmüyor: bir aracın hatası turun sonu değil, model yine konuşuyor.
        Kalan sınır: silahlanmayla cevap arasına bir proaktif bekçi mesajı
        girerse o teslim edilir — bekçiler uzak modda seyrek, bilinçli kabul.
        """
        callback = None
        answer = ""
        with self._answer_lock:
            waiter = self._answer_waiter
            if waiter is None:
                return
            head, _, body = text.partition(":")
            head = head.strip().lower()
            if head in ("siz", "you") and body.strip() == waiter["text"]:
                waiter["armed"] = True
            elif waiter["armed"] and head in ("chiron", "daphne"):
                self._answer_waiter = None
                callback = waiter["callback"]
                answer = body.strip()
        if callback is not None:
            callback(answer, True)

        lowered = text.lower()
        if lowered.startswith("siz:") or lowered.startswith("you:"):
            self.mark_user_activity(True)
            self.set_state("THINKING")
        elif lowered.startswith("err:") or "error" in lowered:
            self.write_debug(text, level="ERROR")
            # Chiron konuşurken gelen hata satırı sahneyi durdurmamalı: 3D
            # çekirdek "speaking" animasyonunun ortasında idle'a düşüyordu
            # (ERROR'ın sahnede karşılığı yok). Hata zaten sohbette görünüyor;
            # konuşma bitince durum kendiliğinden güncellenecek.
            if self._state != "SPEAKING":
                self.set_state("ERROR")

    def write_debug(self, text: str, level: str = "INFO") -> None:
        self._emit("debug", {"text": text, "level": level, "at": time.time()})

    def emit_reasoning(self, text: str) -> None:
        """Modelin düşünme adımı — alt zaman çizelgesine (2026-07-31).

        Sohbete YAZILMIYOR: sohbet Chiron'un söyledikleri için, muhakeme ise ne
        söyleyeceğine nasıl karar verdiği. İkisini aynı akışa koymak sohbeti
        okunmaz hâle getirirdi.
        """
        clean = str(text or "").strip()
        if clean:
            self._emit("reasoning", {"text": clean, "at": time.time()})

    # ── Görev akışı (Timeline, 2026-07-30) ──────────────────────────────────
    # `task_started`/`task_finished` olayları backend/models/events.py'de
    # 2026-07-27'den beri TANIMLIYDI ama hiçbir yerden yayınlanmıyordu — yani
    # Chiron araç çalıştırırken arayüz bunu hiç görmüyordu. Artık her araç
    # çağrısı (main.py → _execute_tool) buradan geçiyor.
    def task_started(self, name: str, args: dict[str, Any] | None = None) -> None:
        self._emit("task_started", {"name": name, "args": _summarize_args(args), "at": time.time()})

    def task_finished(self, name: str, success: bool, message: str = "") -> None:
        self._emit(
            "task_finished",
            {
                "name": name,
                "success": bool(success),
                # Mesaj kısaltılıyor: araç sonuçları bazen paragraf uzunluğunda
                # oluyor ve Timeline tek satırlık bir akış.
                "message": str(message or "")[:160],
                "at": time.time(),
            },
        )

    def update_mic_level(self, level: float) -> None:
        """Mikrofon ses seviyesi (0..1) — sohbet dock'undaki dalga formu için.

        Kimse dinlemiyorsa hiç yayınlanmıyor ve hız MIC_LEVEL_FPS ile sınırlı:
        mikrofon döngüsü saniyede ~30 kez kare okuyor, hepsini sokete basmak
        arayüzü boşuna meşgul ederdi. 12 FPS dalga formu için akıcı görünüyor.
        """
        if not manager.has_clients():
            return
        now = time.monotonic()
        if now - self._last_mic_level_at < 1.0 / MIC_LEVEL_FPS:
            return
        self._last_mic_level_at = now
        self._emit("mic_level", {"level": round(max(0.0, min(1.0, level)), 3)})

    def mark_user_activity(self, active: bool = True) -> None:
        self._emit("user_activity", {"active": bool(active)})

    def play_success_sfx(self) -> None:
        self._emit("sfx", {"name": "success"})

    def focus_panel(self, section: str, duration_ms: int = 4200) -> None:
        section = (section or "").strip().lower()
        if section:
            self._emit("panel_focus", {"section": section, "durationMs": duration_ms})

    def set_webcam_active(self, active: bool) -> None:
        self.webcam_active = bool(active)
        self._emit("webcam_state", {"active": self.webcam_active})

    def emit_detections(self, detections: list[dict], source: str = "panel") -> None:
        """Yerel nesne tespiti sonuçlarını Vision paneline yayınlar.

        `source` — "panel" (kullanıcı tara'ya bastı) ya da "assistant" (Chiron
        recognize_objects aracını kendi çağırdı). İkisi de aynı panele düşüyor:
        Chiron bir şey gördüğünde kullanıcı da onu görmeli.
        """
        self._emit(
            "vision_detections",
            {"objects": detections or [], "source": source, "at": time.time()},
        )

    def emit_text(self, lines: list[dict], source: str = "panel") -> None:
        """Yerel OCR sonuçlarını Vision paneline yayınlar.

        Kutu sözleşmesi nesne tespitiyle aynı (normalize x1,y1,x2,y2) — panel
        ikisini de aynı çizim koduyla gösteriyor (bkz. actions/ocr.py).
        """
        self._emit(
            "vision_text",
            {"lines": lines or [], "source": source, "at": time.time()},
        )

    def update_webcam_preview(self, jpeg_bytes: bytes) -> None:
        # Kimse dinlemiyorsa base64 çevirimini hiç yapma: kare başına ~130 KB
        # metin üretip çöpe atmak, webcam açıkken saniyede 8 kez boşa iş demek.
        if not manager.has_clients():
            return
        now = time.monotonic()
        if now - self._last_webcam_frame_at < 1.0 / WEBCAM_PREVIEW_FPS:
            return
        self._last_webcam_frame_at = now
        self._emit("webcam_frame", {"jpeg": base64.b64encode(jpeg_bytes).decode("ascii")})

    # ── Açılış ──────────────────────────────────────────────────────────────
    def wait_for_api_key(self) -> None:
        """ChironLive başlamadan önce API anahtarının varlığını bekler.

        Tkinter sürümü burada bir kurulum penceresi açıyordu. Web sürümünde
        anahtar config'ten okunuyor; yoksa kullanıcıya ne yapacağı söylenip
        beklenir (anahtar dosyaya yazıldığı anda döngü kendiliğinden devam eder,
        uygulamayı yeniden başlatmak gerekmez)."""
        warned = False
        while not str(get_app_config_value("gemini_api_key", "") or "").strip():
            if not warned:
                self.write_log(
                    "ERR: Gemini API anahtarı yok — config/api_keys.json içindeki "
                    '"gemini_api_key" alanını doldur. Chiron anahtar girilir girilmez başlar.'
                )
                warned = True
            time.sleep(1.0)
