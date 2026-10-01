"""Yerel görü modelleri ayrı bir alt süreçte (Faz 0, 2026-10-02).

Kullanıcı isteği: "Onları çalıştırdığımda çalışsın, yoksa çalışmasın."

NEDEN ALT SÜREÇ: YOLO-World ve EasyOCR bir kez kullanılınca torch yüzünden Aıron
süreci 1,3–1,8 GB özel bellek tutuyordu ve bunu süreç kapanana kadar bırakmıyordu.
Modeli süreç İÇİNDE bırakmak (core/idle_model.py) ölçüldü ve işe yaramadı: torch'un
ayırıcısı belleği Windows'a iade etmiyor (3 yükle/bırak turunda 1,67–1,77 GB sabit).
Bellek ancak süreç ölünce döner. Bu yüzden: iş gelince alt süreç açılır, 2 dk iş
gelmezse kendini kapatır.

Arayüz `actions.object_recognition.detect_objects_in_jpeg` ve
`actions.ocr.read_text_in_jpeg` ile AYNI imza ve aynı sözleşme: asla exception
fırlatmaz, her zaman liste döner. Alt süreç çökerse / zaman aşımında boş liste
döner ve bir sonraki çağrıda yeniden açılır.

Protokol: stdin/stdout üzerinde 4 bayt uzunluk + pickle çerçeveleri. Alt süreç
açılır açılmaz kendi stdout'unu stderr'e yönlendirir; kütüphanelerin print'leri
protokolü bozamaz (protokol, stdout'un önceden alınmış kopyasından akar).
Pickle yalnız bu sürecin kendi başlattığı çocuğuyla konuşuyor — dışarıya açık değil.

MCP server bu modülü KULLANMAZ: kendi ayrı sürecinde, indirmesiz okuyucuyla
çalışıyor (mcp_server/tools.py).
"""

from __future__ import annotations

import logging
import os
import pickle
import struct
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger("airon")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IDLE_EXIT_SECONDS = float(os.environ.get("AIRON_VISION_IDLE_S", "120"))  # testte kısaltılabilir
# İlk çağrı torch + model yüklemesini de içeriyor (ölçüldü: ~2,5 sn OCR; YOLO-World
# + CLIP daha uzun). Takılan bir çocuk Aıron'u sonsuza dek bekletmesin.
CALL_TIMEOUT_SECONDS = 180.0

_HEADER = struct.Struct("<I")


def _write_frame(stream, obj: Any) -> None:
    data = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    stream.write(_HEADER.pack(len(data)))
    stream.write(data)
    stream.flush()


def _read_frame(stream) -> Any:
    head = stream.read(_HEADER.size)
    if len(head) < _HEADER.size:
        raise EOFError("kanal kapandı")
    (size,) = _HEADER.unpack(head)
    data = stream.read(size)
    if len(data) < size:
        raise EOFError("eksik çerçeve")
    return pickle.loads(data)


# ── Ebeveyn tarafı ───────────────────────────────────────────────────────────
class _Worker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None

    def _start(self) -> subprocess.Popen:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(
            # Ebeveyn pid'i: çocuk onu izler, Aıron ölünce (çağrı ortasında bile) kapanır.
            [sys.executable, "-m", "core.vision_worker", "--child", str(os.getpid())],
            cwd=str(PROJECT_ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        logger.info("[Görü] alt süreç açıldı (pid %s)", proc.pid)
        return proc

    def _kill(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass

    def call(self, kind: str, *args: Any) -> list:
        with self._lock:  # model tek; istekler sırayla
            for attempt in (1, 2):
                if self._proc is None or self._proc.poll() is not None:
                    try:
                        self._proc = self._start()  # boşta kapanmışsa yeniden aç
                    except Exception:
                        # Sözleşme: asla exception fırlatma (Astra incelemesi).
                        logger.warning("[Görü] alt süreç başlatılamadı", exc_info=True)
                        self._proc = None
                        return []
                proc = self._proc
                result: dict[str, Any] = {}

                def exchange() -> None:
                    try:
                        _write_frame(proc.stdin, (kind, args))
                        result["value"] = _read_frame(proc.stdout)
                    except Exception as exc:  # kanal koptu (çocuk boşta kapanmış olabilir)
                        result["error"] = exc

                t = threading.Thread(target=exchange, daemon=True)
                t.start()
                t.join(CALL_TIMEOUT_SECONDS)
                if t.is_alive():
                    logger.warning("[Görü] alt süreç %s sn yanıt vermedi, kapatıldı", int(CALL_TIMEOUT_SECONDS))
                    self._kill()
                    return []
                if "value" in result:
                    value = result["value"]
                    return value if isinstance(value, list) else []
                # Çocuk tam bu anda boşta kapandıysa bir kez yeniden dene.
                self._kill()
                if attempt == 2:
                    logger.warning("[Görü] alt süreç hatası: %s", result.get("error"))
            return []

    def shutdown(self) -> None:
        with self._lock:
            self._kill()


_worker = _Worker()


def detect_objects_in_jpeg(jpeg_bytes: bytes, extra_vocabulary: list[str] | None = None) -> list[dict]:
    from actions.object_recognition import HAS_PIL, HAS_ULTRALYTICS

    if not HAS_ULTRALYTICS or not HAS_PIL:
        return []  # çocuk açmaya değmez
    return _worker.call("detect", jpeg_bytes, list(extra_vocabulary or []))


def read_text_in_jpeg(jpeg_bytes: bytes) -> list[dict]:
    from actions.ocr import HAS_EASYOCR, HAS_PIL

    if not HAS_EASYOCR or not HAS_PIL:
        return []
    return _worker.call("ocr", jpeg_bytes)


def shutdown() -> None:
    _worker.shutdown()


# ── Çocuk tarafı ─────────────────────────────────────────────────────────────
def _watch_parent() -> None:
    """Aıron ölünce çocuğu hemen kapat — model çağrısının ORTASINDA olsa bile.

    Astra incelemesi (2026-10-02): kapanma yalnız ana döngüde kontrol edildiği
    için ebeveyn uzun bir çağrı sırasında ölürse çocuk yetim kalıyordu.
    os._exit: ana thread model içinde bloklu olabilir, temiz çıkış beklenmez.
    """
    if len(sys.argv) < 3 or not sys.argv[-1].isdigit():
        return
    parent_pid = int(sys.argv[-1])
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, parent_pid)
    except Exception:
        return
    if not handle:
        os._exit(0)  # ebeveyn zaten yok

    def watch() -> None:
        kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)  # ebeveyn ölene kadar
        os._exit(0)

    threading.Thread(target=watch, daemon=True, name="airon-vision-parent").start()


def _child_main() -> int:
    # Protokol kanalı: stdout'un kopyası. Sonra fd 1'i stderr'e çevir — model
    # kütüphanelerinin print'leri protokolü bozmasın.
    proto_out = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    # Girdi de aynı şekilde: protokol stdin'in KOPYASINDAN okunur, fd 0 NUL'a çevrilir.
    # NEDEN (ölçüldü, 2026-10-02): okuyucu thread stdin pipe'ında bloklu beklerken
    # model kütüphanelerinden biri import sırasında stdin'e dokunuyor; Windows senkron
    # G/Ç'yi dosya nesnesi başına sıraya soktuğu için o çağrı da bekliyor → OCR hiç
    # bitmiyor, ebeveyn 180 sn sonra zaman aşımına düşüyordu.
    proto_in = os.fdopen(os.dup(0), "rb")
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    os.close(devnull)
    sys.stdin = open(os.devnull, "r")

    import queue

    requests: "queue.Queue[Any]" = queue.Queue()

    def reader() -> None:
        while True:
            try:
                requests.put(_read_frame(proto_in))
            except Exception:
                requests.put(None)  # ebeveyn gitti
                return

    threading.Thread(target=reader, daemon=True).start()
    _watch_parent()

    while True:
        try:
            item = requests.get(timeout=IDLE_EXIT_SECONDS)
        except queue.Empty:
            return 0  # boşta: kapan, bellek işletim sistemine dönsün
        if item is None:
            return 0
        kind, args = item
        try:
            if kind == "detect":
                from actions.object_recognition import detect_objects_in_jpeg as fn
            elif kind == "ocr":
                from actions.ocr import read_text_in_jpeg as fn
            else:
                raise ValueError(kind)
            value = fn(*args)
        except Exception:
            value = []
        try:
            _write_frame(proto_out, value)
        except Exception:
            return 0


if __name__ == "__main__" and "--child" in sys.argv:
    sys.exit(_child_main())
