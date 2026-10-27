"""Dosya yönetimi — yeniden adlandırma, sıralı adlandırma, taşıma, silme.

Kullanıcı isteği (2026-08-01): Chiron dosyaları yönetebilsin — özellikle
"şu klasördeki görselleri 1'den başlayarak sırala" gibi toplu işler.

Öncesinde Chiron'da dosya DEĞİŞTİREN hiçbir araç yoktu; `search_files` buluyor,
`summarize_file` okuyordu. `shell_run` ile `ren` komutu uydurulabilirdi ama her
çağrıda onay istediği için toplu işte kullanılamazdı.

## Silme neden Geri Dönüşüm Kutusu'na gidiyor

Kullanıcının istediği davranış: "hedef belirginse sormadan yap". Sorun şu ki
"belirgin" kararını çoğu zaman ekranı yorumlayan bir vision modeli veriyor ve
o yanılabiliyor ([[Bilinen-Tuzaklar]] § Bir güvenlik kapısı, denetlediği şeye
güvenemez). Yanlış tıklama geri alınabilir, yanlış SİLME alınamaz.

Çözüm onay eklemek değil, işlemi geri alınabilir yapmak: `delete` işlemi
Geri Dönüşüm Kutusu'na gönderiyor, onay istemiyor. Böylece kullanıcının
istediği akıcılık korunuyor ve hata telafi edilebilir kalıyor.
`delete_permanent` ayrı bir işlem ve HER ZAMAN onay istiyor.

## Çakışma tuzağı

`a.jpg → 1.jpg` yapılırken hedefte zaten `1.jpg` varsa üzerine yazılır ve o
dosya kaybolur. Sıralı adlandırma bu yüzden İKİ FAZLI: önce hepsi çakışması
imkânsız geçici adlara, sonra nihai adlara. Tek fazlı yazılsaydı sessizce veri
kaybettirirdi — ve tam olarak "1.jpg zaten var" durumu sıralamada en sık
karşılaşılan hâl.
"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from actions.tool_result import fail, ok
from core.tool_registry import register_tool

try:
    from send2trash import send2trash

    HAS_SEND2TRASH = True
except ImportError:  # pragma: no cover — requirements.txt'te var
    HAS_SEND2TRASH = False


# Tek çağrıda işlenecek azami dosya. Kazara bir kök klasör verilirse binlerce
# dosyayı sessizce işlemesin — sınır aşılırsa açıklayıp duruyor.
MAX_FILES = 500

# Bu yolların ALTINDA hiçbir işlem yapılmıyor. Sebep basit: Chiron'un hedefi
# bazen ekran analizinden geliyor ve yanlış bir yol üretebiliyor; sistem
# klasörlerinde bir hata onarılabilir olmaktan çıkar.
def _korumali_kokler() -> list[Path]:
    kokler = []
    for degisken in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
        deger = os.environ.get(degisken)
        if deger:
            kokler.append(Path(deger))
    # Sürücü kökünün kendisi de korunuyor (C:\ üzerinde toplu işlem yok).
    return kokler


def _yol_guvenli(yol: Path) -> str:
    """Boşsa güvenli; değilse engelleme sebebi döner."""
    try:
        cozulmus = yol.resolve()
    except Exception as exc:
        return f"yol çözülemedi: {exc}"

    if cozulmus.parent == cozulmus:
        return f"sürücü kökünde ({cozulmus}) toplu işlem yapmam"

    for korumali in _korumali_kokler():
        try:
            if cozulmus == korumali or korumali in cozulmus.parents:
                return f"sistem klasörü ({korumali}) altında işlem yapmam"
        except Exception:
            continue
    return ""


def _hedef_dosyalar(target: Path, pattern: str) -> list[Path]:
    """Klasörse içindeki (desene uyan) dosyalar, dosyaysa kendisi."""
    if target.is_file():
        return [target]
    if not target.is_dir():
        return []
    desen = pattern.strip() or "*"
    return sorted(p for p in target.glob(desen) if p.is_file())


def _sirala(dosyalar: list[Path], sort_by: str) -> list[Path]:
    olcut = (sort_by or "name").strip().lower()
    if olcut in ("date", "tarih", "modified"):
        return sorted(dosyalar, key=lambda p: p.stat().st_mtime)
    if olcut in ("size", "boyut"):
        return sorted(dosyalar, key=lambda p: p.stat().st_size)
    # Varsayılan: ada göre, ama "10.jpg" > "9.jpg" olacak şekilde doğal sıralama.
    import re

    def anahtar(p: Path):
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]

    return sorted(dosyalar, key=anahtar)


def _sirali_plan(dosyalar: list[Path], start: int) -> list[tuple[Path, Path]]:
    """(kaynak, hedef) çiftleri — uzantı korunuyor."""
    plan = []
    for i, kaynak in enumerate(dosyalar, start=start):
        plan.append((kaynak, kaynak.with_name(f"{i}{kaynak.suffix}")))
    return plan


def _iki_fazli_adlandir(plan: list[tuple[Path, Path]]) -> tuple[int, list[str]]:
    """Çakışmasız toplu yeniden adlandırma.

    Faz 1: her kaynak, çakışması imkânsız geçici bir ada taşınır.
    Faz 2: geçici adlar nihai hedeflere taşınır.

    Tek fazda yapılsaydı `a.jpg → 1.jpg` sırasında var olan `1.jpg` ezilir ve
    o dosya kaybolurdu — sıralı adlandırmada en sık karşılaşılan durum bu.
    """
    ek = uuid.uuid4().hex[:8]
    gecici: list[tuple[Path, Path]] = []
    hatalar: list[str] = []

    for kaynak, _hedef in plan:
        gecici_yol = kaynak.with_name(f".chiron-{ek}-{kaynak.name}")
        try:
            kaynak.rename(gecici_yol)
            gecici.append((gecici_yol, _hedef))
        except Exception as exc:
            hatalar.append(f"{kaynak.name}: {exc}")

    islenen = 0
    for gecici_yol, hedef in gecici:
        try:
            gecici_yol.rename(hedef)
            islenen += 1
        except Exception as exc:
            hatalar.append(f"{hedef.name}: {exc}")
            # Geçici adda kalmasın — kaynağına döndürmeye çalış.
            try:
                gecici_yol.rename(gecici_yol.with_name(gecici_yol.name.split("-", 2)[-1]))
            except Exception:
                pass
    return islenen, hatalar


def _ozet(plan: list[tuple[Path, Path]], limit: int = 8) -> str:
    satirlar = [f"{k.name} → {h.name}" for k, h in plan[:limit]]
    if len(plan) > limit:
        satirlar.append(f"... ve {len(plan) - limit} dosya daha")
    return "\n".join(satirlar)


@register_tool("manage_files")
def manage_files(
    action: str,
    target: str,
    destination: str = "",
    pattern: str = "",
    sort_by: str = "name",
    start: int = 1,
    confirm: bool = False,
) -> dict:
    """Dosya/klasör işlemleri: sıralı adlandırma, yeniden adlandırma, taşıma,
    kopyalama, silme."""
    islem = (action or "").strip().lower()
    if not target.strip():
        return fail("Hangi dosya ya da klasör üzerinde çalışacağımı söylemen lazım.")

    hedef_yol = Path(target.strip().strip('"')).expanduser()
    if not hedef_yol.exists():
        return fail(f"Bulamadım: {hedef_yol}")

    engel = _yol_guvenli(hedef_yol)
    if engel:
        return fail(f"Bu işlemi yapmadım — {engel}.")

    dosyalar = _hedef_dosyalar(hedef_yol, pattern)
    if not dosyalar:
        nerede = f"'{pattern}' desenine uyan " if pattern.strip() else ""
        return fail(f"{hedef_yol} içinde {nerede}dosya bulamadım.")
    if len(dosyalar) > MAX_FILES:
        return fail(
            f"{len(dosyalar)} dosya var, tek seferde en fazla {MAX_FILES} işliyorum. "
            "Daha dar bir desen ver (ör. pattern='*.jpg')."
        )

    # ── Sıralı adlandırma ───────────────────────────────────────────────────
    if islem in ("sequence", "sirala", "sıralı", "sequential"):
        try:
            baslangic = max(1, int(start))
        except (TypeError, ValueError):
            baslangic = 1
        plan = _sirali_plan(_sirala(dosyalar, sort_by), baslangic)

        if not confirm:
            return ok(
                f"{len(plan)} dosya şöyle adlandırılacak:\n{_ozet(plan)}\n\nOnaylıyor musun?",
                needs_confirmation=True,
                count=len(plan),
                preview=[f"{k.name} → {h.name}" for k, h in plan],
            )

        islenen, hatalar = _iki_fazli_adlandir(plan)
        mesaj = f"{islenen} dosyayı {baslangic}'den başlayarak sıraladım."
        if hatalar:
            mesaj += f" {len(hatalar)} tanesinde sorun çıktı: {'; '.join(hatalar[:3])}"
        return ok(mesaj, count=islenen, errors=hatalar)

    # ── Geri Dönüşüm Kutusu'na silme (onay YOK — geri alınabilir) ───────────
    if islem in ("delete", "sil", "trash"):
        if not HAS_SEND2TRASH:
            return fail(
                "Geri Dönüşüm Kutusu'na göndermek için 'send2trash' kurulu değil. "
                "Kalıcı silmek istersen action='delete_permanent' kullan."
            )
        silinen, hatalar = 0, []
        for p in dosyalar:
            try:
                send2trash(str(p))
                silinen += 1
            except Exception as exc:
                hatalar.append(f"{p.name}: {exc}")
        mesaj = f"{silinen} dosyayı Geri Dönüşüm Kutusu'na gönderdim (geri alabilirsin)."
        if hatalar:
            mesaj += f" {len(hatalar)} tanesi silinemedi."
        return ok(mesaj, count=silinen, errors=hatalar, recoverable=True)

    # ── Kalıcı silme (HER ZAMAN onay) ──────────────────────────────────────
    if islem in ("delete_permanent", "kalici_sil", "kalıcı sil"):
        if not confirm:
            return ok(
                f"{len(dosyalar)} dosyayı KALICI olarak sileceğim — Geri Dönüşüm "
                f"Kutusu'na gitmeyecek, geri alınamaz:\n{chr(10).join(p.name for p in dosyalar[:8])}"
                + (f"\n... ve {len(dosyalar) - 8} dosya daha" if len(dosyalar) > 8 else "")
                + "\n\nEmin misin?",
                needs_confirmation=True,
                count=len(dosyalar),
            )
        silinen, hatalar = 0, []
        for p in dosyalar:
            try:
                p.unlink()
                silinen += 1
            except Exception as exc:
                hatalar.append(f"{p.name}: {exc}")
        return ok(f"{silinen} dosyayı kalıcı olarak sildim.", count=silinen, errors=hatalar)

    # ── Taşıma / kopyalama ─────────────────────────────────────────────────
    if islem in ("move", "tasi", "taşı", "copy", "kopyala"):
        if not destination.strip():
            return fail("Nereye taşıyacağımı/kopyalayacağımı söylemen lazım.")
        varis = Path(destination.strip().strip('"')).expanduser()
        engel = _yol_guvenli(varis)
        if engel:
            return fail(f"Bu işlemi yapmadım — {engel}.")
        varis.mkdir(parents=True, exist_ok=True)

        kopyala = islem in ("copy", "kopyala")
        if not confirm and len(dosyalar) > 1:
            fiil = "kopyalanacak" if kopyala else "taşınacak"
            return ok(
                f"{len(dosyalar)} dosya {varis} klasörüne {fiil}. Onaylıyor musun?",
                needs_confirmation=True,
                count=len(dosyalar),
            )

        islenen, hatalar = 0, []
        for p in dosyalar:
            try:
                # Aynı adlı dosya varsa üzerine YAZMA — sonuna sayı ekle.
                hedef = varis / p.name
                sayac = 1
                while hedef.exists():
                    hedef = varis / f"{p.stem} ({sayac}){p.suffix}"
                    sayac += 1
                if kopyala:
                    shutil.copy2(str(p), str(hedef))
                else:
                    shutil.move(str(p), str(hedef))
                islenen += 1
            except Exception as exc:
                hatalar.append(f"{p.name}: {exc}")
        fiil = "kopyaladım" if kopyala else "taşıdım"
        mesaj = f"{islenen} dosyayı {varis} klasörüne {fiil}."
        if hatalar:
            mesaj += f" {len(hatalar)} tanesinde sorun çıktı."
        return ok(mesaj, count=islenen, errors=hatalar)

    # ── Tekil yeniden adlandırma ───────────────────────────────────────────
    if islem in ("rename", "yeniden_adlandir", "adlandır"):
        if not destination.strip():
            return fail("Yeni adı söylemen lazım.")
        if len(dosyalar) != 1:
            return fail(
                f"'rename' tek dosya içindir ama {len(dosyalar)} dosya eşleşti. "
                "Toplu adlandırma için action='sequence' kullan."
            )
        kaynak = dosyalar[0]
        yeni_ad = destination.strip().strip('"')
        # Uzantı verilmediyse mevcut uzantıyı koru.
        yeni = kaynak.with_name(yeni_ad if Path(yeni_ad).suffix else yeni_ad + kaynak.suffix)
        if yeni.exists():
            return fail(f"'{yeni.name}' zaten var, üzerine yazmadım.")
        try:
            kaynak.rename(yeni)
        except Exception as exc:
            return fail(f"Yeniden adlandıramadım: {exc}")
        return ok(f"'{kaynak.name}' → '{yeni.name}' olarak değiştirdim.", path=str(yeni))

    return fail(
        f"Bilinmeyen işlem: '{action}'. Kullanılabilir: sequence, rename, move, "
        "copy, delete, delete_permanent."
    )
