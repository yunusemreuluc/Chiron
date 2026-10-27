"""Görev panosu — kartlar ve yaşam döngüsü (Ajan İstasyonu, adım 1, 2026-10-25).

Kullanıcı isteği (2026-10-25): AgentSpace gibi ofisten iş verebilmek. Ofisin eski
panosu (`ofis.py` görevleri) yalnızca GÖZLEM; burası YAZILABİLİR pano: Yunus kart
açar, "Başlat" der, kart `claude_jobs` kuyruğunda bir Claude işi olur.

Yaşam döngüsü (fikir: ruvnet/ruflo, plugins/ruflo-workflows — MIT; kod alınmadı):

    bekliyor ──Başlat──> calisiyor ──bitti──> bitti
                            │  ├──ONAY_GEREKLI──> onay ──Onayla/Reddet──> calisiyor
                            │  ├──hata/süre/kapanış──> hata ──Başlat──> calisiyor
                            │  └──Durdur──> duraklatildi ──Başlat──> calisiyor
                            └──Sonlandır──> iptal

Kartın durumu iş kuyruğundan TÜRETİLİR (bkz. `_reconcile`): pano işin durumunu
kendisi uydurmaz, `claude_jobs`'a sorar. Durdur/Sonlandır işi iptal eder; iptal
olduktan sonra kartın nereye düşeceğini `intent` söyler.

Devam ettirme: aynı Claude oturumu `--resume` ile sürer (`session_job`). O iş
kuyruğun geçmişinden düşmüşse (KEEP_JOBS) kart görevi baştan verilir.

Proje kartı (adım 3, 2026-10-26): kartta `repo` varsa iş o deponun ayrı bir worktree'sinde
yapılır (bkz. `pano_git.py`). Claude bitirince kart `dogrulaniyor`a geçer: Chiron değişikliği
commit'ler, test komutunu KENDİSİ koşar. Test geçerse `birlestir` (Yunus onaylar), kalırsa
`hata` (Yeniden dene aynı oturumu test çıktısıyla sürdürür). Otomatik birleştirme yok.

    calisiyor ──bitti──> dogrulaniyor ──test geçti──> birlestir ──Birleştir──> bitti
                                     └──test kaldı──> hata          └──Reddet──> iptal

Lider ajan Jarvis (adım 4, 2026-10-26): "Jarvis'e böldür" kartı salt okunur bir Claude
oturumuna (`--permission-mode plan`) verir. Jarvis kartı ve projeyi okur, JSON plan yazar:
2-6 alt görev, her birinin ajanı (claude | codex | gemini) ve hangi görevden sonra geldiği.
Pano planı alt kartlara çevirir; ana kart `bolundu` olur, alt kartların hepsi kapanınca kapanır.

    bekliyor ──Böldür──> planlaniyor ──plan──> bolundu ──(alt kartlar biter)──> bitti
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from backend.core import bekci, claude_jobs, pano_git
from backend.core.pano_git import GitError

logger = logging.getLogger("chiron.pano")

BASE_DIR = Path(__file__).resolve().parents[2]
STORE_PATH = BASE_DIR / "config" / "pano.json"

STATUSES = (
    "bekliyor", "calisiyor", "duraklatildi", "onay", "dogrulaniyor", "birlestir", "bitti", "iptal", "hata",
    "planlaniyor", "bolundu",
)
ACTIVE = ("calisiyor", "planlaniyor")  # bir iş kuyrukta/çalışıyor
# claude: tasarım, çok dosyalı, zor iş · codex (Terra): mekanik kod, desene bakarak test ·
# gemini: yalnızca okuma/araştırma, dosyaya dokunamaz (plan modu)
AGENTS = ("claude", "codex", "gemini")
MAX_SUBTASKS = 8
FINAL = ("bitti", "iptal")
MAX_TITLE = 200
MAX_DETAIL = 3500  # başlık + ayrıntı claude_jobs.MAX_TASK_CHARS'a sığmalı
MAX_CARDS = 200
MAX_HISTORY = 20
MAX_TEST_CMD = 500

RESUME_PAUSED = "Durdurulmuştun. Kaldığın yerden devam et ve işi bitir."
RESUME_FAILED = "Önceki deneme şu hatayla bitti: {error}. Sebebini bul, kaldığın yerden düzelterek devam et."
APPROVED = "Onaylandı: {approval}. Bu adımı yap ve işi bitir."
REJECTED = "Onaylanmadı: {approval}. Bu adımı YAPMA; o ana kadar yapılanı özetle ve bitir."
WORKTREE_NOTE = """\
Çalışma klasörün bu kartın git worktree'si: {worktree} (dal {branch}; ana klasör {repo}).
- Yalnızca bu klasörde çalış, ana klasöre dokunma.
- git commit, push ya da merge YAPMA: değişikliği Chiron commit'leyip test edecek, birleştirmeyi Yunus onaylayacak.
- Test komutu: {test}. Bitirmeden önce kendin de çalıştır."""
LEADER_NOTE = """\
Sen Jarvis'sin: Yunus'un ajan ekibinin lideri. Bu oturum SALT OKUNUR; hiçbir dosyayı değiştirme,
komutla bir şey kurma ya da silme. Görevin aşağıdaki kartı okumak, gerekiyorsa projeyi incelemek ve
işi ekibe bölen bir plan yazmak.

Ekip:
- claude: tasarım kararı, çok dosyalı değişiklik, hata teşhisi, güvenlik, belirsiz iş.
- codex: tanımı net mekanik iş — tek dosyalık düzenleme, var olan desene bakarak test yazma, boilerplate.
  Kotası az; her şeyi ona verme.
- gemini: YALNIZCA okuma/araştırma/özet; dosya yazamaz. Kod değiştirmesi gereken işi gemini'ye verme.

Kurallar:
- 2 ile 6 arası alt görev. Bölmeye değmeyecek kadar küçükse tek görev yaz.
- Her alt görev kendi başına anlaşılır olsun: hangi dosyalar, ne yapılacak, bitince ne doğru olmalı.
  Alt görevi yapan ajan bu kartı görmeyecek, yalnız senin yazdığını görecek.
- Aynı dosyaya yazan iki görev varsa ikincisini birincinin "sonra"sına koy.
- Proje kartıysa her alt görev ayrı bir kopyada yapılıp ayrı test edilecek ve ayrı birleştirilecek.

Son mesajın YALNIZCA şu biçimde tek bir JSON kod bloğu olsun (başka metin yok):
```json
{{"ozet": "planın tek cümlelik özeti",
 "gorevler": [
  {{"baslik": "kısa başlık", "ayrinti": "ne yapılacak, hangi dosyalar, kabul ölçütü", "ajan": "claude", "sonra": []}},
  {{"baslik": "...", "ayrinti": "...", "ajan": "codex", "sonra": [1]}}
 ]}}
```
"sonra": bu görevden önce bitmesi gereken görevlerin 1'den başlayan sıra numaraları.
{unavailable}
Kart:
{card}"""

CODEX_BLOCKED_NOTE = "\nDİKKAT: codex ŞU AN KULLANILAMAZ (kotası {until} tarihine kadar dolu). Ona görev VERME.\n"
# Codex kota hatası: "You've hit your usage limit. ... try again at Nov 24th, 2026 10:02 PM."
_CODEX_LIMIT = re.compile(r"usage limit", re.IGNORECASE)
_CODEX_RETRY = re.compile(r"try again at ([A-Z][a-z]{2})[a-z]* (\d{1,2})(?:st|nd|rd|th)?, (\d{4}) (\d{1,2}:\d{2} [AP]M)")
CODEX_BLOCK_FALLBACK = 24 * 3600  # tarih okunamazsa bir gün bekle

# Claude kotası (adım 6, fikir: ruvnet/ruflo plugins/ruflo-cost-tracker — kod alınmadı). Sayı
# claude_jobs.limits()'ten: Claude Code'un rate_limit_event'i, aboneliğin gerçek doluluğu (0..1).
# Basamaklar: %50 bilgi, %75 uyarı, %90 DUR. Dur %100 değil %90: Yunus'un terminalde kendi işine
# pay kalsın (kullanıcı kararı, plan § 6). Çalışan iş kesilmez; yalnız YENİ Claude işi başlamaz.
QUOTA_INFO, QUOTA_WARN, QUOTA_STOP = 0.5, 0.75, 0.9
QUOTA_WINDOWS = {"five_hour": "5 saatlik pencere", "seven_day": "haftalık pencere"}


def codex_retry_at(text: str) -> float | None:
    """Kota hatası metnindeki "try again at ..." zamanı (yerel saat). Kota hatası değilse None."""
    if not _CODEX_LIMIT.search(text or ""):
        return None
    match = _CODEX_RETRY.search(text)
    if match:
        from datetime import datetime

        month, day, year, clock = match.groups()
        try:
            return datetime.strptime(f"{month} {day} {year} {clock}", "%b %d %Y %I:%M %p").timestamp()
        except ValueError:
            pass
    return _now() + CODEX_BLOCK_FALLBACK


class PanoError(ValueError):
    """Kullanıcıya gösterilecek, beklenen hata (yanlış durumda düğme vb.)."""


def _now() -> float:
    return time.time()


def _clean(text: Any, limit: int) -> str:
    return str(text or "").strip()[:limit]


def _when(ts: float) -> str:
    return time.strftime("%d.%m.%Y %H:%M", time.localtime(ts))


class Pano:
    def __init__(
        self,
        store_path: Path = STORE_PATH,
        jobs: claude_jobs.ClaudeJobs | None = None,
        *,
        background: bool = True,
    ) -> None:
        self.store_path = store_path
        self._jobs = jobs
        # False: doğrulama (commit + test) çağıran thread'de koşar — testler için.
        self._background = background
        self._verifying: set[str] = set()
        self._lock = threading.Lock()
        self._cards: list[dict[str, Any]] = []
        self._next = 1
        # Codex (Terra) kotası dolduysa ne zamana kadar (epoch). Kota hatasından öğrenilir;
        # o zamana kadar Jarvis ona görev vermez, codex kartı başlamaz.
        self._codex_blocked_until: float = 0.0
        self._load()

    @property
    def jobs(self) -> claude_jobs.ClaudeJobs:
        return self._jobs or claude_jobs.jobs

    # ── Kalıcılık ────────────────────────────────────────────────────────
    def _load(self) -> None:
        """Okunamayan dosya boş panoyla açılır ama SİLİNMEZ: kenara alınır (Terra incelemesi,
        2026-10-26 — önceden ilk kayıt bozuk dosyanın üstüne yazıp kurtarmayı imkânsızlaştırıyordu).
        Modül import'ta kuruluyor; burada hata yükselirse backend hiç açılmaz."""
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("cards", []), list):
                raise ValueError("beklenen biçim {next, cards[]} değil")
            self._cards = [c for c in data.get("cards") or [] if isinstance(c, dict) and c.get("id")]
            self._next = int(data.get("next") or len(self._cards) + 1)
            self._codex_blocked_until = float(data.get("codex_blocked_until") or 0)
        except FileNotFoundError:
            return
        except Exception:
            logger.exception("Pano okunamadı, kenara alınıyor: %s", self.store_path)
            self._cards, self._next = [], 1
            try:
                self.store_path.replace(self.store_path.with_name(f"pano.bozuk-{int(_now())}.json"))
            except Exception:
                logger.exception("Bozuk pano dosyası kenara alınamadı")

    def _save(self) -> bool:
        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.store_path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(
                    {"next": self._next, "cards": self._cards, "codex_blocked_until": self._codex_blocked_until},
                    ensure_ascii=False,
                    indent=1,
                ),
                encoding="utf-8",
            )
            os.replace(tmp, self.store_path)
            return True
        except Exception:
            logger.exception("Pano kaydedilemedi")
            return False

    def _commit(self) -> None:
        """Kullanıcı eylemi sonrası kayıt: diske yazılamadıysa bunu SÖYLE (Terra incelemesi).
        Okuma yolundaki (_reconcile) kayıtlar `_save` ile sessiz kalır — durum bellekte doğru."""
        if not self._save():
            raise PanoError("Değişiklik yapıldı ama diske yazılamadı; Chiron yeniden açılınca kaybolabilir.")

    def _prune(self) -> None:
        excess = len(self._cards) - MAX_CARDS
        if excess <= 0:
            return
        old = sorted((c for c in self._cards if c["status"] in FINAL), key=lambda c: c["updated"])
        drop = {c["id"] for c in old[:excess]}
        self._cards = [c for c in self._cards if c["id"] not in drop]

    # ── Okuma ────────────────────────────────────────────────────────────
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            changed = False
            for card in self._cards:
                changed = self._reconcile(card) or changed
            for card in self._cards:
                changed = self._roll_up(card) or changed
            if changed:
                self._save()
            cards = [self._public(c) for c in self._cards]
            agents = {
                "codex": {"available": self._codex_ok(), "until": self._codex_blocked_until or None},
                "claude": self._claude_quota(),
            }
            guard = {"mod": bekci.get_mode(), "modes": list(bekci.MODES)}
        self._kick_verifications()
        cards.sort(key=lambda c: c["updated"], reverse=True)
        return {"cards": cards, "agents": agents, "bekci": guard}

    def get(self, card_id: str) -> dict[str, Any] | None:
        with self._lock:
            card = self._find(card_id)
            if not card:
                return None
            if self._reconcile(card):
                self._save()
            data = self._public(card)
        self._kick_verifications()
        return data

    # ── Yazma ────────────────────────────────────────────────────────────
    def create(
        self,
        title: str,
        detail: str = "",
        repo: str | None = None,
        test_cmd: str | None = None,
        agent: str = "claude",
    ) -> dict[str, Any]:
        title, detail = _clean(title, MAX_TITLE), _clean(detail, MAX_DETAIL)
        if not title:
            raise PanoError("Kartın bir başlığı olmalı.")
        if agent not in AGENTS:
            raise PanoError("Bilinmeyen ajan.")
        root = None
        if repo and repo.strip():
            try:
                root = str(pano_git.repo_root(repo.strip()))
            except GitError as error:
                raise PanoError(str(error)) from error
        with self._lock:
            card = self._new_card(title, detail, root, test_cmd, agent)
            if not self._save():
                # Açılmamış sayılır: diske yazılamayan kart ekranda görünüp sonra kaybolmasın.
                self._cards.remove(card)
                self._next -= 1
                raise PanoError("Kart diske yazılamadı, açılmadı.")
            return self._public(card)

    def _new_card(
        self,
        title: str,
        detail: str,
        root: str | None,
        test_cmd: str | None,
        agent: str,
        parent: str | None = None,
        after: list[str] | None = None,
    ) -> dict[str, Any]:
        """Kartı belleğe ekler (kilit ALTINDA çağrılır, kaydetmez)."""
        now = _now()
        card = {
            "id": f"K-{self._next:03d}",
            "title": title,
            "detail": detail,
            "status": "bekliyor",
            "created": now,
            "updated": now,
            "job_id": None,
            "session_job": None,
            "intent": None,
            "summary": "",
            "approval": "",
            "error": "",
            "steps": 0,
            "last_step": "",
            "cost_usd": 0.0,
            "history": [],
            # Proje kartı (adım 3) — repo yoksa hepsi boş kalır, iş WORK_DIR'de yapılır.
            "repo": root,
            "test_cmd": _clean(test_cmd, MAX_TEST_CMD) if root else "",
            "worktree": None,
            "branch": None,
            "base_branch": None,
            "base_sha": None,
            "test": None,
            "diff": "",
            "merged": None,
            # Lider ajan (adım 4): kim yapacak, hangi kartın parçası, hangi kartlardan sonra.
            "agent": agent,
            "parent": parent,
            "children": [],
            "after": list(after or []),
            "planning": False,
            "plan_summary": "",
            # Bekçi (adım 7): Claude'un takıldığı kurallar + birleştirme öncesi diff taraması.
            "bekci": [],
        }
        self._cards.append(card)
        self._next += 1
        self._prune()
        return card

    def edit(
        self, card_id: str, title: str | None = None, detail: str | None = None, agent: str | None = None
    ) -> dict[str, Any]:
        with self._lock:
            card = self._require(card_id)
            if agent is not None:
                # Ajan, kart yeniden başlatılabildiği her durumda değişebilir (ör. Terra'nın kotası doldu).
                if agent not in AGENTS:
                    raise PanoError("Bilinmeyen ajan.")
                if card["status"] not in ("bekliyor", "duraklatildi", "hata") or card.get("planning"):
                    raise PanoError("Ajan yalnızca bekleyen, durmuş ya da hatalı kartta değişir.")
                if agent != card.get("agent") and card.get("session_job"):
                    # Başka ajan Claude oturumunu sürdüremez: görev baştan verilsin.
                    card["session_job"] = None
                card["agent"] = agent
                if title is None and detail is None:
                    card["updated"] = _now()
                    self._commit()
                    return self._public(card)
            if card["status"] != "bekliyor":
                raise PanoError("Yalnızca bekleyen kart düzenlenebilir.")
            if title is not None:
                title = _clean(title, MAX_TITLE)
                if not title:
                    raise PanoError("Kartın bir başlığı olmalı.")
                card["title"] = title
            if detail is not None:
                card["detail"] = _clean(detail, MAX_DETAIL)
            card["updated"] = _now()
            self._commit()
            return self._public(card)

    def delete(self, card_id: str) -> None:
        with self._lock:
            card = self._require(card_id)
            self._reconcile(card)
            if card["status"] in (*ACTIVE, "dogrulaniyor"):
                raise PanoError("Çalışan kart silinemez; önce sonlandır.")
            open_kids = [i for i in card.get("children") or [] if (self._find(i) or {}).get("status") not in (*FINAL, None)]
            if open_kids:
                raise PanoError(f"Önce alt kartlar kapanmalı: {', '.join(open_kids)}.")
            # Çalışma kopyası silinir, dal KALIR: commit'lenmiş iş kaybolmasın.
            self._drop_worktree(card, force=True)
            self._cards.remove(card)
            self._commit()

    def start(self, card_id: str) -> dict[str, Any]:
        with self._lock:
            card = self._require(card_id)
            self._reconcile(card)
            status = card["status"]
            if status not in ("bekliyor", "duraklatildi", "hata"):
                raise PanoError("Bu kart şu an başlatılamaz.")
            waiting = [d for d in card.get("after") or [] if (self._find(d) or {}).get("status") != "bitti"]
            if waiting:
                raise PanoError(f"Önce {', '.join(waiting)} bitmeli.")
            if card.get("agent") == "codex" and not card.get("planning") and not self._codex_ok():
                raise PanoError(
                    f"Terra'nın (Codex) kotası {_when(self._codex_blocked_until)} tarihine kadar dolu; "
                    "kartın ajanını Claude'a çevir."
                )
            if card.get("planning"):
                # Jarvis'in planı yarıda kaldı ya da okunamadı: yeniden planlat.
                self._submit_plan(card)
                self._commit()
                return self._public(card)
            if status == "duraklatildi":
                note, kind = RESUME_PAUSED, "devam"
            elif status == "hata":
                note, kind = RESUME_FAILED.format(error=card["error"] or "bilinmiyor"), "yeniden"
            else:
                note, kind = None, "baslat"
            # Gemini yalnız okur: kopya gereksiz, deponun kendisinde (salt okunur) çalışır.
            if card.get("repo") and not card.get("worktree") and card.get("agent", "claude") != "gemini":
                try:
                    card.update(pano_git.create_worktree(Path(card["repo"]), pano_git.safe_card_id(card["id"])))
                except GitError as error:
                    raise PanoError(str(error)) from error
            self._submit(card, note, kind)
            self._commit()
            return self._public(card)

    def plan(self, card_id: str) -> dict[str, Any]:
        """Kartı lider ajana (Jarvis) böldürür."""
        with self._lock:
            card = self._require(card_id)
            self._reconcile(card)
            if card["status"] != "bekliyor":
                raise PanoError("Yalnızca bekleyen kart bölünebilir.")
            if card.get("parent"):
                raise PanoError("Alt kart yeniden bölünmez; doğrudan başlat.")
            card["planning"] = True
            self._submit_plan(card)
            self._commit()
            return self._public(card)

    def pause(self, card_id: str) -> dict[str, Any]:
        return self._stop(card_id, "duraklatildi")

    def stop(self, card_id: str) -> dict[str, Any]:
        """Sonlandır: kart iptal olur. Çalışıyorsa önce iş iptal edilir."""
        return self._stop(card_id, "iptal")

    def answer(self, card_id: str, approved: bool) -> dict[str, Any]:
        with self._lock:
            card = self._require(card_id)
            self._reconcile(card)
            if card["status"] != "onay":
                raise PanoError("Bu kart onay beklemiyor.")
            template = APPROVED if approved else REJECTED
            self._submit(card, template.format(approval=card["approval"] or "son adım"), "onay" if approved else "red")
            self._commit()
            return self._public(card)

    def merge(self, card_id: str, approved: bool) -> dict[str, Any]:
        """Test geçmiş kartı ana dala birleştir ya da reddet (çalışma kopyası silinir, dal kalır)."""
        with self._lock:
            card = self._require(card_id)
            if card["status"] != "birlestir":
                raise PanoError("Bu kart birleştirme beklemiyor.")
            repo = Path(card["repo"])
            if not approved:
                self._drop_worktree(card, force=True)
                card.update(status="iptal", updated=_now())
                self._commit()
                return self._public(card)
            try:
                sha = pano_git.merge(repo, card["branch"], card["base_branch"], self._commit_message(card, merge=True))
            except GitError as error:
                if str(error).startswith("Birleştirmede çakışma"):
                    # Claude çözsün: "Yeniden dene" aynı oturumu bu notla sürdürür.
                    card.update(
                        status="hata",
                        error=f"{error} Bu sefer worktree'de `git merge {card['base_branch']}` çalıştırıp "
                        "çakışmaları çöz (bu birleştirmeye izin var), sonra testleri koş.",
                        updated=_now(),
                    )
                    self._commit()
                    return self._public(card)
                raise PanoError(str(error)) from error
            card.update(status="bitti", merged=sha, updated=_now())
            # Birleşti: kopyadaki her iş artık ana dalda; kalan izlenmeyen dosya ancak artık olabilir.
            self._drop_worktree(card, force=True)
            try:
                pano_git.delete_branch(repo, card["branch"])
            except GitError:
                logger.exception("Birleşmiş pano dalı silinemedi: %s", card["branch"])
            self._commit()
            return self._public(card)

    # ── İç ───────────────────────────────────────────────────────────────
    def _drop_worktree(self, card: dict[str, Any], *, force: bool) -> None:
        """Çalışma kopyasını siler. Zorla silmeden önce kopyada kalan iş DALA commit'lenir
        (Terra incelemesi): durdurulmuş bir Claude işinin yarım değişikliği `--force` ile
        geri dönüşsüz gitmesin, dal duruyor ve içinde."""
        if not card.get("worktree"):
            return
        worktree = Path(card["worktree"])
        if force and worktree.exists():
            try:
                pano_git.commit_all(worktree, self._commit_message(card, leftover=True))
            except GitError:
                logger.exception("Kalan iş commit'lenemedi; kopya silinmiyor: %s", worktree)
                return
        try:
            pano_git.remove_worktree(Path(card["repo"]), worktree, force=force)
            card["worktree"] = None
        except GitError:
            logger.exception("Pano çalışma kopyası silinemedi: %s", card["worktree"])

    @staticmethod
    def _commit_message(card: dict[str, Any], *, merge: bool = False, leftover: bool = False) -> str:
        head = f"Pano {card['id']}: {card['title']}"
        if leftover:
            head = f"Pano {card['id']}: kopya silinirken kalan iş ({card['title']})"
        if merge:
            head = f"Birleştir {card['branch']} ({card['id']}: {card['title']})"
        return f"{head}\n\nChiron görev panosundan, Claude Code ile.\n\nCo-Authored-By: Claude <noreply@anthropic.com>"

    def _kick_verifications(self) -> None:
        """`dogrulaniyor` kartların commit + test işini başlatır (kilit DIŞINDA çağrılır).
        Chiron doğrulama ortasında kapanırsa kart bu durumda kalır; açılışta yeniden koşar."""
        with self._lock:
            pending = [c["id"] for c in self._cards if c["status"] == "dogrulaniyor" and c["id"] not in self._verifying]
            self._verifying.update(pending)
        for card_id in pending:
            if self._background:
                threading.Thread(target=self._verify, args=(card_id,), name=f"pano-verify-{card_id}", daemon=True).start()
            else:
                self._verify(card_id)

    def _verify(self, card_id: str) -> None:
        try:
            with self._lock:
                card = self._find(card_id)
                if not card or card["status"] != "dogrulaniyor":
                    return
                worktree, base_sha, test_cmd = Path(card["worktree"]), card["base_sha"], card["test_cmd"]
                message = self._commit_message(card)
            try:
                pano_git.commit_all(worktree, message)
                changed = pano_git.has_commits(worktree, base_sha)
                diff = pano_git.diff_stat(worktree, base_sha) if changed else ""
                # Bekçi'nin ikinci katmanı: hook'u olmayan Codex/Gemini'yi de görür.
                guard = bekci.scan_diff(pano_git.diff_text(worktree, base_sha)) if changed else []
                result = pano_git.run_test(worktree, test_cmd) if changed and test_cmd else None
                if result:
                    pano_git.reset_after_test(worktree)
                failure = None
            except GitError as error:
                changed, diff, result, failure, guard = True, "", None, str(error), []
            with self._lock:
                card = self._find(card_id)
                if not card or card["status"] != "dogrulaniyor":
                    return
                card["diff"] = diff
                card["bekci"] = [h for h in card.get("bekci") or [] if h.get("katman") != "diff"] + guard
                card["test"] = (
                    {"ok": result.ok, "code": result.code, "tail": result.tail, "cmd": result.cmd, "at": _now()}
                    if result
                    else None
                )
                if failure:
                    card.update(status="hata", error=f"Doğrulama yapılamadı: {failure}")
                elif not changed:
                    # Claude hiçbir dosyayı değiştirmedi: birleştirecek bir şey yok.
                    card.update(status="bitti")
                    self._drop_worktree(card, force=True)
                    try:
                        pano_git.delete_branch(Path(card["repo"]), card["branch"])
                    except GitError:
                        logger.exception("Boş pano dalı silinemedi: %s", card["branch"])
                elif result and not result.ok:
                    card.update(status="hata", error=f"Test kaldı ({result.cmd}):\n{result.tail}")
                else:
                    card["status"] = "birlestir"
                card["updated"] = _now()
                self._save()
        finally:
            with self._lock:
                self._verifying.discard(card_id)

    def _stop(self, card_id: str, target: str) -> dict[str, Any]:
        with self._lock:
            card = self._require(card_id)
            self._reconcile(card)
            if card["status"] == "planlaniyor" and target == "duraklatildi":
                raise PanoError("Planlama durdurulamaz; sonlandırabilirsin.")
            if card["status"] == "bolundu":
                raise PanoError("Bölünmüş kart alt kartlarıyla kapanır; alt kartları tek tek sonlandır.")
            if card["status"] in ACTIVE and card["job_id"]:
                card["intent"] = target
                if not self.jobs.cancel(card["job_id"]):
                    # İş tam o anda bitti: kart işin gerçek sonucuna düşsün.
                    card["intent"] = None
                    self._reconcile(card)
            elif card["status"] == "dogrulaniyor":
                # Test süreci arkada koşuyor; kart iptal olsa da test sürer ve kopyaya yazar,
                # ardından gelen silme ona çarpar (Terra). Test 15 dk sınırlı — bitmesi beklenir.
                raise PanoError("Test sürüyor; bitince sonlandırabilirsin.")
            elif target == "iptal" and card["status"] not in FINAL:
                card["status"] = "iptal"
            elif target == "duraklatildi":
                raise PanoError("Yalnızca çalışan kart durdurulabilir.")
            else:
                raise PanoError("Kart zaten kapanmış.")
            card["updated"] = _now()
            self._commit()
            return self._public(card)

    def _task_text(self, card: dict[str, Any]) -> str:
        text = f"Kart {card['id']}: {card['title']}"
        if card["detail"]:
            text += f"\n\n{card['detail']}"
        if card.get("worktree"):
            text += "\n\n" + WORKTREE_NOTE.format(
                worktree=card["worktree"],
                branch=card["branch"],
                repo=card["repo"],
                test=card["test_cmd"] or "yok (Chiron test koşmayacak; kendin uygun olanı çalıştır)",
            )
        return text

    def _submit(self, card: dict[str, Any], note: str | None, kind: str) -> None:
        if card.get("agent", "claude") == "claude":
            self._guard_claude()
        job = None
        if note and card["session_job"]:
            try:
                job = self.jobs.submit(
                    note, resume_of=card["session_job"], origin="pano", engine=card.get("agent", "claude")
                )
            except ValueError as error:
                # Oturum geçmişten düşmüş olabilir; kuyruk doluysa ise baştan vermek de olmaz.
                if "Kuyruk dolu" in str(error) or "kapanıyor" in str(error):
                    raise PanoError(str(error)) from error
                job = None
        if job is None:
            task = self._task_text(card)
            if note and kind != "baslat":
                task += f"\n\n({note})"
            try:
                # Gemini kopyasız: deponun kendisinde, salt okunur.
                cwd = card.get("worktree") or (card.get("repo") if card.get("agent") == "gemini" else None)
                job = self.jobs.submit(task, origin="pano", cwd=cwd, engine=card.get("agent", "claude"))
            except ValueError as error:
                raise PanoError(str(error)) from error
        card.update(
            status="calisiyor",
            job_id=job.id,
            intent=None,
            approval="",
            error="",
            steps=0,
            last_step="",
            updated=_now(),
        )
        card["history"] = (card["history"] + [{"job_id": job.id, "kind": kind, "at": card["updated"]}])[-MAX_HISTORY:]

    def _submit_plan(self, card: dict[str, Any]) -> None:
        self._guard_claude()
        unavailable = "" if self._codex_ok() else CODEX_BLOCKED_NOTE.format(until=_when(self._codex_blocked_until))
        task = LEADER_NOTE.format(card=self._task_text(card), unavailable=unavailable)
        try:
            job = self.jobs.submit(task, origin="pano", cwd=card.get("repo"), engine="claude", mode="plan")
        except ValueError as error:
            raise PanoError(str(error)) from error
        card.update(status="planlaniyor", job_id=job.id, intent=None, error="", steps=0, last_step="", updated=_now())
        card["history"] = (card["history"] + [{"job_id": job.id, "kind": "planla", "at": card["updated"]}])[-MAX_HISTORY:]

    def _apply_plan(self, card: dict[str, Any], text: str) -> None:
        """Jarvis'in JSON planını alt kartlara çevirir (kilit ALTINDA)."""
        try:
            plan = parse_plan(text)
        except ValueError as error:
            card.update(status="hata", error=f"Jarvis'in planı okunamadı: {error}")
            return
        ids: list[str] = []
        context = f"(Bu, {card['id']} \"{card['title']}\" kartının parçası. Planın özeti: {plan['ozet']})"
        for task in plan["gorevler"]:
            if task["ajan"] == "codex" and not self._codex_ok():
                task["ajan"] = "claude"  # Jarvis yine de verdiyse: kota dolu, Claude yapsın
            child = self._new_card(
                _clean(task["baslik"], MAX_TITLE),
                _clean(f"{task['ayrinti']}\n\n{context}", MAX_DETAIL),
                card.get("repo"),
                card.get("test_cmd"),
                task["ajan"],
                parent=card["id"],
                after=[ids[i - 1] for i in task["sonra"]],
            )
            ids.append(child["id"])
        card.update(status="bolundu", children=ids, planning=False, plan_summary=plan["ozet"])

    def _roll_up(self, card: dict[str, Any]) -> bool:
        """Bölünmüş kart: alt kartların hepsi kapanınca kapanır. Değiştiyse True."""
        if card["status"] != "bolundu":
            return False
        kids = [self._find(i) for i in card.get("children") or []]
        kids = [k for k in kids if k]
        if not kids or any(k["status"] not in FINAL for k in kids):
            return False
        card.update(status="bitti" if any(k["status"] == "bitti" for k in kids) else "iptal", updated=_now())
        return True

    def _reconcile(self, card: dict[str, Any]) -> bool:
        """Kartı iş kuyruğundaki gerçek duruma getirir. Değiştiyse True."""
        job_id = card.get("job_id")
        if not job_id:
            return False
        job = self.jobs.get(job_id)
        before = (card["status"], card["steps"], card["last_step"])
        if job is None:
            card.update(status="hata", job_id=None, intent=None, error="İş kaydı bulunamadı.", updated=_now())
            return True
        card["steps"] = job.get("steps") or 0
        card["last_step"] = job.get("last_step") or ""
        status = job["status"]
        if status in claude_jobs.ACTIVE:
            card["status"] = "planlaniyor" if card.get("planning") else "calisiyor"
            card["queue_position"] = job.get("queue_position")
            return before != (card["status"], card["steps"], card["last_step"])
        # Bitti: iş kartın geçmişine geçer.
        if job.get("session_id"):
            card["session_job"] = job_id
        card["cost_usd"] = round(float(card.get("cost_usd") or 0) + float(job.get("cost_usd") or 0), 4)
        card["queue_position"] = None
        if job.get("bekci"):
            card["bekci"] = (list(card.get("bekci") or []) + [dict(h, job_id=job_id) for h in job["bekci"]])[-bekci.MAX_HITS:]
        if status == "done" and card.get("planning"):
            card["summary"] = job.get("summary") or ""
            self._apply_plan(card, card["summary"])
        elif status == "done":
            # Proje kartı: Claude'un "bitti"si yetmez, Chiron commit'leyip test edecek.
            card.update(status="dogrulaniyor" if card.get("worktree") else "bitti", summary=job.get("summary") or "")
        elif status == "needs_approval":
            card.update(status="onay", summary=job.get("summary") or "", approval=job.get("approval") or "")
        elif status == "cancelled":
            card["status"] = card.get("intent") or "duraklatildi"
        else:  # failed | timeout | interrupted
            card.update(status="hata", error=job.get("error") or status, summary=job.get("summary") or card["summary"])
            if card.get("agent") == "codex":
                until = codex_retry_at(f"{card['error']} {job.get('summary') or ''}")
                if until:
                    self._codex_blocked_until = max(self._codex_blocked_until, until)
                    card["error"] = (
                        f"Terra'nın (Codex) kotası {_when(until)} tarihine kadar dolu. "
                        "Kartın ajanını Claude'a çevirip yeniden başlatabilirsin."
                    )
        card.update(job_id=None, intent=None, updated=_now())
        return True

    def _claude_quota(self) -> dict[str, Any]:
        """Claude kotasının şu anki durumu: pencereler, basamak ve dur gerekçesi."""
        limits = getattr(self.jobs, "limits", None)
        data = limits() if callable(limits) else {}
        now = _now()
        windows: dict[str, Any] = {}
        for name in QUOTA_WINDOWS:
            w = data.get(name) if isinstance(data, dict) else None
            if not isinstance(w, dict):
                continue
            resets = float(w.get("resets_at") or 0)
            # Pencere sıfırlandıysa eski doluluk geçersiz.
            used = float(w.get("used") or 0) if not resets or resets > now else 0.0
            windows[name] = {"used": used, "resets_at": resets or None}
        top = max(windows.items(), key=lambda kv: kv[1]["used"], default=(None, {"used": 0.0, "resets_at": None}))
        used = top[1]["used"]
        level = "stop" if used >= QUOTA_STOP else "warn" if used >= QUOTA_WARN else "info" if used >= QUOTA_INFO else "ok"
        reason = ""
        blocked_until = float(data.get("blocked_until") or 0) if isinstance(data, dict) else 0.0
        if blocked_until > now:
            level, reason = "stop", f"Claude kotası doldu; {_when(blocked_until)} sıfırlanıyor."
        elif level == "stop" and top[0]:
            resets = top[1]["resets_at"]
            reason = (
                f"Claude kotası %{round(used * 100)} ({QUOTA_WINDOWS[top[0]]})"
                + (f", {_when(resets)} sıfırlanıyor" if resets else "")
                + ". Yeni Claude işi başlatılmadı; terminale pay kalsın diye sınır %"
                + f"{round(QUOTA_STOP * 100)}."
            )
        return {**windows, "level": level, "reason": reason, "seen": float(data.get("ts") or 0) or None}

    def _guard_claude(self) -> None:
        quota = self._claude_quota()
        if quota["level"] == "stop":
            raise PanoError(quota["reason"])

    def _codex_ok(self) -> bool:
        return _now() >= self._codex_blocked_until

    def _find(self, card_id: str) -> dict[str, Any] | None:
        return next((c for c in self._cards if c["id"] == card_id), None)

    def _require(self, card_id: str) -> dict[str, Any]:
        card = self._find(card_id)
        if not card:
            raise PanoError("Kart bulunamadı.")
        return card

    @staticmethod
    def _public(card: dict[str, Any]) -> dict[str, Any]:
        data = {k: v for k, v in card.items() if k != "intent"}
        data["stopping"] = card["status"] in ACTIVE and bool(card.get("intent"))
        data["can_resume"] = bool(card.get("session_job"))
        return data


def parse_plan(text: str) -> dict[str, Any]:
    """Jarvis'in son mesajından planı çıkarır ve doğrular. Bozuksa ValueError (kart `hata`ya düşer).

    Son ```json bloğu, yoksa ilk `{` ile son `}` arası. Ajan bilinmiyorsa claude; "sonra" yalnız
    kendinden ÖNCEKİ görevleri gösterebilir (döngü olmasın).
    """
    import re

    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    raw = blocks[-1] if blocks else text[text.find("{"): text.rfind("}") + 1]
    try:
        data = json.loads(raw)
    except ValueError as error:
        raise ValueError("JSON değil") from error
    tasks = data.get("gorevler") if isinstance(data, dict) else None
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("görev listesi yok")
    if len(tasks) > MAX_SUBTASKS:
        raise ValueError(f"en fazla {MAX_SUBTASKS} alt görev")
    clean: list[dict[str, Any]] = []
    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict) or not str(task.get("baslik") or "").strip():
            raise ValueError(f"{index}. görevin başlığı yok")
        after = task.get("sonra") or []
        if not isinstance(after, list) or any(not isinstance(i, int) or not 1 <= i < index for i in after):
            raise ValueError(f"{index}. görevin 'sonra' listesi geçersiz")
        agent = str(task.get("ajan") or "claude").strip().lower()
        clean.append({
            "baslik": str(task["baslik"]).strip(),
            "ayrinti": str(task.get("ayrinti") or "").strip(),
            "ajan": agent if agent in AGENTS else "claude",
            "sonra": sorted(set(after)),
        })
    return {"ozet": str(data.get("ozet") or "").strip(), "gorevler": clean}


pano = Pano()
