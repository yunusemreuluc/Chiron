"""Kullanınca yüklenen, boşta kalınca bellekten çıkan ağır model (2026-10-02).

Kullanıcı isteği (Faz 0): "Onları çalıştırdığımda çalışsın, yoksa çalışmasın."
YOLO-World ve EasyOCR zaten ilk kullanımda yükleniyordu (açılışta bedel yok),
ama bir kez yüklenince süreç kapanana kadar bellekte kalıyordu.

Burada: model ilk `use()` ile yüklenir, son kullanımdan `idle_seconds` sonra
bırakılır. Kullanım sürerken (başka thread'de bile) asla bırakılmaz — sayaç
kilit altında. Bir sonraki kullanım modeli yeniden yükler (birkaç sn).

Sınır: Python bir modülün import'unu geri alamaz. torch/ultralytics/easyocr
kütüphanelerinin kendisi (~yüzlerce MB kod) yüklü kalır; geri verilen, model
ağırlıkları ve çıkarım tamponları.
"""

from __future__ import annotations

import gc
import logging
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator

logger = logging.getLogger("airon")


class IdleModel:
    def __init__(self, name: str, loader: Callable[[], Any], idle_seconds: float = 120.0) -> None:
        self.name = name
        self._loader = loader
        self.idle_seconds = idle_seconds
        self._lock = threading.Lock()
        self._obj: Any = None
        self._users = 0
        self._last_used = 0.0
        self._timer: threading.Timer | None = None

    @property
    def loaded(self) -> bool:
        return self._obj is not None

    @contextmanager
    def use(self) -> Iterator[Any]:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            if self._obj is None:
                started = time.monotonic()
                self._obj = self._loader()  # yükleme hatası çağırana gider
                logger.info("[%s] yüklendi (%.1f sn)", self.name, time.monotonic() - started)
            self._users += 1
            obj = self._obj
        try:
            yield obj
        finally:
            with self._lock:
                self._users -= 1
                self._last_used = time.monotonic()
                if self._users == 0:
                    self._schedule()

    def ensure(self, loader: Callable[[], Any]) -> None:
        """Bu süreçte yükleyiciyi KALICI olarak `loader` yap; model yoksa onunla kur.

        MCP server okuyucuyu indirme kapalı kuruyor (bkz. mcp_server/tools.py).
        Yükleyici kalıcı değişir (Astra incelemesi, 2026-10-02): model boşta
        bırakılıp sonra yeniden kurulursa da varsayılan (indirmeli) yükleyiciye
        dönülmez. Kullanım da sayılır — hemen ardından gelen `use()`'tan önce
        zamanlayıcı modeli bırakmasın.
        """
        with self._lock:
            self._loader = loader
            if self._obj is None:
                self._obj = loader()
            self._last_used = time.monotonic()
            if self._users == 0:
                self._schedule()

    def _schedule(self) -> None:
        # Kilit altında çağrılır.
        if self._timer is not None:
            self._timer.cancel()
        timer = threading.Timer(self.idle_seconds, self._release_if_idle)
        timer.daemon = True
        timer.name = f"airon-idle-{self.name}"
        self._timer = timer
        timer.start()

    def _release_if_idle(self) -> None:
        with self._lock:
            idle = time.monotonic() - self._last_used
            if self._users or self._obj is None or idle < self.idle_seconds - 0.5:
                return
            self._obj = None
            self._timer = None
        gc.collect()
        logger.info("[%s] %d sn kullanılmadı, bellekten çıkarıldı", self.name, int(idle))

    def release(self) -> None:
        """Hemen bırak (kullanımda değilse). Testler ve kapanış için."""
        with self._lock:
            if self._users:
                return
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._obj = None
        gc.collect()
