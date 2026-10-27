"""CHIRON backend — uygulama ayarları. main.py'deki (masaüstü) app_config.py'den
BAĞIMSIZ — bu sadece FastAPI servisinin kendi çalışma ayarları (host/port/CORS)."""

from __future__ import annotations

HOST = "127.0.0.1"
PORT = 8000

# Next.js dev sunucusu varsayılan olarak 3000 portunda çalışır.
CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
