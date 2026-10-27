"""
Kalıcı dosya loglaması.

Eskiden tüm sistem/hata mesajları print() ile yazılıyordu — bu, uygulama
CHIRON.bat üzerinden pythonw.exe (konsolsuz) ile başlatıldığında hiçbir yere
gitmeden kayboluyordu. Üretimde "neden başarısız oldu" sorusuna cevap
verebilmek için tüm print() çağrıları logging modülüne taşınıyor; bu modül
o logger'ı logs/chiron.log dosyasına (döner, sınırlı boyutlu) yazacak şekilde
kurar.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "chiron.log"

_configured = False


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Root logger'ı bir kez kurar — sonraki çağrılar no-op. Her modül kendi
    `logging.getLogger(__name__)` logger'ını kullanabilir, hepsi aynı dosyaya
    akar."""
    global _configured
    root = logging.getLogger()
    if _configured:
        return root

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # pythonw.exe ile calisirken sys.stdout None olabilir — konsol varsa (normal
    # `python main.py` ile calistirilirsa) oraya da yazsin, yoksa sessizce atla.
    if sys.stdout is not None:
        try:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            root.addHandler(console_handler)
        except Exception:
            pass

    root.setLevel(level)
    _configured = True
    return root
