"""Uzaktan erişim uçları — telefon girişi, oturum durumu, PIN ayarı, geçmiş.

Kapının kendisi `backend/core/remote_auth.py` içindeki ara katman; buradaki
uçlar yalnızca çerezi veriyor/alıyor. Bkz. Notes/Uzaktan-Erisim.md.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from backend.core import claude_jobs, commands, desktop_control, feature_requests, remote_auth
from backend.websocket.manager import manager

router = APIRouter(prefix="/api/remote", tags=["remote"])


def is_remote(request: Request) -> bool:
    return bool(getattr(request.state, "remote", False))


@router.get("/session")
async def session(request: Request) -> dict:
    """Telefon arayüzü açılışta sorar: giriş ekranı mı, sohbet mi?"""
    remote = is_remote(request)
    authenticated = (not remote) or remote_auth.session_from_scope(request.scope)
    return {
        "success": True,
        "message": "oturum",
        "data": {
            "authenticated": authenticated,
            "remote": remote,
            "pinSet": remote_auth.pin_is_set(),
            "lockedSeconds": remote_auth.lock_remaining(),
        },
    }


class LoginRequest(BaseModel):
    pin: str


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response) -> dict:
    if not is_remote(request):
        # Yerel pencere zaten yetkili; çerez vermenin anlamı yok.
        return {"success": True, "message": "yerel istemci", "data": {}}

    ok, message = remote_auth.attempt_login(body.pin.strip())
    if not ok:
        response.status_code = 401
        return {"success": False, "message": message, "data": {}}

    token, max_age = remote_auth.issue_session()
    response.set_cookie(
        remote_auth.COOKIE_NAME,
        token,
        max_age=max_age,
        httponly=True,
        # Uzak trafik yalnızca `tailscale serve` üzerinden, yani HTTPS geliyor.
        secure=True,
        samesite="strict",
        path="/",
    )
    return {"success": True, "message": message, "data": {}}


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(remote_auth.COOKIE_NAME, path="/", secure=True, samesite="strict")
    return {"success": True, "message": "çıkış yapıldı", "data": {}}


class PinUpdate(BaseModel):
    pin: str


@router.get("/config")
async def read_config(request: Request) -> dict:
    """Ayarlar paneli için — yalnızca yerel pencere."""
    if is_remote(request):
        return {"success": False, "message": "Bu ayar yalnızca PC'den okunabilir.", "data": {}}
    return {
        "success": True,
        "message": "uzaktan erişim",
        "data": {
            "pinSet": remote_auth.pin_is_set(),
            "minPinLength": remote_auth.MIN_PIN_LENGTH,
            "maxPinLength": remote_auth.MAX_PIN_LENGTH,
            "remotePort": remote_auth.REMOTE_PORT,
        },
    }


@router.post("/pin")
async def update_pin(body: PinUpdate, request: Request) -> dict:
    """PIN'i ayarlar/değiştirir. Telefondan DEĞİŞTİRİLEMEZ: çalınan bir oturum
    PIN'i değiştirip gerçek sahibini kilitleyebilirdi."""
    if is_remote(request):
        return {"success": False, "message": "PIN yalnızca PC'den değiştirilebilir.", "data": {}}
    pin = body.pin.strip()
    # Yalnızca rakam: telefonda giriş ekranı sayısal klavye açıyor. Harfli bir
    # PIN kabul edilseydi o klavyeyle girilemez, kullanıcı dışarıda kilitli kalırdı.
    if not (pin.isascii() and pin.isdigit()) or not (
        remote_auth.MIN_PIN_LENGTH <= len(pin) <= remote_auth.MAX_PIN_LENGTH
    ):
        return {
            "success": False,
            "message": (
                f"PIN {remote_auth.MIN_PIN_LENGTH}-{remote_auth.MAX_PIN_LENGTH} haneli, "
                "yalnızca rakam olmalı."
            ),
            "data": {},
        }
    remote_auth.set_pin(pin)
    await manager.close_remote()
    return {"success": True, "message": "PIN kaydedildi — eski telefon oturumları kapandı.", "data": {}}


@router.get("/history")
async def history() -> dict:
    """Son sohbet satırları.

    Telefonda ekran kilitlenince tarayıcı WebSocket'i kapatıyor; o arada gelen
    cevap canlı akışta kaçıyor. Telefon her yeniden bağlanışta buradan
    tamamlıyor (bkz. core/web_ui.py log geçmişi).
    """
    lines = commands.read_provider("log_history")
    return {"success": True, "message": "geçmiş", "data": {"lines": lines or []}}


class ToggleCommand(BaseModel):
    value: bool


@router.post("/mode")
async def set_remote_mode(command: ToggleCommand) -> dict:
    """Uzak modu elle aç/kapat (telefondan da PC'den de)."""
    if not commands.dispatch("remote_mode", {"value": command.value}):
        return {"success": False, "message": "Sesli asistan çalışmıyor.", "data": {}}
    return {"success": True, "message": "güncellendi", "data": {"remote": command.value}}


# ── Telefondaki Aıron'un masaüstü köprüsü (2026-09-15) ───────────────────────
# Android uygulaması (airon-mobile) bu uçları kendi araçlarından çağırıyor.
# Hepsi uzak kapının arkasında: PIN oturumu olmadan ulaşılamaz.

ASK_TIMEOUT_SECONDS = 90.0
_ask_lock = asyncio.Lock()
# update_memory oku-birleştir-yaz yapıyor; eşzamanlı iki not birbirini ezmesin.
_note_lock = asyncio.Lock()


class AskRequest(BaseModel):
    text: str


@router.post("/ask")
async def ask_desktop(body: AskRequest) -> dict:
    """PC'deki Aıron'a sorar ve CEVABI BEKLER (`query_desktop_airon`).

    `/api/voice/text` gönder-unut; cevap WebSocket'e log olarak düşüyor. Telefon
    ise cevabı kendi sesiyle okuyacak, yani HTTP cevabında metni istiyor.
    Sorular sıraya giriyor (bkz. core/web_ui.py _handle_ask).
    """
    text = body.text.strip()
    if not text:
        return {"success": False, "message": "boş soru", "data": {}}
    if not commands.is_ready():
        return {"success": False, "message": "PC'deki Aıron hazır değil.", "data": {}}

    async with _ask_lock:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[tuple[str, bool]] = loop.create_future()

        def on_answer(answer: str, ok: bool) -> None:
            def settle() -> None:
                if not future.done():
                    future.set_result((answer, ok))

            loop.call_soon_threadsafe(settle)

        if not commands.dispatch("ask", {"text": text, "on_answer": on_answer}):
            return {"success": False, "message": "Sesli asistan çalışmıyor.", "data": {}}
        try:
            answer, ok = await asyncio.wait_for(future, ASK_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            commands.dispatch("ask_cancel", {})
            return {"success": False, "message": "PC'deki Aıron zamanında cevap vermedi.", "data": {}}
    return {"success": ok, "message": "cevap" if ok else answer, "data": {"answer": answer}}


class DesktopCommand(BaseModel):
    action: str
    text: str = ""


@router.post("/desktop")
async def desktop_command(body: DesktopCommand) -> dict:
    """Beyaz listedeki masaüstü komutları (`send_desktop_command`)."""
    if body.action not in desktop_control.ACTIONS:
        return {
            "success": False,
            "message": f"Bilinmeyen komut. Geçerli: {', '.join(desktop_control.ACTIONS)}",
            "data": {},
        }
    ok, message = await asyncio.to_thread(desktop_control.execute, body.action, body.text)
    return {"success": ok, "message": message, "data": {"action": body.action}}


class NoteRequest(BaseModel):
    text: str
    source: str = "telefon"


@router.post("/note")
async def save_note(body: NoteRequest) -> dict:
    """Telefonda alınan hızlı notu PC hafızasına da yazar (`save_quick_note`).

    `notes` kategorisine zaman damgalı anahtarla gidiyor: PC'deki Aıron sonraki
    oturumda bunu sistem promptunda görür, Hafıza panelinde de listelenir.
    """
    import datetime
    import secrets

    from memory.memory_manager import update_memory

    text = body.text.strip()
    if not text:
        return {"success": False, "message": "boş not", "data": {}}
    # Saniye çözünürlüklü anahtar aynı saniyedeki iki notu tek kayda birleştiriyordu
    # (Astra incelemesi) — mikrosaniye + rastgele ek.
    key = "not_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + secrets.token_hex(2)
    async with _note_lock:
        await asyncio.to_thread(
            update_memory, {"notes": {key: {"value": text, "source": body.source}}}
        )
    return {"success": True, "message": "Not PC hafızasına yazıldı.", "data": {"key": key}}


# ── Telefondaki Aıron'un istek listesi (2026-09-17) ─────────────────────────


class FeatureRequest(BaseModel):
    id: str
    title: str
    said: str = ""
    attempted: str = ""
    device: str = ""
    at: str = ""
    detail: str = Field(default="", max_length=1500)


@router.post("/requests")
async def add_feature_request(body: FeatureRequest) -> dict:
    """Telefonun yapamadığı bir işi istek listesine ekler."""
    import datetime

    at = body.at.strip() or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        result = await asyncio.to_thread(
            feature_requests.add,
            body.id,
            body.title,
            body.said,
            body.attempted,
            body.device,
            at,
            body.detail,
        )
    except ValueError as error:
        return {"success": False, "message": str(error), "data": {}}
    return {
        "success": True,
        "message": f"İstek listeye eklendi ({result['number']}).",
        "data": result,
    }


@router.get("/requests/list")
async def list_feature_requests() -> dict:
    """PC'deki istek listesinin özetini döndürür."""
    items = await asyncio.to_thread(feature_requests.list_items)
    return {"success": True, "message": "istek listesi", "data": {"items": items}}


@router.get("/requests/done")
async def completed_feature_requests() -> dict:
    """Telefonda henüz bildirilmeyen tamamlanmış istekleri döndürür."""
    items = await asyncio.to_thread(feature_requests.pending_done)
    return {"success": True, "message": "tamamlanan istekler", "data": {"items": items}}


class FeatureRequestAck(BaseModel):
    numbers: list[str]


@router.post("/requests/ack")
async def acknowledge_feature_requests(body: FeatureRequestAck) -> dict:
    """Telefonun kullanıcıya haber verdiği istekleri işaretler."""
    updated = await asyncio.to_thread(feature_requests.mark_notified, body.numbers)
    return {"success": True, "message": "bildirimler güncellendi", "data": {"updated": updated}}


# ── Telefondan Claude Code'a iş (Faz 1, 2026-10-03) ──────────────────────────
# Bkz. backend/core/claude_jobs.py ve Notes/Plan-Claude-Entegrasyonu.md § Faz 1.
# Kapı: /api/remote/* public değil — uzaktan PIN oturumu şart.


class ClaudeJobRequest(BaseModel):
    task: str = Field(max_length=claude_jobs.MAX_TASK_CHARS)
    # Dolu ise o işin oturumunu sürdürür (onay cevabı, "bir de şunu ekle").
    resume_of: str | None = Field(default=None, max_length=32)


@router.post("/claude")
async def start_claude_job(body: ClaudeJobRequest, response: Response) -> dict:
    try:
        job = await asyncio.to_thread(claude_jobs.jobs.submit, body.task, body.resume_of)
    except ValueError as error:
        response.status_code = 409
        return {"success": False, "message": str(error), "data": {}}
    data = claude_jobs.jobs.get(job.id) or job.public()
    return {"success": True, "message": "İş Claude'a verildi.", "data": data}


@router.get("/claude")
async def list_claude_jobs() -> dict:
    return {"success": True, "message": "işler", "data": {"jobs": claude_jobs.jobs.list()}}


# Sabit yollar {job_id}'den ÖNCE: yoksa "updates" bir iş kimliği sanılır.
@router.get("/claude/updates")
async def claude_job_updates() -> dict:
    """Telefona henüz söylenmemiş sonuçlar (bitti / onay bekliyor / hata)."""
    return {"success": True, "message": "güncellemeler", "data": {"jobs": claude_jobs.jobs.updates()}}


class ClaudeJobAck(BaseModel):
    ids: list[str] = Field(max_length=50)


@router.post("/claude/ack")
async def acknowledge_claude_jobs(body: ClaudeJobAck) -> dict:
    count = await asyncio.to_thread(claude_jobs.jobs.acknowledge, body.ids)
    return {"success": True, "message": "işaretlendi", "data": {"updated": count}}


@router.get("/claude/{job_id}")
async def claude_job_status(job_id: str, response: Response) -> dict:
    data = claude_jobs.jobs.get(job_id)
    if data is None:
        response.status_code = 404
        return {"success": False, "message": "Böyle bir iş yok.", "data": {}}
    return {"success": True, "message": data["status"], "data": data}


@router.post("/claude/{job_id}/cancel")
async def cancel_claude_job(job_id: str) -> dict:
    ok = await asyncio.to_thread(claude_jobs.jobs.cancel, job_id)
    return {
        "success": ok,
        "message": "İptal edildi." if ok else "İş bulunamadı ya da zaten bitmiş.",
        "data": {},
    }
