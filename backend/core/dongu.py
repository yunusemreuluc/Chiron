"""7/24 döngü: panodaki bekleyen kartları kendi kendine yürütür (Ajan İstasyonu adım 8, 2026-10-26).

Kullanıcı isteği (2026-10-25): "bizimki de iş versin, 7/24 kendi kendine çalışsın". Plan § adım 8:
kotada dur, sıfırlanınca devam, sabah rapor.

Ne yapar (her TICK_SECONDS'ta bir, yalnız açıkken):
- Kart çalışırken BUSY_TICK_SECONDS'ta bir.
- `pano.snapshot()` — kartları iş kuyruğuyla eşitler, bekleyen doğrulamayı (commit + test) tetikler.
  Arayüz kapalıyken de proje kartları ilerlesin diye; önceden doğrulama yalnız arayüz yoklayınca koşuyordu.
- Hiçbir kart çalışmıyorsa "Bekliyor" sütununun EN ESKİ başlatılabilir kartını başlatır. Tek seferde tek iş
  (claude_jobs kuralıyla aynı: iki tam yetkili ajan aynı anda yazmasın). Chiron'un alt kartları `after`
  sırasıyla kendiliğinden yürür.
- Claude kotası `stop` basamağındaysa Claude kartlarını atlar; pencere sıfırlanınca kota şeridi düşer ve
  döngü kendiliğinden devam eder. Codex kotası doluysa Codex kartları atlanır.
- Her sabah RAPOR_SAATI'nde son rapordan beri olanları yazar (`logs/dongu/rapor-YYYY-MM-DD.md` + Pano).

Ne YAPMAZ (bilinçli): kart bölmez (Chiron'a böldürmek Yunus'un kararı), hata veren kartı yeniden denemez
(kotayı aynı hatada yakmasın), onay/birleştirme vermez — o kartlar Yunus'u bekler, döngü diğerleriyle sürer.

Maliyet: tik yereldir (dosya + bellek), API çağrısı yok — ekran bekçisi dersi (Bilinen-Tuzaklar § Kotayı
yakan şey araçlar değil). Para harcayan tek şey başlatılan kart; günlük üst sınır DAILY_LIMIT.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from backend.core.pano import Pano, PanoError, pano

logger = logging.getLogger("chiron.dongu")

BASE_DIR = Path(__file__).resolve().parents[2]
STATE_PATH = BASE_DIR / "config" / "dongu.json"
REPORT_DIR = BASE_DIR / "logs" / "dongu"

TICK_SECONDS = 60
# Kart çalışırken sık bak: biten kart hemen yerini sıradakine bıraksın, şerit bayat "Çalışıyor" demesin.
BUSY_TICK_SECONDS = 10
DAILY_LIMIT = 20  # günde en fazla bu kadar kart başlatılır (kaçak döngüye fren)
RAPOR_SAATI = 8  # yerel saat
SKIP_SECONDS = 30 * 60  # başlatılamayan kart bu kadar süre denenmez
MAX_EVENTS = 40

BUSY = ("calisiyor", "planlaniyor", "dogrulaniyor")
# Raporda "Yunus'u bekliyor" sayılanlar
WAITING_YUNUS = ("onay", "birlestir")


def next_report_at(after: float, hour: int = RAPOR_SAATI) -> float:
    """`after`'dan sonraki ilk yerel `hour`:00."""
    base = datetime.fromtimestamp(after)
    target = base.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= base:
        target += timedelta(days=1)
    return target.timestamp()


class Dongu:
    def __init__(
        self,
        board: Pano | None = None,
        state_path: Path = STATE_PATH,
        report_dir: Path = REPORT_DIR,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._board = board
        self.state_path = state_path
        self.report_dir = report_dir
        self._clock = clock
        self._lock = threading.Lock()
        self._skip: dict[str, float] = {}  # kart → bu zamana kadar deneme
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self.state: dict[str, Any] = {
            "acik": False,
            "durum": "kapali",
            "neden": "",
            "gun": "",
            "baslatilan": 0,
            "son_rapor": 0.0,
            "rapor": None,
            "olaylar": [],
        }
        self._load()

    @property
    def board(self) -> Pano:
        return self._board or pano

    # ── Kalıcılık ────────────────────────────────────────────────────────
    def _load(self) -> None:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.state.update({k: v for k, v in data.items() if k in self.state})
        except FileNotFoundError:
            return
        except Exception:
            logger.exception("Döngü durumu okunamadı; kapalı başlıyor: %s", self.state_path)
            self.state["acik"] = False

    def _save(self) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.state_path)
        except Exception:
            logger.exception("Döngü durumu kaydedilemedi")

    def _event(self, text: str) -> None:
        self.state["olaylar"] = (self.state["olaylar"] + [{"at": self._clock(), "metin": text}])[-MAX_EVENTS:]

    # ── Dışarıdan ────────────────────────────────────────────────────────
    def public(self) -> dict[str, Any]:
        with self._lock:
            data = json.loads(json.dumps(self.state))
        data["sonraki_rapor"] = next_report_at(max(data["son_rapor"] or 0, self._clock()))
        data["gunluk_sinir"] = DAILY_LIMIT
        return data

    def set_open(self, on: bool) -> dict[str, Any]:
        with self._lock:
            if on and not self.state["acik"]:
                # İlk rapor açıldığı andan itibaren olanı anlatsın.
                if not self.state["son_rapor"]:
                    self.state["son_rapor"] = self._clock()
                self._skip.clear()
                self._event("Döngü açıldı.")
            elif not on and self.state["acik"]:
                self._event("Döngü kapatıldı. Çalışan iş kesilmedi.")
            self.state["acik"] = on
            self.state.update(durum="bekliyor" if on else "kapali", neden="")
            self._save()
        if on:
            self.wake()
        return self.public()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="pano-dongu", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def wake(self) -> None:
        """Açılınca bir dakika beklemeden ilk tik."""
        self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            # Tikten ÖNCE temizle: tik sürerken gelen uyandırma (yeni kart) kaybolmasın, bekleme hemen dönsün.
            self._wake.clear()
            try:
                self.tick()
            except Exception:  # döngü hiçbir hatada ölmemeli
                logger.exception("Döngü tikinde hata")
            with self._lock:
                busy = self.state["acik"] and self.state["durum"] == "calisiyor"
            self._wake.wait(BUSY_TICK_SECONDS if busy else TICK_SECONDS)

    # ── Tik ──────────────────────────────────────────────────────────────
    def tick(self) -> None:
        with self._lock:
            if not self.state["acik"]:
                return
        snapshot = self.board.snapshot()
        cards = snapshot["cards"]
        now = self._clock()
        with self._lock:
            if not self.state["acik"]:
                return
            today = datetime.fromtimestamp(now).strftime("%Y-%m-%d")
            if self.state["gun"] != today:
                self.state.update(gun=today, baslatilan=0)
            if now >= next_report_at(self.state["son_rapor"] or now - 1):
                self._report(cards, snapshot.get("agents") or {}, now)
            self._step(cards, snapshot.get("agents") or {}, now)
            self._save()

    def _step(self, cards: list[dict[str, Any]], agents: dict[str, Any], now: float) -> None:
        busy = [c for c in cards if c["status"] in BUSY]
        if busy:
            self.state.update(durum="calisiyor", neden=f"{busy[0]['id']} {busy[0]['title']}")
            return
        if self.state["baslatilan"] >= DAILY_LIMIT:
            self.state.update(durum="sinir", neden=f"Bugün {DAILY_LIMIT} kart başlatıldı; yarın devam.")
            return
        by_id = {c["id"]: c for c in cards}
        ready = [
            c
            for c in cards
            if c["status"] == "bekliyor"
            and not c.get("planning")
            and all(by_id.get(d, {}).get("status") == "bitti" for d in c.get("after") or [])
            and self._skip.get(c["id"], 0) <= now
        ]
        ready.sort(key=lambda c: c["created"])
        claude = agents.get("claude") or {}
        codex = agents.get("codex") or {}
        sleeping: list[str] = []
        for card in ready:
            agent = card.get("agent") or "claude"
            if agent == "claude" and claude.get("level") == "stop":
                sleeping.append(claude.get("reason") or "Claude kotası dolu.")
                continue
            if agent == "codex" and codex.get("available") is False:
                sleeping.append("Terra'nın (Codex) kotası dolu.")
                continue
            try:
                self.board.start(card["id"])
            except Exception as error:
                # PanoError beklenen ret; başkası (ör. deposu silinmiş kartta NotADirectoryError) da
                # döngüyü aynı kartta kilitlemesin — kart bir süre atlanır, sıradaki denenir.
                if not isinstance(error, PanoError):
                    logger.exception("Döngü %s kartını başlatamadı", card["id"])
                self._skip[card["id"]] = now + SKIP_SECONDS
                self._event(f"{card['id']} başlatılamadı: {error}")
                continue
            self.state["baslatilan"] += 1
            self._event(f"{card['id']} başlatıldı: {card['title']}")
            self.state.update(durum="calisiyor", neden=f"{card['id']} {card['title']}")
            return
        if sleeping:
            self.state.update(durum="uyuyor", neden=sleeping[0])
        else:
            self.state.update(durum="bekliyor", neden="Başlatılacak kart yok.")

    # ── Sabah raporu ─────────────────────────────────────────────────────
    def _report(self, cards: list[dict[str, Any]], agents: dict[str, Any], now: float) -> None:
        since = float(self.state["son_rapor"] or now - 86400)
        recent = [c for c in cards if c["updated"] >= since]
        done = [c for c in recent if c["status"] == "bitti" and not c.get("children")]
        waiting = [c for c in cards if c["status"] in WAITING_YUNUS]
        failed = [c for c in recent if c["status"] == "hata"]
        queued = [c for c in cards if c["status"] == "bekliyor"]
        guard = [(c, h) for c in recent for h in c.get("bekci") or [] if (h.get("at") or 0) >= since]
        cost = round(sum(float(c.get("cost_usd") or 0) for c in recent if c["status"] not in ("bekliyor",)), 2)
        quota = agents.get("claude") or {}
        report = {
            "at": now,
            "since": since,
            "bitti": [self._line(c) for c in done],
            "bekliyor_yunus": [self._line(c) for c in waiting],
            "hata": [self._line(c, c.get("error")) for c in failed],
            "sirada": len(queued),
            "bekci": [{"kart": c["id"], "ad": h.get("ad"), "engellendi": bool(h.get("engellendi"))} for c, h in guard],
            "maliyet_usd": cost,
            "kota": quota.get("reason") or {"ok": "rahat", "info": "yarısı kullanıldı", "warn": "azalıyor"}.get(
                quota.get("level", ""), ""
            ),
        }
        self.state.update(son_rapor=now, rapor=report)
        self._event("Sabah raporu yazıldı.")
        try:
            self.report_dir.mkdir(parents=True, exist_ok=True)
            day = datetime.fromtimestamp(now).strftime("%Y-%m-%d")
            (self.report_dir / f"rapor-{day}.md").write_text(render_report(report), encoding="utf-8")
        except Exception:
            logger.exception("Sabah raporu dosyaya yazılamadı")

    @staticmethod
    def _line(card: dict[str, Any], note: str | None = None) -> dict[str, Any]:
        text = (note or card.get("summary") or "").strip().replace("\n", " ")
        return {"id": card["id"], "baslik": card["title"], "not": text[:240], "durum": card["status"]}


def render_report(report: dict[str, Any]) -> str:
    when = lambda ts: datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")  # noqa: E731
    lines = [f"# Sabah raporu — {when(report['at'])}", "", f"{when(report['since'])}'den beri.", ""]

    def section(title: str, rows: list[dict[str, Any]]) -> None:
        lines.append(f"## {title} ({len(rows)})")
        lines.extend(f"- **{r['id']}** {r['baslik']}" + (f" — {r['not']}" if r["not"] else "") for r in rows)
        lines.append("")

    section("Bitti", report["bitti"])
    section("Seni bekliyor (onay / birleştirme)", report["bekliyor_yunus"])
    section("Hata", report["hata"])
    if report["bekci"]:
        lines.append(f"## Bekçi ({len(report['bekci'])})")
        lines.extend(
            f"- {b['kart']}: {b['ad']}" + (" — durduruldu" if b["engellendi"] else "") for b in report["bekci"]
        )
        lines.append("")
    lines.append(f"Sırada {report['sirada']} kart · harcama ~{report['maliyet_usd']} $ · Claude kotası: {report['kota']}")
    return "\n".join(lines) + "\n"


dongu = Dongu()
