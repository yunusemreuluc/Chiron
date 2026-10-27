"""Uzaktan erişim (telefon) — kimlik doğrulama ve istek sınıflandırma.

NEDEN (2026-09-15, kullanıcı isteği): "evden uzaktayken telefonumdan PC'mi
kontrol edeceğim". Chiron'un araçları arasında `shell_run`, `control_power`,
`manage_files` var — kimliği doğrulanmamış tek bir uzak istek, makinenin
tamamını teslim etmek demek. Bu yüzden katmanlar:

  1. TAŞIMA — backend hâlâ yalnızca 127.0.0.1'i dinliyor; LAN'a hiç açılmıyor.
     Telefon Tailscale üzerinden geliyor: `tailscale serve` tailnet'e HTTPS
     açıp REMOTE_PORT'a (8001) aktarıyor. Port yönlendirme YOK.
  2. SINIFLANDIRMA — isteğin uzak olup olmadığı, proxy'nin hangi başlıkları
     eklediğine GÜVENİLEREK değil, isteğin GELDİĞİ PORTA bakılarak belirleniyor
     (bkz. desktop.py — tek uvicorn sunucusu iki soketi birden dinliyor).
     Yerel porta proxy başlığıyla ya da yabancı bir Host ile gelen istek de
     uzak sayılıyor: `tailscale serve` yanlışlıkla 8000'e yönlendirilirse kapı
     sessizce açılmasın.
  3. PIN — uzak her istek imzalı bir oturum çerezi taşımak zorunda. Çerez
     PIN'le alınıyor; hatalı denemeler katlanarak kilitleniyor.

Belirsizlikte KAPALI: PIN hiç ayarlanmamışsa uzak giriş tamamen reddediliyor.
Bkz. Notes/Uzaktan-Erisim.md.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Any

from app_config import load_app_config, save_app_config

logger = logging.getLogger("chiron.backend")

# desktop.py bu iki portu AYNI uvicorn sunucusunda dinliyor. Masaüstü penceresi
# LOCAL_PORT'tan, `tailscale serve` REMOTE_PORT'tan geliyor.
LOCAL_PORT = 8000
REMOTE_PORT = 8001

COOKIE_NAME = "chiron_remote"
SESSION_DAYS = 30
MIN_PIN_LENGTH = 6
MAX_PIN_LENGTH = 12

_PBKDF2_ITERATIONS = 240_000

_LOOPBACK_CLIENTS = {"127.0.0.1", "::1"}
_LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "[::1]"}
# Bir ters proxy'nin (tailscale serve dahil) eklediği başlıklar. Yerel porta
# bunlardan biriyle gelen istek, pencereden değil bir proxy'den geliyordur.
_PROXY_HEADERS = {
    b"x-forwarded-for",
    b"x-forwarded-host",
    b"x-forwarded-proto",
    b"forwarded",
    b"tailscale-user-login",
    b"tailscale-user-name",
    b"tailscale-headers-info",
}

# Kimlik doğrulaması OLMADAN uzaktan erişilebilen yollar: giriş ekranının
# kendisi ve onu çizmek için gereken statik dosyalar. Hiçbiri veri taşımıyor.
_PUBLIC_EXACT = {
    "/m",
    "/m/",
    "/m/manifest.webmanifest",
    "/api/remote/login",
    "/api/remote/session",
    "/favicon.ico",
}
_PUBLIC_PREFIXES = ("/_next/static/", "/m/icons/")

# Uzak istemciye yayınlanan WebSocket olayları. Webcam karesi (saniyede 8 kez
# ~130 KB) ve mikrofon seviyesi mobil veride hem pahalı hem anlamsız.
REMOTE_EVENTS = frozenset(
    {"log", "assistant_status", "energy_state", "task_started", "task_finished"}
)


# ── İstek sınıflandırma ──────────────────────────────────────────────────────
def _hostname(host_header: str) -> str:
    host = host_header.strip().lower()
    if host.startswith("["):
        end = host.find("]")
        return host[: end + 1] if end != -1 else host
    return host.split(":", 1)[0]


def is_remote_scope(scope: dict[str, Any]) -> bool:
    """Bu HTTP/WebSocket isteği uzaktan mı geliyor?

    Yerel sayılmak için HEPSİ doğru olmalı: yerel porta gelmiş, istemci
    loopback, proxy başlığı yok, Host yerel. Biri bile tutmazsa uzak.
    """
    server = scope.get("server")
    if not server or server[1] != LOCAL_PORT:
        # Sunucu adresi bilinmiyorsa (ör. test istemcisi) ya da REMOTE_PORT'sa.
        # `uvicorn backend.main:app --port 8000` ile elle çalıştırmada da
        # server[1] == 8000 olduğu için geliştirme akışı etkilenmiyor.
        return True

    client = scope.get("client")
    if not client or client[0] not in _LOOPBACK_CLIENTS:
        return True

    host = ""
    for name, value in scope.get("headers") or []:
        if name in _PROXY_HEADERS:
            return True
        if name == b"host":
            host = value.decode("latin-1")
    return _hostname(host) not in _LOCAL_HOSTNAMES


def is_public_path(path: str) -> bool:
    return path in _PUBLIC_EXACT or path.startswith(_PUBLIC_PREFIXES)


# ── PIN ──────────────────────────────────────────────────────────────────────
def _hash_pin(pin: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_pin(pin: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", pin.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def pin_is_set() -> bool:
    return bool(str(load_app_config().get("remote_pin_hash") or ""))


def set_pin(pin: str) -> None:
    """PIN'i değiştirir. Oturum imzası PIN özetine bağlı olduğundan, PIN
    değişince eski telefon oturumlarının HEPSİ geçersizleşir — kaybolan bir
    telefonun erişimini kesmenin yolu bu."""
    save_app_config({"remote_pin_hash": _hash_pin(pin, secrets.token_bytes(16))})


# ── Oturum çerezi ────────────────────────────────────────────────────────────
def _session_secret() -> bytes:
    config = load_app_config()
    secret = str(config.get("remote_session_secret") or "")
    if not secret:
        secret = secrets.token_hex(32)
        save_app_config({"remote_session_secret": secret})
    return bytes.fromhex(secret)


def _signature(expires: int, pin_hash: str) -> str:
    message = f"{expires}.{pin_hash}".encode("utf-8")
    return hmac.new(_session_secret(), message, hashlib.sha256).hexdigest()


def issue_session() -> tuple[str, int]:
    """Yeni oturum belirteci ve saniye cinsinden ömrü."""
    max_age = SESSION_DAYS * 24 * 3600
    expires = int(time.time()) + max_age
    pin_hash = str(load_app_config().get("remote_pin_hash") or "")
    return f"v1.{expires}.{_signature(expires, pin_hash)}", max_age


def session_is_valid(token: str | None) -> bool:
    if not token:
        return False
    try:
        version, expires_raw, signature = token.split(".")
        expires = int(expires_raw)
    except ValueError:
        return False
    if version != "v1" or expires < time.time():
        return False
    pin_hash = str(load_app_config().get("remote_pin_hash") or "")
    if not pin_hash:
        return False
    return hmac.compare_digest(signature, _signature(expires, pin_hash))


def session_from_scope(scope: dict[str, Any]) -> bool:
    for name, value in scope.get("headers") or []:
        if name != b"cookie":
            continue
        for part in value.decode("latin-1").split(";"):
            key, _, cookie_value = part.strip().partition("=")
            if key == COOKIE_NAME and session_is_valid(cookie_value):
                return True
    return False


# ── Hatalı deneme kilidi ─────────────────────────────────────────────────────
# Süreç genelinde TEK sayaç, IP başına değil: bütün uzak istekler aynı proxy'den
# (127.0.0.1) geliyor, yani IP ayırt edici değil. Tek kullanıcılı bir sistemde
# bu zaten doğru model — PIN'e kim deniyor olursa olsun kapı kilitlenmeli.
_FREE_ATTEMPTS = 5
_BASE_LOCK_SECONDS = 60
_MAX_LOCK_SECONDS = 3600

_failures = 0
_locked_until = 0.0


def lock_remaining() -> int:
    return max(0, int(_locked_until - time.monotonic() + 0.999))


def attempt_login(pin: str) -> tuple[bool, str]:
    """PIN'i dener. (başarılı mı, kullanıcıya gösterilecek mesaj)."""
    global _failures, _locked_until

    remaining = lock_remaining()
    if remaining:
        return False, f"Çok fazla hatalı deneme. {remaining} sn sonra tekrar dene."

    stored = str(load_app_config().get("remote_pin_hash") or "")
    if not stored:
        return False, "Uzaktan erişim PIN'i ayarlanmamış. PC'de Ayarlar → Uzaktan erişim."

    # Uzunluk sınırı hatalı deneme SAYILIYOR: aksi hâlde sınırın dışındaki
    # girdiler kilidi hiç tetiklemeden sonsuz denenebilirdi (zararsız ama
    # "sayaç her denemeyi görür" sözleşmesini bozardı).
    if len(pin) <= MAX_PIN_LENGTH and _verify_pin(pin, stored):
        _failures = 0
        _locked_until = 0.0
        logger.info("Uzaktan erişim: başarılı PIN girişi")
        return True, "giriş yapıldı"

    _failures += 1
    logger.warning("Uzaktan erişim: hatalı PIN denemesi (%d)", _failures)
    if _failures >= _FREE_ATTEMPTS:
        seconds = min(_MAX_LOCK_SECONDS, _BASE_LOCK_SECONDS * 2 ** (_failures - _FREE_ATTEMPTS))
        _locked_until = time.monotonic() + seconds
        return False, f"Hatalı PIN. Giriş {seconds} sn kilitlendi."
    return False, "Hatalı PIN."


# ── ASGI ara katmanı ─────────────────────────────────────────────────────────
class RemoteAccessMiddleware:
    """Uzak her isteği kapıdan geçirir; yerel istekler hiç etkilenmez.

    Saf ASGI, `BaseHTTPMiddleware` değil: o sınıf WebSocket isteklerini
    görmüyor ve `/ws` tam da korunması gereken yollardan biri.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        scope_type = scope.get("type")
        if scope_type not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        remote = is_remote_scope(scope)
        if not origin_allowed(scope, remote):
            if scope_type == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                await _json(send, 403, {"success": False, "message": "Kaynak reddedildi.", "data": {}})
            return

        if not remote:
            await self.app(scope, receive, send)
            return

        # Uç noktalar (ör. voice.py) isteğin uzak olduğunu buradan okuyor —
        # sınıflandırma tek yerde yapılsın, ikinci bir kopya sapmasın.
        scope.setdefault("state", {})["remote"] = True
        path = scope.get("path") or "/"

        if scope_type == "websocket":
            if session_from_scope(scope):
                await self.app(scope, receive, send)
            else:
                await send({"type": "websocket.close", "code": 1008})
            return

        if is_public_path(path) or session_from_scope(scope):
            if path == "/" and scope.get("method") == "GET":
                # Masaüstü arayüzü telefonda anlamsız (1366px hedefli 3D sahne).
                await _redirect(send, "/m/")
                return
            await self.app(scope, receive, send)
            return

        if path == "/" or not path.startswith(("/api/", "/sfx/")):
            await _redirect(send, "/m/")
            return
        await _json(send, 401, {"success": False, "message": "Oturum gerekli.", "data": {}})


# Yerel pencerenin (desktop.py → http://127.0.0.1:8000) ve `npm run dev`'in
# (3000) kaynakları. Başka bir kaynak yerel porta tarayıcıdan ulaşamamalı.
_LOCAL_ORIGINS = frozenset(
    {
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    }
)
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def origin_allowed(scope: dict[str, Any], remote: bool) -> bool:
    """Tarayıcıdan gelen istek bizim sayfamızdan mı geliyor?

    NEDEN (2026-09-15, Astra çapraz incelemesi): tarayıcılar WebSocket'e aynı
    kaynak politikası UYGULAMIYOR. PC'de açılan herhangi bir web sitesi
    `ws://127.0.0.1:8000/ws`'e bağlanıp sohbeti ve webcam karelerini
    okuyabiliyordu — bu açık uzaktan erişimden ÖNCE de vardı, çünkü yerel
    bağlantı hiç denetlenmiyordu. Uzakta ise `SameSite=Strict` tek başına
    yetmiyor: aynı tailnet'teki `baska.tailXXXX.ts.net` ile PC'nin adresi aynı
    "site" sayılıyor ve çerez gidiyor.

    Kural: WebSocket el sıkışması ve durum değiştiren HTTP isteği bir Origin
    taşıyorsa, o Origin bizim olmalı. Origin YOKSA geçiliyor — tarayıcılar bu
    iki durumda Origin'i her zaman gönderiyor; göndermeyen şey tarayıcı değil
    (curl, test istemcisi) ve onu durduran zaten port + çerez.
    """
    if scope.get("type") == "http" and scope.get("method", "GET") in _SAFE_METHODS:
        return True
    origin = ""
    hosts: set[str] = set()
    for name, value in scope.get("headers") or []:
        text = value.decode("latin-1").strip().lower()
        if name == b"origin":
            origin = text
        elif name in (b"host", b"x-forwarded-host") and text:
            hosts.add(text)
    if not origin:
        return True
    if not remote:
        return origin in _LOCAL_ORIGINS
    # Uzak: sayfanın geldiği adresin kendisi. Host YA DA X-Forwarded-Host: bir
    # ters proxy Host'u hedefe (127.0.0.1:8001) yeniden yazabiliyor ve özgün
    # adresi X-Forwarded-Host'ta taşıyor — `tailscale serve`'ün hangisini
    # yaptığına bağımlı kalmamak için ikisi de kabul. Başka bir sitedeki sayfa
    # bu başlığı ayarlayamaz: WebSocket el sıkışmasında ve form gönderiminde
    # özel başlık yok, fetch ile eklemek CORS ön kontrolüne takılıyor.
    # Şema bilerek karşılaştırılmıyor: eşleşmesi gereken şey adresin kendisi.
    origin_host = origin.split("://", 1)[-1]
    return origin_host in hosts


async def _redirect(send: Any, location: str) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 307,
            "headers": [(b"location", location.encode("latin-1")), (b"content-length", b"0")],
        }
    )
    await send({"type": "http.response.body", "body": b""})


async def _json(send: Any, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode("latin-1")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
