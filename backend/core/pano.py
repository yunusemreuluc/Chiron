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
yapılır (bkz. `pano_git.py`). Claude bitirince kart `dogrulaniyor`a geçer: Aıron değişikliği
commit'ler, test komutunu KENDİSİ koşar. Test geçerse `birlestir` (Yunus onaylar), kalırsa
`hata` (Yeniden dene aynı oturumu test çıktısıyla sürdürür). Otomatik birleştirme yok.

    calisiyor ──bitti──> dogrulaniyor ──test geçti──> birlestir ──Birleştir──> bitti
                                     └──test kaldı──> hata          └──Reddet──> iptal
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from backend.core import claude_jobs, pano_git
from backend.core.pano_git import GitError

logger = logging.getLogger("airon.pano")

BASE_DIR = Path(__file__).resolve().parents[2]
STORE_PATH = BASE_DIR / "config" / "pano.json"

STATUSES = (
    "bekliyor", "calisiyor", "duraklatildi", "onay", "dogrulaniyor", "birlestir", "bitti", "iptal", "hata",
)
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
- git commit, push ya da merge YAPMA: değişikliği Aıron commit'leyip test edecek, birleştirmeyi Yunus onaylayacak.
- Test komutu: {test}. Bitirmeden önce kendin de çalıştır."""


class PanoError(ValueError):
    """Kullanıcıya gösterilecek, beklenen hata (yanlış durumda düğme vb.)."""


def _now() -> float:
    return time.time()


def _clean(text: Any, limit: int) -> str:
    return str(text or "").strip()[:limit]


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
                json.dumps({"next": self._next, "cards": self._cards}, ensure_ascii=False, indent=1),
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
            raise PanoError("Değişiklik yapıldı ama diske yazılamadı; Aıron yeniden açılınca kaybolabilir.")

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
            if changed:
                self._save()
            cards = [self._public(c) for c in self._cards]
        self._kick_verifications()
        cards.sort(key=lambda c: c["updated"], reverse=True)
        return {"cards": cards}

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
        self, title: str, detail: str = "", repo: str | None = None, test_cmd: str | None = None
    ) -> dict[str, Any]:
        title, detail = _clean(title, MAX_TITLE), _clean(detail, MAX_DETAIL)
        if not title:
            raise PanoError("Kartın bir başlığı olmalı.")
        root = None
        if repo and repo.strip():
            try:
                root = str(pano_git.repo_root(repo.strip()))
            except GitError as error:
                raise PanoError(str(error)) from error
        with self._lock:
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
            }
            self._cards.append(card)
            self._next += 1
            self._prune()
            if not self._save():
                # Açılmamış sayılır: diske yazılamayan kart ekranda görünüp sonra kaybolmasın.
                self._cards.remove(card)
                self._next -= 1
                raise PanoError("Kart diske yazılamadı, açılmadı.")
            return self._public(card)

    def edit(self, card_id: str, title: str | None = None, detail: str | None = None) -> dict[str, Any]:
        with self._lock:
            card = self._require(card_id)
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
            if card["status"] in ("calisiyor", "dogrulaniyor"):
                raise PanoError("Çalışan kart silinemez; önce sonlandır.")
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
            if status == "duraklatildi":
                note, kind = RESUME_PAUSED, "devam"
            elif status == "hata":
                note, kind = RESUME_FAILED.format(error=card["error"] or "bilinmiyor"), "yeniden"
            else:
                note, kind = None, "baslat"
            if card.get("repo") and not card.get("worktree"):
                try:
                    card.update(pano_git.create_worktree(Path(card["repo"]), pano_git.safe_card_id(card["id"])))
                except GitError as error:
                    raise PanoError(str(error)) from error
            self._submit(card, note, kind)
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
        return f"{head}\n\nAıron görev panosundan, Claude Code ile.\n\nCo-Authored-By: Claude <noreply@anthropic.com>"

    def _kick_verifications(self) -> None:
        """`dogrulaniyor` kartların commit + test işini başlatır (kilit DIŞINDA çağrılır).
        Aıron doğrulama ortasında kapanırsa kart bu durumda kalır; açılışta yeniden koşar."""
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
                result = pano_git.run_test(worktree, test_cmd) if changed and test_cmd else None
                if result:
                    pano_git.reset_after_test(worktree)
                failure = None
            except GitError as error:
                changed, diff, result, failure = True, "", None, str(error)
            with self._lock:
                card = self._find(card_id)
                if not card or card["status"] != "dogrulaniyor":
                    return
                card["diff"] = diff
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
            if card["status"] == "calisiyor" and card["job_id"]:
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
                test=card["test_cmd"] or "yok (Aıron test koşmayacak; kendin uygun olanı çalıştır)",
            )
        return text

    def _submit(self, card: dict[str, Any], note: str | None, kind: str) -> None:
        job = None
        if note and card["session_job"]:
            try:
                job = self.jobs.submit(note, resume_of=card["session_job"], origin="pano")
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
                job = self.jobs.submit(task, origin="pano", cwd=card.get("worktree"))
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
            card["status"] = "calisiyor"
            card["queue_position"] = job.get("queue_position")
            return before != (card["status"], card["steps"], card["last_step"])
        # Bitti: iş kartın geçmişine geçer.
        if job.get("session_id"):
            card["session_job"] = job_id
        card["cost_usd"] = round(float(card.get("cost_usd") or 0) + float(job.get("cost_usd") or 0), 4)
        card["queue_position"] = None
        if status == "done":
            # Proje kartı: Claude'un "bitti"si yetmez, Aıron commit'leyip test edecek.
            card.update(status="dogrulaniyor" if card.get("worktree") else "bitti", summary=job.get("summary") or "")
        elif status == "needs_approval":
            card.update(status="onay", summary=job.get("summary") or "", approval=job.get("approval") or "")
        elif status == "cancelled":
            card["status"] = card.get("intent") or "duraklatildi"
        else:  # failed | timeout | interrupted
            card.update(status="hata", error=job.get("error") or status, summary=job.get("summary") or card["summary"])
        card.update(job_id=None, intent=None, updated=_now())
        return True

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
        data["stopping"] = card["status"] == "calisiyor" and bool(card.get("intent"))
        data["can_resume"] = bool(card.get("session_job"))
        return data


pano = Pano()
