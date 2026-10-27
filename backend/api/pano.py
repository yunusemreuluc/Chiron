"""Görev panosu uçları — kart aç, başlat, durdur, sonlandır, onayla (Ajan İstasyonu, adım 1).

Kart mantığı `backend/core/pano.py`'de. Uzak istemci için RemoteAccessMiddleware
kapısı geçerli (bütün /api/ yolları PIN'li); yerel istekte Origin denetimi var.
"""

from __future__ import annotations

import asyncio
from typing import Callable

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from backend.core import bekci, pano_git, remote_auth
from backend.core.dongu import dongu
from backend.core.pano import MAX_DETAIL, MAX_TEST_CMD, MAX_TITLE, PanoError, pano

router = APIRouter(prefix="/api/pano", tags=["pano"])


def _ok(data: dict, message: str = "") -> dict:
    return {"success": True, "message": message, "data": data}


async def _run(response: Response, action: Callable[[], dict], message: str) -> dict:
    try:
        card = await asyncio.to_thread(action)
    except PanoError as error:
        response.status_code = 409
        return {"success": False, "message": str(error), "data": {}}
    return _ok({"card": card}, message)


class CardCreate(BaseModel):
    title: str = Field(max_length=MAX_TITLE)
    detail: str = Field(default="", max_length=MAX_DETAIL)
    # Proje kartı: iş bu deponun ayrı bir worktree'sinde yapılır, test Chiron'da koşar.
    repo: str | None = Field(default=None, max_length=400)
    test_cmd: str | None = Field(default=None, max_length=MAX_TEST_CMD)
    # Kartı kim yapacak: claude | codex (Terra) | gemini (yalnız okur).
    agent: str = Field(default="claude", max_length=16)


class CardEdit(BaseModel):
    title: str | None = Field(default=None, max_length=MAX_TITLE)
    detail: str | None = Field(default=None, max_length=MAX_DETAIL)
    agent: str | None = Field(default=None, max_length=16)


class CardAnswer(BaseModel):
    approved: bool


class GuardMode(BaseModel):
    mod: str = Field(max_length=16)


class LoopSwitch(BaseModel):
    acik: bool


@router.get("")
async def list_cards() -> dict:
    data = await asyncio.to_thread(pano.snapshot)
    data["dongu"] = dongu.public()
    return _ok(data)


@router.post("/dongu")
async def switch_loop(body: LoopSwitch) -> dict:
    """7/24 döngüyü aç/kapat. Telefondan da olur: açmak korumayı gevşetmez (bekçi ve kota freni
    aynen geçerli), kapatmak her yerden yapılabilmeli. Kapatmak çalışan işi kesmez."""
    state = await asyncio.to_thread(dongu.set_open, body.acik)
    return _ok({"dongu": state}, "7/24 döngü açık." if body.acik else "7/24 döngü kapandı.")


@router.post("/bekci")
async def set_guard_mode(body: GuardMode, request: Request, response: Response) -> dict:
    """Bekçi modu: uyar (yalnız kaydeder) | engelle (yüksek seviyeli adımı reddeder).
    Yalnızca PC'den — telefon korumayı gevşetemesin (test komutu kuralıyla aynı gerekçe)."""
    if remote_auth.is_remote_scope(request.scope):
        response.status_code = 403
        return {"success": False, "message": "Bekçi modu yalnızca PC'den değiştirilir.", "data": {}}
    if body.mod not in bekci.MODES:
        response.status_code = 400
        return {"success": False, "message": f"Bilinmeyen mod: {body.mod}", "data": {}}
    mode = await asyncio.to_thread(bekci.set_mode, body.mod)
    return _ok({"mod": mode}, "Bekçi engelliyor." if mode == "engelle" else "Bekçi yalnız uyarıyor.")


@router.get("/repos")
async def list_repos() -> dict:
    """Kart açarken seçilecek projeler (~/Projects altındaki git depoları) + önerilen test komutu."""
    return _ok({"repos": await asyncio.to_thread(pano_git.list_repos)})


@router.post("")
async def create_card(body: CardCreate, request: Request, response: Response) -> dict:
    # Test komutu kabukta, Claude'un izin denetimi OLMADAN koşar (Terra incelemesi, kritik):
    # uzaktan (telefon) yalnızca Chiron'un o depo için önerdiği komut kabul edilir.
    # Özel komut ancak PC'nin kendi penceresinden girilir.
    if body.repo and body.test_cmd and remote_auth.is_remote_scope(request.scope):
        try:
            suggested = await asyncio.to_thread(lambda: pano_git.suggest_test(pano_git.repo_root(body.repo or "")))
        except pano_git.GitError:
            suggested = ""
        if body.test_cmd.strip() != suggested:
            response.status_code = 403
            return {
                "success": False,
                "message": "Özel test komutu yalnızca PC'den girilebilir; telefondan önerilen komut ya da boş.",
                "data": {},
            }
    result = await _run(
        response,
        lambda: pano.create(body.title, body.detail, body.repo, body.test_cmd, body.agent),
        "Kart açıldı.",
    )
    dongu.wake()  # döngü açıksa yeni kart bir dakika beklemesin
    return result


@router.patch("/{card_id}")
async def edit_card(card_id: str, body: CardEdit, response: Response) -> dict:
    return await _run(
        response, lambda: pano.edit(card_id, body.title, body.detail, body.agent), "Kart güncellendi."
    )


@router.delete("/{card_id}")
async def delete_card(card_id: str, response: Response) -> dict:
    def action() -> dict:
        pano.delete(card_id)
        return {"id": card_id}

    return await _run(response, action, "Kart silindi.")


@router.post("/{card_id}/start")
async def start_card(card_id: str, response: Response) -> dict:
    return await _run(response, lambda: pano.start(card_id), "Kart ajana verildi.")


@router.post("/{card_id}/plan")
async def plan_card(card_id: str, response: Response) -> dict:
    """Kartı lider ajan Jarvis'e böldürür (salt okunur Claude oturumu, JSON plan → alt kartlar)."""
    return await _run(response, lambda: pano.plan(card_id), "Jarvis planlıyor.")


@router.post("/{card_id}/pause")
async def pause_card(card_id: str, response: Response) -> dict:
    return await _run(response, lambda: pano.pause(card_id), "Durduruluyor.")


@router.post("/{card_id}/stop")
async def stop_card(card_id: str, response: Response) -> dict:
    return await _run(response, lambda: pano.stop(card_id), "Kart sonlandırıldı.")


@router.post("/{card_id}/merge")
async def merge_card(card_id: str, body: CardAnswer, response: Response) -> dict:
    """Test geçmiş kartı ana dala birleştir (approved) ya da reddet."""
    return await _run(
        response,
        lambda: pano.merge(card_id, body.approved),
        "Ana dala birleştirildi." if body.approved else "Reddedildi; dal duruyor.",
    )


@router.post("/{card_id}/answer")
async def answer_card(card_id: str, body: CardAnswer, response: Response) -> dict:
    return await _run(
        response,
        lambda: pano.answer(card_id, body.approved),
        "Onay verildi." if body.approved else "Reddedildi.",
    )
