"""7/24 döngü: panodaki bekleyen kartları kendi kendine yürütür (Ajan İstasyonu adım 8, 2026-10-26).

Kullanıcı isteği (2026-10-25): "bizimki de iş versin, 7/24 kendi kendine çalışsın". Plan § adım 8:
kotada dur, sıfırlanınca devam, sabah rapor.

Ne yapar (her TICK_SECONDS'ta bir, yalnız açıkken):
- Kart çalışırken BUSY_TICK_SECONDS'ta bir.
- `pano.snapshot()` — kartları iş kuyruğuyla eşitler, bekleyen doğrulamayı (commit + test) tetikler.
  Arayüz kapalıyken de proje kartları ilerlesin diye; önceden doğrulama yalnız arayüz yoklayınca koşuyordu.
- "Bekliyor" sütununun EN ESKİ başlatılabilir kartını başlatır, tik başına bir kart. Kart çalışırken yalnız
  PROJE kartı (kendi worktree'si olan) eklenebilir, toplam MAX_PARALLEL (2026-10-29, paralel pano): ayrı
  kopyalarda iki ajan birbirinin dosyasına yazamaz. Projesiz kart yine tek başına (ana klasörde çakışırlar). Chiron'un alt kartları `after`
  sırasıyla kendiliğinden yürür.
- Claude kotası `stop` basamağındaysa Claude kartlarını atlar; pencere sıfırlanınca kota şeridi düşer ve
  döngü kendiliğinden devam eder. Codex kotası doluysa Codex kartları atlanır.
- Her sabah RAPOR_SAATI'nde son rapordan beri olanları yazar (`logs/dongu/rapor-YYYY-MM-DD.md` + Pano).

Ne YAPMAZ (bilinçli): kart bölmez (Chiron'a böldürmek Yunus'un kararı), hata veren kartı yeniden denemez
(kotayı aynı hatada yakmasın), onay/birleştirme vermez — o kartlar Yunus'u bekler, döngü diğerleriyle sürer.

Maliyet: tik yereldir (dosya + bellek), API çağrısı yok — ekran bekçisi dersi (Bilinen-Tuzaklar § Kotayı
yakan şey araçlar değil). Para harcayan tek şey başlatılan kart; günlük üst sınır DAILY_LIMIT.

Kendini geliştirme (2026-10-30, Yunus: "kendi kendini geliştirsin, öğrensin, arayüzü daha kullanışlı olsun,
7/24 çalışsın, yaptıklarını ve öğrendiklerini bana söylesin"): `gelisim` açıksa ve kuyrukta iş yoksa döngü
Chiron'un kendi deposuna bir PROJE kartı açar (`GELISIM_PREFIX`). Kart ayrı kopyada araştırır, TEK küçük
iyileştirme yapar, test eder, `Notes/Gelisim-Gunlugu.md`'ye ne yaptığını/neden daha iyi olduğunu/ne öğrendiğini
yazar. Frenler: GELISIM_ARALIK, GELISIM_GUNLUK, Claude kotası yalnız rahatken (ok/info), kart başına bütçe.

Onaysız (2026-11-06, Yunus: "benden onay istemesin, yapsın, commit ve push yapsın"): eski hali onay bekleyen 2
kartta günlerce duruyordu (30.10–04.11 arası hiç kart yok). Şimdi test geçen kart kendi kendine birleşir ve gönderilir
(`Pano.auto_merge`, işçi `_oto_is`). Kart `onay` isterse reddedilir, `hata`ya düşerse bir kez yeniden denenir, olmazsa
bırakılır; döngü hiçbir kartta kilitlenmez. Yalnız hassas dosyaya dokunan kart Yunus'u bekler (`oto_engel`).
Sonuç `gelisim_haber`e girer; sesli Chiron söyler (main.py _watch_gelisim).
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

from backend.core.claude_jobs import MAX_PARALLEL
from backend.core.pano import GELISIM_PREFIX, Pano, PanoError, pano

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

GELISIM_ARALIK = 2 * 3600  # iki geliştirme kartı arası en az
GELISIM_GUNLUK = 6
GELISIM_BEKLEYEN = 2  # birleşmeyi bekleyen bu kadar geliştirme varken yenisi açılmaz (çakışma birikmesin)
GELISIM_KOTA = ("ok", "info", "")  # Yunus'un kendi işine pay kalsın: kota azalırken geliştirme açılmaz
GELISIM_HABER = 10
OTO_DENEME = 1  # hataya düşen kart bir kez yeniden denenir, sonra bırakılır
OTO_BEKLE = 5 * 60  # ana klasör izin vermediyse bu kadar sonra yeniden
OTO_PUSH_BEKLE = 10 * 60
# Görev kısa ve okuma listesi dar (2026-11-06): eski metin 7 notu okutuyordu, bağlam kart boyunca her turda yeniden
# ödeniyor. Açık istekler ve eski başlıklar hazır veriliyor, büyük notlar yalnız gerekince parça parça okunuyor.
GELISIM_TASK = """\
Sen Chiron'sun; bu iş KENDİNİ GELİŞTİRME işi. Çalıştığın kopya Chiron'un kendi deposu. Yunus sonucu sesle duyacak.

1. TEK, küçük, somut bir iyileştirme seç (en fazla ~300 satır). Öncelik: aşağıdaki açık istekler; sonra
   `logs/chiron.log`da tekrar eden gerçek hatalar (`grep ERROR`, son satırlar); sonra Yunus'un günlük kullanımda
   hissedeceği kullanışlılık. Son kayıtlar yeni sesli araçsa bu kez var olanı düzelt ya da arayüzü iyileştir.
   YASAK: ödeme, anahtar, güvenlik ayarı, bekçi, kota frenleri, bu döngü, yeni bağımlılık. Dokunursan birleşmez.
2. Tutumlu çalış: dosyayı baştan sona okuma, `grep -n` ile bul, gereken parçayı oku; çıktıları `| tail` ile kes.
   Notes/Arayuz.md ve Notes/Bilinen-Tuzaklar.md çok büyük, yalnız konunun bölümünü oku. Hedef ~25 araç çağrısı.
   Web'de en fazla bir kısa arama yap. Alt ajan açma.
3. Uygula, var olan desene uy. Yeni araç dört yere yazılır: @register_tool, tool_defs.py, core/prompt.txt,
   Notes/Araclar/ sayfası. Arayüzün tiplerini Chiron denetler; node_modules kopyada yok.
4. Yeni davranışa test ekle, en sonda BİR kez koş: {test} 2>&1 | tail -5. Testin geçerse Chiron birleştirip gönderir.
5. Docs/Son-Oturum.md ve Docs/Acik-Konular.md'ye dokunma. Notes/Gelisim-Gunlugu.md'de başlıkların en üstüne ekle:
   ## <tarih> — <kısa başlık>
   - **Ne yaptım:** / **Neden daha iyi:** (somut fark) / **Ne öğrendim:** / **Kaynak:**
6. Son mesajın sesle okunacak: 2-3 kısa Türkçe cümle, birinci ağızdan. Dosya yolu, kod, Claude adı yok.

Açık istekler:
{istekler}

Daha önce yapılanlar (tekrar etme):
{gunluk}
{recent}"""


def acik_istekler(repo: Path, limit: int = 5) -> str:
    """İstek listesinin açık maddeleri, kısa. Dosya büyüyor; kart hepsini okumasın."""
    try:
        text = (repo / "Notes" / "Istek-Listesi.md").read_text(encoding="utf-8")
    except OSError:
        return "- (okunamadı)"
    rows = []
    for block in text.split("\n### ")[1:]:
        lines = block.splitlines()
        durum = next((ln for ln in lines if ln.startswith("**Durum:**")), "")
        if "yeni" not in durum and "bakıldı" not in durum:
            continue
        said = next((ln.strip() for ln in lines if ln.startswith("- ")), "")
        said = said.split("·")[1].strip() if said.count("·") >= 1 else said
        rows.append(f"- {lines[0].strip()[:60]}: {said[:80]}")
    return "\n".join(rows[-limit:]) or "- (yok)"


def gunluk_basliklari(repo: Path, limit: int = 10) -> str:
    """Geliştirme günlüğünün son başlıkları (en yeni üstte)."""
    try:
        text = (repo / "Notes" / "Gelisim-Gunlugu.md").read_text(encoding="utf-8")
    except OSError:
        return ""
    return "\n".join(f"- {ln[3:].strip()[:70]}" for ln in text.splitlines() if ln.startswith("## "))[: limit * 75]


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
            "gelisim": False,
            "gelisim_son": 0.0,
            "gelisim_gun": "",
            "gelisim_sayi": 0,
            "gelisim_durum": {},  # kart → son görülen durum (haber için)
            "gelisim_haber": [],  # söylenmeyi bekleyen geliştirme sonuçları
            "gelisim_deneme": {},  # kart → otomatik yeniden deneme sayısı
            "gelisim_push": None,  # birleşti ama gönderilemedi: {"repo", "dal"}
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

    def set_gelisim(self, on: bool) -> dict[str, Any]:
        """Kendini geliştirmeyi aç/kapat. Açmak döngüyü de açar (kartları döngü yürütür)."""
        with self._lock:
            if on != self.state["gelisim"]:
                self._event("Kendini geliştirme açıldı." if on else "Kendini geliştirme kapatıldı. Çalışan iş kesilmedi.")
            self.state["gelisim"] = on
            self._save()
        if on:
            return self.set_open(True)
        return self.public()

    def take_news(self) -> list[dict[str, Any]]:
        """Söylenmemiş geliştirme sonuçları; alınanlar listeden düşer."""
        with self._lock:
            news = list(self.state["gelisim_haber"])
            if news:
                self.state["gelisim_haber"] = []
                self._save()
            return news

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
            self._track_gelisim(cards, now)
            self._oto_kurtar(cards, snapshot.get("agents") or {}, now)
            self._step(cards, snapshot.get("agents") or {}, now)
            if self.state["durum"] == "bekliyor":
                self._maybe_gelisim(cards, snapshot.get("agents") or {}, now)
            self._save()
        self._oto_baslat(cards, now)

    def _step(self, cards: list[dict[str, Any]], agents: dict[str, Any], now: float) -> None:
        busy = [c for c in cards if c["status"] in BUSY]
        if len(busy) >= MAX_PARALLEL:
            self.state.update(durum="calisiyor", neden=f"{busy[0]['id']} {busy[0]['title']}")
            return
        if self.state["baslatilan"] >= DAILY_LIMIT:
            if busy:
                self.state.update(durum="calisiyor", neden=f"{busy[0]['id']} {busy[0]['title']}")
            else:
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
            # Kart sürerken yanına yalnız kendi kopyasında çalışacak proje kartı.
            and (not busy or bool(c.get("repo")))
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
        if busy:
            self.state.update(durum="calisiyor", neden=f"{busy[0]['id']} {busy[0]['title']}")
        elif sleeping:
            self.state.update(durum="uyuyor", neden=sleeping[0])
        else:
            self.state.update(durum="bekliyor", neden="Başlatılacak kart yok.")

    # ── Kendini geliştirme ───────────────────────────────────────────────
    def _track_gelisim(self, cards: list[dict[str, Any]], now: float) -> None:
        """Geliştirme kartı Yunus'a söylenecek bir duruma geçince haber kuyruğuna ekler."""
        seen = self.state["gelisim_durum"]
        alive = set()
        for card in cards:
            if not card["title"].startswith(GELISIM_PREFIX):
                continue
            alive.add(card["id"])
            status = card["status"]
            # Haber yalnız sonuçta: birleşti, ya da kararı Yunus'a kaldı. Yeniden denenecek hata sessiz.
            key = "engel" if status == "birlestir" and card.get("oto_engel") else status
            if seen.get(card["id"]) != key and (key in ("engel", "bitti") or (key == "hata" and not self.state["gelisim"])):
                text = {"engel": card.get("oto_engel"), "hata": card.get("error")}.get(key, card.get("summary")) or ""
                self._haber(card, "birlestir" if key == "engel" else status, text, now)
            seen[card["id"]] = key
        self.state["gelisim_durum"] = {k: v for k, v in seen.items() if k in alive}

    def _haber(self, card: dict[str, Any], durum: str, text: str, now: float) -> None:
        self.state["gelisim_haber"] = (
            self.state["gelisim_haber"]
            + [{"id": card["id"], "baslik": card["title"], "durum": durum, "metin": text.strip()[:600], "at": now}]
        )[-GELISIM_HABER:]

    def _oto_kurtar(self, cards: list[dict[str, Any]], agents: dict[str, Any], now: float) -> None:
        """Kart Yunus'a takılmasın: `onay` reddedilir (riskli adım yapılmadan biter), `hata` bir kez yeniden denenir."""
        if not self.state["gelisim"]:
            return
        tries = self.state.setdefault("gelisim_deneme", {})
        for card in cards:
            if not card["title"].startswith(GELISIM_PREFIX):
                continue
            try:
                if card["status"] == "onay":
                    self.board.answer(card["id"], False)
                    self._event(f"{card['id']} onay istedi, sormadan reddedildi: {card.get('approval') or ''}"[:200])
                elif card["status"] == "hata":
                    budget = "budget" in (card.get("error") or "")  # aynı bütçeye yeniden çarpmasın
                    if tries.get(card["id"], 0) >= OTO_DENEME or budget:
                        self.board.give_up(card["id"])
                        tries.pop(card["id"], None)
                        self._event(f"{card['id']} bırakıldı: {(card.get('error') or '')[:120]}")
                        self._haber(card, "hata", card.get("error") or "", now)
                    elif (agents.get("claude") or {}).get("level", "") in GELISIM_KOTA:
                        tries[card["id"]] = tries.get(card["id"], 0) + 1
                        self.board.start(card["id"])
                        self.state["baslatilan"] += 1
                        self._event(f"{card['id']} yeniden deneniyor.")
            except Exception:
                logger.exception("Geliştirme kartı kurtarılamadı: %s", card["id"])

    def _oto_baslat(self, cards: list[dict[str, Any]], now: float) -> None:
        """Test geçmiş kartı birleştirmeyi ya da bekleyen gönderimi başlatır. Test sürebilir: kilit dışında, tek işçi."""
        with self._lock:
            if not self.state["gelisim"] or getattr(self, "_oto_mesgul", False):
                return
            later = self.__dict__.setdefault("_oto_sonra", {})
            card_id = next(
                (
                    c["id"]
                    for c in cards
                    if c["title"].startswith(GELISIM_PREFIX)
                    and c["status"] == "birlestir"
                    and not c.get("oto_engel")
                    and later.get(c["id"], 0) <= now
                ),
                None,
            )
            push_due = self.state.get("gelisim_push") and later.get("push", 0) <= now
            if not card_id and not push_due:
                return
            self._oto_mesgul = True
        if getattr(self.board, "_background", True):
            threading.Thread(target=self._oto_is, args=(card_id,), name="gelisim-birlestir", daemon=True).start()
        else:
            self._oto_is(card_id)

    def _oto_is(self, card_id: str | None) -> None:
        try:
            if card_id:
                try:
                    result = self.board.auto_merge(card_id)
                except Exception as error:
                    logger.exception("Otomatik birleştirme başarısız: %s", card_id)
                    result = {"durum": "bekliyor", "neden": str(error)}
                with self._lock:
                    self._oto_sonuc(card_id, result)
                    self._save()
            self._oto_push()
        finally:
            with self._lock:
                self._oto_mesgul = False
            self.wake()

    def _oto_sonuc(self, card_id: str, result: dict[str, Any]) -> None:
        durum, neden = result.get("durum"), str(result.get("neden") or "")
        later = self.__dict__.setdefault("_oto_sonra", {})
        if durum == "birlesti":
            self.state["gelisim_push"] = {"repo": result["repo"], "dal": result["dal"]}
            self.state.setdefault("gelisim_deneme", {}).pop(card_id, None)
            later.pop("push", None)
            self._event(f"{card_id} birleşti: {result.get('sha')}")
        elif durum == "bekliyor":
            if later.get(card_id, 0) == 0:  # her denemede günlüğe yazmasın
                self._event(f"{card_id} birleşmeyi bekliyor: {neden[:160]}")
            later[card_id] = self._clock() + OTO_BEKLE
        elif durum in ("engel", "cakisma", "test"):
            self._event(f"{card_id} birleşmedi ({durum}): {neden[:160]}")
        else:  # kartın kopyası yok ya da durumu değişti: her tikte denenmesin
            later[card_id] = self._clock() + OTO_BEKLE

    def _oto_push(self) -> None:
        with self._lock:
            target = self.state.get("gelisim_push")
        if not target:
            return
        from backend.core import pano_git

        try:
            pano_git.push(Path(target["repo"]), target["dal"])
        except Exception as error:
            with self._lock:
                later = self.__dict__.setdefault("_oto_sonra", {})
                if not later.get("push"):
                    self._event(f"Gönderilemedi, yeniden denenecek: {str(error)[:160]}")
                later["push"] = self._clock() + OTO_PUSH_BEKLE
                self._save()
            return
        with self._lock:
            self.state["gelisim_push"] = None
            self.__dict__.setdefault("_oto_sonra", {}).pop("push", None)
            self._event(f"{target['dal']} gönderildi.")
            self._save()

    def _maybe_gelisim(self, cards: list[dict[str, Any]], agents: dict[str, Any], now: float) -> None:
        """Kuyruk boşken Chiron'un kendi deposuna bir geliştirme kartı açar (frenler sınıf belgesinde)."""
        if not self.state["gelisim"]:
            return
        today = datetime.fromtimestamp(now).strftime("%Y-%m-%d")
        if self.state["gelisim_gun"] != today:
            self.state.update(gelisim_gun=today, gelisim_sayi=0)
        mine = [c for c in cards if c["title"].startswith(GELISIM_PREFIX)]
        waiting = [c for c in mine if c["status"] in ("birlestir", "onay")]
        blocked = [c for c in waiting if c.get("oto_engel")]
        why = None
        if len(blocked) >= GELISIM_BEKLEYEN:
            why = f"{len(blocked)} geliştirme hassas dosyaya dokunduğu için senin kararını bekliyor."
        elif len(waiting) >= GELISIM_BEKLEYEN:
            why = f"{len(waiting)} geliştirme birleşmeyi bekliyor; ana klasör müsait olunca devam ediyorum."
        elif any(c["status"] not in ("bitti", "iptal", "birlestir", "onay") for c in mine):
            return
        elif self.state["gelisim_sayi"] >= GELISIM_GUNLUK:
            why = f"Bugün {GELISIM_GUNLUK} geliştirme yaptım; yarın devam."
        elif now - float(self.state["gelisim_son"] or 0) < GELISIM_ARALIK:
            nxt = datetime.fromtimestamp(float(self.state["gelisim_son"]) + GELISIM_ARALIK).strftime("%H:%M")
            why = f"Sıradaki geliştirme {nxt}'de."
        elif (agents.get("claude") or {}).get("level", "") not in GELISIM_KOTA:
            why = "Claude kotası azaldı; geliştirme senin işine pay bırakıyor."
        if why:
            self.state["neden"] = why
            return
        from backend.core import pano_git  # döngü testleri git'siz koşsun diye geç içe aktarım

        repo = Path(__file__).resolve().parents[2]
        test = pano_git.suggest_test(repo)
        recent = "\n".join(
            f"- {(c.get('summary') or c.get('error') or '').strip()[:110]}"
            for c in sorted(mine, key=lambda c: c["created"])[-3:]
        )
        title = f"{GELISIM_PREFIX} {datetime.fromtimestamp(now).strftime('%d.%m %H:%M')} kendini geliştirme"
        detail = GELISIM_TASK.format(
            test=test or "testler", istekler=acik_istekler(repo), gunluk=gunluk_basliklari(repo), recent=recent
        )
        try:
            card = self.board.create(title, detail, str(repo), test)
        except Exception as error:
            self._event(f"Geliştirme kartı açılamadı: {error}")
            self.state["neden"] = f"Geliştirme kartı açılamadı: {error}"
            self.state["gelisim_son"] = now  # aynı hatayı her dakika denemesin
            return
        self.state["gelisim_son"] = now
        self.state["gelisim_sayi"] += 1
        self._event(f"{card['id']} açıldı: kendini geliştirme")
        self.wake()

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
