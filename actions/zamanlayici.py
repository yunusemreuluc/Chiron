"""Sesli zamanlayıcı ve kısa hatırlatıcı (2026-11-04, kendini geliştirme K-014).

"10 dakika sonra çayı hatırlat", "25 dakikalık zamanlayıcı kur", "saat 15:30'da toplantıyı hatırlat",
"ne kadar kaldı?", "çay zamanlayıcısını iptal et". Önceden `add_reminder` Windows'ta yalnız tarayıcıda
Microsoft To-Do açıyordu — sesle kurulup zamanı gelince SESLE haber veren bir şey yoktu.

Desen Alexa'nın adlı zamanlayıcıları: her zamanlayıcının bir adı var, dolunca adı söylenir ("çay hazır"),
sorma ve iptal ada göre yapılır (developer.amazon.com/docs/alexa-voice-service/enable-named-timers-and-reminders).

Haber yolu araştırma panosuyla aynı: dolan zamanlayıcı `pop_due()` ile alınır, main.py `_watch_timers`
saniyede bir bakar ve proaktif sistem mesajı olarak Chiron'a söyletir. Chiron konuşurken ya da
duraklatılmışken dolan zamanlayıcı listede kalır, sonraki uygun anda söylenir — kaybolmaz.

Bilinçli sınır: zamanlayıcılar bellekte; Chiron kapanırsa gider. Günlerce sonraki hatırlatma için
`add_reminder`/takvim var, bu araç en fazla 24 saat ileriye kurulur.
"""

from __future__ import annotations

import itertools
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any

from actions.tool_result import fail, ok
from core.tool_registry import register_tool

ACTIONS = ("set", "list", "cancel")
MAX_SECONDS = 24 * 60 * 60

_lock = threading.Lock()
_timers: list[dict[str, Any]] = []  # {id, label, due (epoch), seconds (kurulan süre)}
_ids = itertools.count(1)


# ── Biçimleme ────────────────────────────────────────────────────────────────
def spoken_duration(seconds: float) -> str:
    """Sesle okunacak süre: '1 saat 5 dakika', '40 saniye'. Saniye yalnız bir dakikanın altında söylenir."""
    total = max(0, int(round(seconds)))
    if total < 60:
        return f"{total} saniye"
    hours, rest = divmod(total, 3600)
    minutes = (rest + 30) // 60 if hours else round(rest / 60)
    if minutes == 60:
        hours, minutes = hours + 1, 0
    parts = []
    if hours:
        parts.append(f"{hours} saat")
    if minutes:
        parts.append(f"{minutes} dakika")
    return " ".join(parts) or "1 dakika"


def _clock(epoch: float) -> str:
    return datetime.fromtimestamp(epoch).strftime("%H:%M")


def _lik(text: str) -> str:
    """'-lık/-lik' eki ünlü uyumuyla: '10 dakikalık', '1 saatlik', '40 saniyelik'."""
    if text.endswith("saat"):  # alıntı kelime, ince ek alır: saatlik
        return text + "lik"
    vowels = [c for c in text.lower() if c in "aıoueiöü"]
    return text + ("lık" if vowels and vowels[-1] in "aıou" else "lik")


def _name(timer: dict[str, Any]) -> str:
    return timer["label"] or f"{_lik(spoken_duration(timer['seconds']))} zamanlayıcı"


# ── Süre çözme ───────────────────────────────────────────────────────────────
def resolve_seconds(minutes: float = 0, seconds: float = 0, at: str = "", now: datetime | None = None) -> float:
    """Kurulacak süreyi saniye olarak döner; geçersizse ValueError (mesajı kullanıcıya gider)."""
    at = (at or "").strip()
    if at:
        match = re.fullmatch(r"(\d{1,2})[:.](\d{2})", at)
        if not match or int(match.group(1)) > 23 or int(match.group(2)) > 59:
            raise ValueError(f"Saati anlayamadım: '{at}'. SS:DD biçiminde ver, örneğin 15:30.")
        now = now or datetime.now()
        target = now.replace(hour=int(match.group(1)), minute=int(match.group(2)), second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)  # "saat 9'da" dendi ve 9 geçtiyse yarın 9
        return (target - now).total_seconds()
    total = float(minutes or 0) * 60 + float(seconds or 0)
    if total <= 0:
        raise ValueError("Süre ya da saat söylenmedi — kaç dakika sonra ya da saat kaçta?")
    if total > MAX_SECONDS:
        raise ValueError("Zamanlayıcı en fazla 24 saat ileriye kurulabiliyor; daha ilerisi için hatırlatıcı ekleyeyim.")
    return total


def _find(label: str) -> list[dict[str, Any]]:
    """Ada göre eşleşenler (büyük/küçük harf duyarsız, parça eşleşmesi). Kilit altında çağrılır."""
    key = (label or "").strip().casefold()
    if not key:
        return list(_timers)
    exact = [t for t in _timers if t["label"].casefold() == key]
    return exact or [t for t in _timers if key in t["label"].casefold()]


# ── Araç ─────────────────────────────────────────────────────────────────────
@register_tool("set_timer")
def set_timer(action: str = "set", minutes: float = 0, seconds: float = 0, at: str = "", label: str = "") -> dict:
    action = (action or "set").strip().lower()
    label = (label or "").strip()
    now = time.time()

    if action == "set":
        try:
            duration = resolve_seconds(minutes, seconds, at)
        except ValueError as error:
            return fail(str(error))
        timer = {"id": next(_ids), "label": label, "due": now + duration, "seconds": duration}
        with _lock:
            _timers.append(timer)
        return ok(
            f"Tamam, {_name(timer)} kuruldu: {spoken_duration(duration)} sonra (saat {_clock(timer['due'])}) "
            "haber vereceğim.",
            id=timer["id"], due=_clock(timer["due"]), seconds=round(duration),
        )

    if action == "list":
        with _lock:
            active = sorted(_timers, key=lambda t: t["due"])
        if not active:
            return ok("Kurulu zamanlayıcı yok.", timers=[])
        lines = [f"{_name(t)}: {spoken_duration(t['due'] - now)} kaldı (saat {_clock(t['due'])})" for t in active]
        return ok("; ".join(lines) + ".", timers=[{"label": t["label"], "due": _clock(t["due"])} for t in active])

    if action == "cancel":
        everything = label.casefold() in ("hepsi", "tümü", "tumu", "all")
        with _lock:
            matches = list(_timers) if everything else _find(label)
            if not matches:
                return fail(f"'{label}' adında zamanlayıcı yok." if label and not everything else "Kurulu zamanlayıcı yok.")
            if len(matches) > 1 and not everything:
                names = ", ".join(_name(t) for t in matches)
                return fail(f"Birden çok zamanlayıcı var: {names}. Hangisini iptal edeyim?", timers=names)
            for timer in matches:
                _timers.remove(timer)
        names = ", ".join(_name(t) for t in matches)
        return ok(f"İptal edildi: {names}.", cancelled=len(matches))

    return fail(f"Bilinmeyen işlem: {action}. Geçerli: {', '.join(ACTIONS)}.")


# ── main.py bekçisi ──────────────────────────────────────────────────────────
def has_timers() -> bool:
    return bool(_timers)


def pop_due(now: float | None = None) -> list[str]:
    """Dolmuş zamanlayıcıları listeden çıkarır, her biri için Chiron'a söyletilecek sistem mesajını döner."""
    now = time.time() if now is None else now
    with _lock:
        due = [t for t in _timers if t["due"] <= now]
        for timer in due:
            _timers.remove(timer)
    messages = []
    for timer in due:
        what = f"'{timer['label']}' hatırlatması" if timer["label"] else _name(timer)
        late = now - timer["due"]
        note = f" ({spoken_duration(late)} gecikmeyle — sen konuşuyordun ya da duraklatılmıştın)" if late >= 60 else ""
        messages.append(
            f"[SİSTEM] Zamanlayıcı doldu (kullanıcının sözü değil): {what}{note}. Kullanıcıya bunu tek kısa, "
            "doğal cümleyle haber ver (ör. 'Çay zamanı.' ya da '25 dakika doldu.'); soru sorma, başka araç çağırma."
        )
    return messages
