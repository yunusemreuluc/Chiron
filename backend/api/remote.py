"""Uzaktan erişim uçları — telefon girişi, oturum durumu, PIN ayarı, geçmiş.

Kapının kendisi `backend/core/remote_auth.py` içindeki ara katman; buradaki
uçlar yalnızca çerezi veriyor/alıyor. Bkz. Notes/Uzaktan-Erisim.md.
"""

from __future__ import annotations

import asyncio
import ctypes
import json
from collections.abc import Callable
from ctypes import wintypes
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.api import system as system_api
from backend.core import apk_teslim, claude_jobs, commands, desktop_control, feature_requests, remote_auth
from backend.core.ofis import WAITING, WORKING, office as office_state
from backend.core.sohbet import SohbetError, sohbet
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


# ── Telefondaki Chiron'un masaüstü köprüsü (2026-09-15) ───────────────────────
# Android uygulaması (chiron-mobile) bu uçları kendi araçlarından çağırıyor.
# Hepsi uzak kapının arkasında: PIN oturumu olmadan ulaşılamaz.

ASK_TIMEOUT_SECONDS = 90.0
_ask_lock = asyncio.Lock()
# update_memory oku-birleştir-yaz yapıyor; eşzamanlı iki not birbirini ezmesin.
_note_lock = asyncio.Lock()


def _short(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _read_context() -> dict[str, Any]:
    # `/api/system/context` ile aynı kaynak; ekran görüntüsü/OCR yok.
    from actions.ambient_context import read_context

    return read_context()


def _locked_status() -> bool | None:
    """Windows giriş masaüstüne geçilemiyorsa ekran kilitlidir; bilinemezse null."""
    try:
        user32 = ctypes.windll.user32
        open_desktop = user32.OpenInputDesktop
        open_desktop.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        open_desktop.restype = wintypes.HANDLE
        switch_desktop = user32.SwitchDesktop
        switch_desktop.argtypes = (wintypes.HANDLE,)
        switch_desktop.restype = wintypes.BOOL
        close_desktop = user32.CloseDesktop
        close_desktop.argtypes = (wintypes.HANDLE,)
        close_desktop.restype = wintypes.BOOL

        desktop = open_desktop(0, False, 0x0100)  # DESKTOP_SWITCHDESKTOP
        if not desktop:
            return None
        try:
            return not bool(switch_desktop(desktop))
        finally:
            close_desktop(desktop)
    except Exception:
        return None


def _pc_status() -> dict[str, object]:
    metrics = system_api.read_pc_metrics()
    try:
        idle_seconds: float | None = float(_read_context()["idle_seconds"])
    except Exception:
        idle_seconds = None

    data: dict[str, object] = {
        "uptime_minutes": metrics["uptime_minutes"],
        "cpu_percent": metrics["cpu_percent"],
        "ram_percent": metrics["ram_percent"],
        "idle_seconds": idle_seconds,
        "locked": _locked_status(),
    }
    if "battery" in metrics:
        data["battery"] = metrics["battery"]
    return data


def _foreground_status() -> dict[str, str | None] | None:
    context = _read_context()
    app = _short(context.get("app"), 80)
    title = _short(context.get("window_title"), 80)
    if not app and not title:
        return None
    return {"app": app or None, "title": title or None}


def _claude_status() -> dict[str, list[dict[str, object]]]:
    listed = claude_jobs.jobs.list()
    active = [
        {
            "id": job.get("id"),
            "status": job.get("status"),
            "last_step": _short(job.get("last_step"), 160),
            "elapsed_seconds": job.get("elapsed_seconds", 0),
            "task": _short(job.get("task"), 120),
        }
        for job in listed
        if job.get("status") in claude_jobs.ACTIVE
    ]
    finished = sorted(
        (
            job
            for job in listed
            if job.get("status") not in claude_jobs.ACTIVE and job.get("finished_at") is not None
        ),
        key=lambda job: float(job.get("finished_at") or 0),
        reverse=True,
    )[:3]
    recent = [
        {
            "id": job.get("id"),
            "status": job.get("status"),
            "summary": _short(job.get("summary"), 300),
            # Onay normalde tek cümle; boyut sözleşmesini bozan hatalı kayıtları da sınırla.
            "approval": _short(job.get("approval"), 300),
            "finished_at": job.get("finished_at"),
        }
        for job in finished
    ]
    return {"active": active, "recent": recent}


def _office_status() -> list[dict[str, str]]:
    try:
        workers = office_state.snapshot().get("workers", [])
    except Exception:
        return []
    active = []
    for worker in workers:
        if worker.get("status") not in (WORKING, WAITING):
            continue
        active.append(
            {
                "name": _short(worker.get("name"), 80),
                "status": _short(worker.get("status"), 40),
                "task": _short(
                    worker.get("current") or worker.get("title") or worker.get("brief"), 100
                ),
            }
        )
        if len(active) == 5:
            break
    return active


def _assistant_status() -> dict[str, bool]:
    return {"voice_ready": bool(commands.is_ready())}


async def _status_section(reader: Callable[[], Any]) -> Any:
    try:
        return await asyncio.to_thread(reader)
    except Exception:
        return None


def _fit_status_response(response: dict[str, Any], limit: int = 4096) -> None:
    """Değişken metinleri gerekirse kısaltarak UTF-8 JSON yanıtını 4 KB altında tutar."""
    data = response["data"]
    slots: list[tuple[dict[str, Any], str]] = []
    foreground = data.get("foreground")
    if isinstance(foreground, dict):
        slots.extend((foreground, key) for key in ("app", "title"))
    claude = data.get("claude")
    if isinstance(claude, dict):
        for job in claude.get("active", []):
            slots.extend((job, key) for key in ("last_step", "task"))
        for job in claude.get("recent", []):
            slots.extend((job, key) for key in ("summary", "approval"))
    for worker in data.get("office") or []:
        slots.extend((worker, key) for key in ("name", "task"))

    def size() -> int:
        return len(json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    while size() >= limit:
        candidates = [
            (len(value.encode("utf-8")), owner, key, value)
            for owner, key in slots
            if isinstance((value := owner.get(key)), str) and value
        ]
        if not candidates:
            break
        _, owner, key, value = max(candidates, key=lambda item: item[0])
        owner[key] = value[: max(0, len(value) // 2)]


@router.get("/status")
async def remote_status() -> dict:
    """Telefondan, sesli Chiron oturumuna sormadan okunabilen kısa PC özeti."""
    pc, foreground, claude, office, assistant = await asyncio.gather(
        _status_section(_pc_status),
        _status_section(_foreground_status),
        _status_section(_claude_status),
        _status_section(_office_status),
        _status_section(_assistant_status),
    )
    response = {
        "success": True,
        "message": "PC durumu",
        "data": {
            "pc": pc,
            "foreground": foreground,
            "claude": claude,
            "office": office,
            "assistant": assistant,
        },
    }
    _fit_status_response(response)
    return response


class AskRequest(BaseModel):
    text: str


@router.post("/ask")
async def ask_desktop(body: AskRequest) -> dict:
    """PC'deki Chiron'a sorar ve CEVABI BEKLER (`query_desktop_chiron`).

    `/api/voice/text` gönder-unut; cevap WebSocket'e log olarak düşüyor. Telefon
    ise cevabı kendi sesiyle okuyacak, yani HTTP cevabında metni istiyor.
    Sorular sıraya giriyor (bkz. core/web_ui.py _handle_ask).
    """
    text = body.text.strip()
    if not text:
        return {"success": False, "message": "boş soru", "data": {}}
    if not commands.is_ready():
        return {"success": False, "message": "PC'deki Chiron hazır değil.", "data": {}}

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
            return {"success": False, "message": "PC'deki Chiron zamanında cevap vermedi.", "data": {}}
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

    `notes` kategorisine zaman damgalı anahtarla gidiyor: PC'deki Chiron sonraki
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


# ── Telefondaki Chiron'un istek listesi (2026-09-17) ─────────────────────────


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


class FeatureRequestRemove(BaseModel):
    number: str = Field(max_length=16)


@router.post("/requests/remove")
async def remove_feature_request(body: FeatureRequestRemove) -> dict:
    """İsteği geçmişini koruyarak normal listeden kaldırır."""
    try:
        result = await asyncio.to_thread(feature_requests.remove, body.number)
    except ValueError as error:
        return {"success": False, "message": str(error), "data": {}}
    return {
        "success": True,
        "message": f"{result['number']} listeden kaldırıldı.",
        "data": result,
    }


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


# ── APK teslimi (2026-10-29) — bkz. backend/core/apk_teslim.py ─────────────────
# adb yalnız Wi-Fi'da çalışıyor; telefon APK'yı buradan indirip kendisi "Yükle" bildirimi gösterir.


@router.get("/apk")
async def list_apks() -> dict:
    items = await asyncio.to_thread(apk_teslim.listing)
    return {"success": True, "message": "apk", "data": {"apks": items}}


@router.get("/apk/{apk_id}/indir")
async def download_apk(apk_id: str, response: Response):
    try:
        item, path = await asyncio.to_thread(apk_teslim.file_for, apk_id)
    except apk_teslim.ApkError as error:
        response.status_code = 404
        return {"success": False, "message": str(error), "data": {}}
    return FileResponse(
        path,
        media_type="application/vnd.android.package-archive",
        filename=f"{item['name']}.apk",
        headers={"X-Chiron-Sha256": item["sha256"]},
    )


# ── Telefondan sesli iş → Komuta sohbeti (2026-10-29) ─────────────────────────
# Yunus: "Claude'a iş verdim gibi olmasın, hemen hallediyorum desin; Komuta'dan kopuk kalmasın."
# Sesli Chiron'un işi ayrı bir tek seferlik iş değil, PC'deki son Komuta sohbetine yazılır
# (aynı Claude oturumu sürer); telefondaki Komuta ekranı da aynı sohbeti gösterir.


class KomutaTask(BaseModel):
    text: str = Field(max_length=claude_jobs.MAX_TASK_CHARS)
    new_topic: bool = False  # öncekiyle ilgisiz iş: yeni sohbet aç


class KomutaAnswer(BaseModel):
    job_id: str = Field(max_length=32)
    approved: bool


def _komuta_result(chat: dict) -> dict:
    last = chat["messages"][-1] if chat.get("messages") else {}
    return {"chat_id": chat["id"], "title": chat["title"], "job_id": last.get("job_id"), "status": last.get("status")}


@router.post("/komuta")
async def komuta_task(body: KomutaTask, response: Response) -> dict:
    try:
        chat = await asyncio.to_thread(sohbet.phone_task, body.text, body.new_topic)
    except SohbetError as error:
        response.status_code = 409
        return {"success": False, "message": str(error), "data": {}}
    return {"success": True, "message": "İş başladı.", "data": _komuta_result(chat)}


@router.post("/komuta/onay")
async def komuta_answer(body: KomutaAnswer, response: Response) -> dict:
    try:
        chat = await asyncio.to_thread(sohbet.answer_job, body.job_id, body.approved)
    except SohbetError as error:
        response.status_code = 409
        return {"success": False, "message": str(error), "data": {}}
    return {"success": True, "message": "Cevap iletildi.", "data": _komuta_result(chat)}


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
    # `active`: telefon "son 10" listesinden çıkarım yapmasın, süren iş varsa yoklamayı sürdürsün.
    return {"success": True, "message": "güncellemeler", "data": claude_jobs.jobs.updates_snapshot()}


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
