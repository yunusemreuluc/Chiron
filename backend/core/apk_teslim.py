"""APK teslimi — derlenen APK'yı telefona adb'siz ulaştırır (2026-10-29).

Kullanıcı sorusu: "işteyken Chiron Dilcep'i yapar ama telefona kuramaz, sunucu alsam çözülür mü?" Hayır: adb
kablosuz hata ayıklamaya bağlı, o da yalnız Wi-Fi'da açık. Çözüm kurulumu telefona bırakmak: PC APK'yı burada
yayınlar, telefondaki Chiron mevcut Tailscale + PIN bağlantısıyla indirir, sha256'yı doğrular ve "Yükle"
bildirimi gösterir. Son dokunuş Android gereği kullanıcıda; imza tutmazsa Android güncellemeyi zaten reddeder.

Yayınlama (Claude işinin içinden, Chiron'un venv'iyle):
    python -m backend.core.apk_teslim <apk-yolu> --ad Dilcep [--not "alt bar değişti"]
Telefon uçları: backend/api/remote.py → GET /api/remote/apk, GET /api/remote/apk/{id}/indir (PIN'li).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import sys
import threading
import time
import zipfile
from pathlib import Path
from typing import Any

STORE_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "chiron" / "apk"
KEEP = 5  # telefona gönderilmiş son APK'lar; eskiler silinir
MAX_BYTES = 300 * 1024 * 1024
MAX_NAME = 40
MAX_NOTE = 300

_lock = threading.Lock()


class ApkError(Exception):
    """Kullanıcıya gösterilecek hata."""


def _index_path(store: Path) -> Path:
    return store / "index.json"


def _read(store: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(_index_path(store).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return []
    return [item for item in data if isinstance(item, dict) and item.get("id")] if isinstance(data, list) else []


def _write(store: Path, items: list[dict[str, Any]]) -> None:
    store.mkdir(parents=True, exist_ok=True)
    tmp = _index_path(store).with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, _index_path(store))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def publish(apk: Path, name: str, note: str = "", store: Path | None = None) -> dict[str, Any]:
    """APK'yı kutuya kopyalar ve listeye ekler (en yeni başta)."""
    store = store or STORE_DIR
    apk = Path(apk)
    if not apk.is_file():
        raise ApkError(f"APK yok: {apk}")
    if apk.suffix.lower() != ".apk":
        raise ApkError("Yalnız .apk dosyası gönderilir.")
    size = apk.stat().st_size
    if size > MAX_BYTES:
        raise ApkError(f"APK çok büyük ({size // (1024 * 1024)} MB).")
    # Bozuk/yarım derleme telefona gitmesin: APK bir zip ve içinde manifest olmalı.
    try:
        with zipfile.ZipFile(apk) as archive:
            if "AndroidManifest.xml" not in archive.namelist():
                raise ApkError("Dosya geçerli bir APK değil (AndroidManifest.xml yok).")
    except zipfile.BadZipFile as error:
        raise ApkError("Dosya geçerli bir APK değil.") from error
    name = " ".join((name or "").split())[:MAX_NAME] or apk.stem
    item = {
        "id": secrets.token_hex(6),
        "name": name,
        "note": " ".join((note or "").split())[:MAX_NOTE],
        "size": size,
        "sha256": _sha256(apk),
        "created": time.time(),
    }
    with _lock:
        store.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(apk, store / f"{item['id']}.apk")
        items = [item, *_read(store)]
        for old in items[KEEP:]:
            (store / f"{old['id']}.apk").unlink(missing_ok=True)
        _write(store, items[:KEEP])
    return item


def listing(store: Path | None = None) -> list[dict[str, Any]]:
    store = store or STORE_DIR
    with _lock:
        return [item for item in _read(store) if (store / f"{item['id']}.apk").is_file()]


def file_for(apk_id: str, store: Path | None = None) -> tuple[dict[str, Any], Path]:
    store = store or STORE_DIR
    with _lock:
        item = next((i for i in _read(store) if i["id"] == apk_id), None)
    # Kimlik yalnız listeden gelir; yol kullanıcı girdisinden kurulmaz.
    path = store / f"{item['id']}.apk" if item else None
    if not item or not path or not path.is_file():
        raise ApkError("APK bulunamadı.")
    return item, path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="APK'yı telefona gönder (Chiron indirip Yükle bildirimi gösterir).")
    parser.add_argument("apk", type=Path)
    parser.add_argument("--ad", required=True, help="Uygulama adı, ör. Dilcep")
    parser.add_argument("--not", dest="note", default="", help="Telefonda görünecek kısa not")
    args = parser.parse_args(argv)
    try:
        item = publish(args.apk, args.ad, args.note)
    except ApkError as error:
        print(f"HATA: {error}", file=sys.stderr)
        return 1
    print(f"Gönderildi: {item['name']} ({item['size'] // 1024} KB, kimlik {item['id']}). "
          "Telefondaki Chiron bir dakika içinde indirip 'Yükle' bildirimi gösterir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
