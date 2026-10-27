"""Telefondan gelen geliştirme isteklerini Obsidian kasasında saklar."""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import unicodedata
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STORE_PATH = PROJECT_ROOT / "Notes" / "Istek-Listesi.md"
STATE_PATH = PROJECT_ROOT / "config" / "feature_requests_state.json"

HEADER = """# İstek Listesi

Telefondaki Chiron'un yapamadığı ve kullanıcının "listeye ekle" dediği istekler.
Durum değerleri: `yeni` → `bakıldı` → `yapıldı` / `yapılmayacak`. Durumu elle değiştirebilirsin;
`yapıldı` olanı telefon bir sonraki konuşmada kullanıcıya haber verir.

## İstekler
"""

_store_lock = threading.Lock()
_request_heading = re.compile(r"^###\s+(İ-\d+)\s+·\s*(.*?)\s*$", re.MULTILINE)
_list_heading = re.compile(r"^##\s+İstekler\s*$", re.MULTILINE)
_level_two_heading = re.compile(r"^##(?!#)\s+", re.MULTILINE)
_upper_heading = re.compile(r"^#{1,2}(?!#)\s+", re.MULTILINE)
_metadata_line = re.compile(r"^\*\*Durum:\*\*.*$", re.IGNORECASE | re.MULTILINE)
_status_field = re.compile(r"^\*\*Durum:\*\*\s*([^·\r\n]+)", re.IGNORECASE)
_count_field = re.compile(r"(\*\*Sayı:\*\*\s*)(\d+)", re.IGNORECASE)
_notified_field = re.compile(
    r"(\*\*Bildirildi:\*\*[ \t]*)([^·\r\n]*?)([ \t]*(?:·|$))", re.IGNORECASE
)
_ids_comment = re.compile(r"^[ \t]*<!--\s*ids:\s*(.*?)\s*-->[ \t]*$", re.MULTILINE)


def _atomic_write(text: str) -> None:
    """Depoyu aynı dizinde oluşturulan geçici dosya üzerinden değiştirir."""
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        dir=STORE_PATH.parent,
        prefix=f".{STORE_PATH.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as temporary:
            temporary.write(text)
        os.replace(temporary_name, STORE_PATH)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _atomic_write_state(state: dict) -> None:
    """Yan durum dosyasını aynı dizinde atomik olarak değiştirir."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        dir=STATE_PATH.parent,
        prefix=f".{STATE_PATH.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as temporary:
            json.dump(state, temporary, ensure_ascii=False, sort_keys=True)
            temporary.write("\n")
        os.replace(temporary_name, STATE_PATH)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _read_state() -> dict:
    if not STATE_PATH.exists():
        return {"ids": {}, "last_number": 0}
    data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    ids = data.get("ids", {})
    last_number = data.get("last_number", 0)
    if not isinstance(ids, dict) or not isinstance(last_number, int):
        raise ValueError("Geçersiz istek durum dosyası.")
    return {
        "ids": {
            str(request_id): str(number)
            for request_id, number in ids.items()
        },
        "last_number": max(0, last_number),
    }


def _read_store() -> str:
    if STORE_PATH.exists():
        return STORE_PATH.read_text(encoding="utf-8")
    _atomic_write(HEADER)
    return HEADER


def _request_area(text: str) -> tuple[int, int]:
    heading = _list_heading.search(text)
    if heading is None:
        return len(text), len(text)
    following_heading = _level_two_heading.search(text, heading.end())
    return heading.end(), following_heading.start() if following_heading else len(text)


def _sections(text: str) -> list[tuple[int, int, str, str]]:
    """İstek bölümlerini ``(baş, son, numara, başlık)`` olarak döndürür."""
    headings = list(_request_heading.finditer(text))
    sections = []
    for index, heading in enumerate(headings):
        candidates = [len(text)]
        if index + 1 < len(headings):
            candidates.append(headings[index + 1].start())
        following_heading = _upper_heading.search(text, heading.end())
        if following_heading:
            candidates.append(following_heading.start())
        sections.append(
            (
                heading.start(),
                min(candidates),
                heading.group(1),
                heading.group(2).strip(),
            )
        )
    return sections


def _clean(value: str, limit: int, *, title: bool = False) -> str:
    value = value.replace("<!--", "<!‐‐").replace("-->", "‐‐>")
    value = re.sub(r"^#+", "", value, flags=re.MULTILINE)
    while "**" in value:
        value = value.replace("**", "*")
    # U+2028/U+2029 ve dikey sekme re ile satır sonu sayılmıyor ama splitlines() bölüyor:
    # okuyucu sahte bir örnek satırı görmesin diye burada da boşluğa çevriliyor.
    value = re.sub(r"[\r\n\u2028\u2029\x0b\x0c\x85]+", " ", value).strip()
    if title:
        value = value.replace("·", "-")
    return value[:limit]


def _normalise(value: str) -> str:
    """Türkçe harfleri ve uç noktalamasını karşılaştırma için sadeleştirir."""
    value = value.strip()
    while value and (value[0].isspace() or unicodedata.category(value[0]).startswith("P")):
        value = value[1:]
    while value and (value[-1].isspace() or unicodedata.category(value[-1]).startswith("P")):
        value = value[:-1]
    value = value.casefold().translate(str.maketrans({"ı": "i", "ş": "s", "ğ": "g"}))
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if unicodedata.category(character) != "Mn"
    )


def _status(section: str) -> str:
    metadata = _metadata_line.search(section)
    match = _status_field.search(metadata.group(0)) if metadata else None
    return _normalise(match.group(1)) if match else ""


def _raw_status(section: str) -> str:
    metadata = _metadata_line.search(section)
    match = _status_field.search(metadata.group(0)) if metadata else None
    return match.group(1).strip() if match else ""


def _normalise_number(number: str) -> str:
    """Kullanıcının yazdığı istek numarasını depo biçimine çevirir."""
    match = re.fullmatch(r"(?:İ|I)-([0-9]+)|([0-9]+)", number.strip())
    if match is None:
        return number.strip()
    value = int(match.group(1) or match.group(2))
    return f"İ-{value:03d}"


def _count(section: str) -> int:
    metadata = _metadata_line.search(section)
    match = _count_field.search(metadata.group(0)) if metadata else None
    if match:
        return int(match.group(2))
    return max(1, sum(line.startswith("- ") for line in section.splitlines()))


def _ids(section: str) -> list[str]:
    match = _ids_comment.search(section)
    if match is None:
        return []
    return [item.strip() for item in match.group(1).split(",") if item.strip()]


def _bullet(at: str, said: str, attempted: str, device: str) -> str:
    return f'- {at} · "{said}" · denenen: {attempted or "—"} · {device}'


def _entry(bullet: str, detail: str) -> str:
    if not detail:
        return bullet
    return f"{bullet}\n  - Ayrıntı: {detail}"


def _merge_section(section: str, request_id: str, entry: str, new_count: int) -> str:
    metadata = _metadata_line.search(section)
    if metadata:
        changed_line = _count_field.sub(
            lambda match: f"{match.group(1)}{new_count}", metadata.group(0), count=1
        )
        section = section[: metadata.start()] + changed_line + section[metadata.end() :]
    ids_match = _ids_comment.search(section)
    if ids_match:
        ids = _ids(section)
        ids.append(request_id)
        section = section[: ids_match.start()] + section[ids_match.end() :]
    else:
        ids = [request_id]

    trailing_newlines = len(section) - len(section.rstrip("\n"))
    core = section[:-trailing_newlines] if trailing_newlines else section
    ending = section[-trailing_newlines:] if trailing_newlines else ""
    separator = "" if core.endswith("\n") else "\n"
    return f"{core}{separator}{entry}\n<!-- ids: {','.join(ids)} -->{ending}"


def _insert_section(text: str, section: str) -> str:
    area_start, area_end = _request_area(text)
    if area_start == area_end == len(text) and _list_heading.search(text) is None:
        separator = (
            ""
            if not text or text.endswith("\n\n")
            else ("\n" if text.endswith("\n") else "\n\n")
        )
        return f"{text}{separator}{section}\n"

    prefix = text[:area_end]
    separator = "" if prefix.endswith("\n\n") else ("\n" if prefix.endswith("\n") else "\n\n")
    return f"{prefix}{separator}{section}\n{text[area_end:]}"


def add(
    request_id: str,
    title: str,
    said: str,
    attempted: str,
    device: str,
    at: str,
    detail: str = "",
) -> dict:
    """Yeni istek açar veya aynı başlıklı açık isteğe bir örnek ekler."""
    title = _clean(title, 120, title=True)
    if not title:
        raise ValueError("İstek başlığı boş olamaz.")
    said = _clean(said, 300).replace('"', "'")
    attempted = _clean(attempted, 300)
    device = _clean(device, 80)
    detail = _clean(detail, 1200)
    request_id = re.sub(r"[\r\n]+", " ", request_id).strip()
    at = re.sub(r"[\r\n]+", " ", at).strip()
    bullet = _bullet(at, said, attempted, device)
    entry = _entry(bullet, detail)

    with _store_lock:
        text = _read_store()
        sections = _sections(text)
        state = _read_state()
        file_largest_number = max(
            (int(number.removeprefix("İ-")) for _, _, number, _ in sections),
            default=0,
        )
        state["last_number"] = max(state["last_number"], file_largest_number)

        sections_by_number = {}
        for start, end, number, _ in sections:
            section = text[start:end]
            sections_by_number[number] = section
            for stored_id in _ids(section):
                state["ids"].setdefault(stored_id, number)

        stored_number = state["ids"].get(request_id)
        if stored_number is not None:
            section = sections_by_number.get(stored_number, "")
            _atomic_write_state(state)
            return {
                "number": stored_number,
                "count": _count(section) if section else 1,
                "merged": False,
                "duplicate": True,
            }

        for start, end, number, _ in sections:
            section = text[start:end]
            if request_id in _ids(section):
                state["ids"][request_id] = number
                _atomic_write_state(state)
                return {
                    "number": number,
                    "count": _count(section),
                    "merged": False,
                    "duplicate": True,
                }

        normalised_title = _normalise(title)
        for start, end, number, existing_title in sections:
            section = text[start:end]
            if (
                _normalise(existing_title) == normalised_title
                and _status(section) not in {"yapildi", "yapilmayacak"}
            ):
                new_count = _count(section) + 1
                updated = _merge_section(section, request_id, entry, new_count)
                _atomic_write(text[:start] + updated + text[end:])
                state["ids"][request_id] = number
                _atomic_write_state(state)
                return {
                    "number": number,
                    "count": new_count,
                    "merged": True,
                    "duplicate": False,
                }

        largest_number = max(file_largest_number, state["last_number"])
        number = f"İ-{largest_number + 1:03d}"
        new_section = (
            f"### {number} · {title}\n"
            "**Durum:** yeni · **Sayı:** 1 · **Bildirildi:** hayır\n"
            f"{entry}\n"
            f"<!-- ids: {request_id} -->\n"
        )
        _atomic_write(_insert_section(text, new_section))
        state["ids"][request_id] = number
        state["last_number"] = largest_number + 1
        _atomic_write_state(state)
        return {"number": number, "count": 1, "merged": False, "duplicate": False}


def list_items(include_removed: bool = False) -> list[dict]:
    """İstek listesini dosyayı değiştirmeden özetler."""
    with _store_lock:
        if not STORE_PATH.exists():
            return []
        text = STORE_PATH.read_text(encoding="utf-8")
        items: list[dict] = []
        for start, end, number, title in _sections(text):
            section = text[start:end]
            # NEDEN: Kullanıcı "sil" dediğinde kayıt geçmişte kalsın ama normal listede görünmesin.
            if not include_removed and _status(section) == "yapilmayacak":
                continue
            last_said = ""
            last_detail = ""
            for line in section.splitlines():
                said_start = line.find(' · "') if line.startswith("- ") else -1
                said_end = line.find('" · denenen:', said_start + 4) if said_start >= 0 else -1
                if said_end >= 0:
                    last_said = line[said_start + 4 : said_end]
                    last_detail = ""  # ayrıntı, altında durduğu örneğe ait
                elif line.startswith("  - Ayrıntı: "):
                    last_detail = line.removeprefix("  - Ayrıntı: ")
            items.append(
                {
                    "number": number,
                    "title": title,
                    "status": _raw_status(section),
                    "count": _count(section),
                    "last_said": last_said,
                    "last_detail": last_detail,
                }
            )
        return items


def remove(number: str) -> dict:
    """İsteği geçmişten silmeden ``yapılmayacak`` olarak işaretler."""
    wanted = _normalise_number(number)
    with _store_lock:
        text = _read_store()
        for start, end, stored_number, title in _sections(text):
            if stored_number != wanted:
                continue
            section = text[start:end]
            result = {
                "number": stored_number,
                "title": title,
                "status": "yapılmayacak",
            }
            if _status(section) == "yapilmayacak":
                return result

            metadata = _metadata_line.search(section)
            status = _status_field.search(metadata.group(0)) if metadata else None
            if status is None:
                raise ValueError(f"İstek {wanted} durum alanı bulunamadı.")
            raw_status = status.group(1)
            leading_space = raw_status[: len(raw_status) - len(raw_status.lstrip())]
            trailing_space = raw_status[len(raw_status.rstrip()) :]
            replacement = f"{leading_space}yapılmayacak{trailing_space}"
            status_start = metadata.start() + status.start(1)
            status_end = metadata.start() + status.end(1)
            changed_section = section[:status_start] + replacement + section[status_end:]
            _atomic_write(text[:start] + changed_section + text[end:])
            return result
    raise ValueError(f"İstek {wanted} bulunamadı.")


def pending_done() -> list[dict]:
    """Tamamlanmış fakat telefonda henüz bildirilmemiş istekleri döndürür."""
    with _store_lock:
        text = _read_store()
        pending: list[dict] = []
        for start, end, number, title in _sections(text):
            section = text[start:end]
            metadata = _metadata_line.search(section)
            notified = _notified_field.search(metadata.group(0)) if metadata else None
            if (
                _status(section) == "yapildi"
                and notified is not None
                and _normalise(notified.group(2)) == "hayir"
            ):
                pending.append({"number": number, "title": title})
        return pending


def mark_notified(numbers: list[str]) -> int:
    """Verilen isteklerin bildirildi alanını ``evet`` yapar."""
    wanted = {number.strip() for number in numbers}
    with _store_lock:
        text = _read_store()
        updated = text
        changed = 0
        offset = 0
        for start, end, number, _ in _sections(text):
            if number not in wanted:
                continue
            section = text[start:end]
            metadata = _metadata_line.search(section)
            notified = _notified_field.search(metadata.group(0)) if metadata else None
            if notified is None or _normalise(notified.group(2)) == "evet":
                continue
            replacement = f"{notified.group(1)}evet{notified.group(3)}"
            notified_start = metadata.start() + notified.start()
            notified_end = metadata.start() + notified.end()
            changed_section = section[:notified_start] + replacement + section[notified_end:]
            actual_start = start + offset
            actual_end = end + offset
            updated = updated[:actual_start] + changed_section + updated[actual_end:]
            offset += len(changed_section) - len(section)
            changed += 1
        if changed:
            _atomic_write(updated)
        return changed
