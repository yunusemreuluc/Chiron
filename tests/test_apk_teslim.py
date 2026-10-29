"""APK teslimi: yayınla, listele, indir; bozuk dosya ve eski kayıtlar."""

from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.api import remote as remote_api  # noqa: E402
from backend.core import apk_teslim  # noqa: E402


def _apk(path: Path, body: bytes = b"dex") -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"manifest")
        archive.writestr("classes.dex", body)
    return path


def test_publish_lists_newest_first_and_keeps_last_five(tmp_path):
    store = tmp_path / "kutu"
    ids = [
        apk_teslim.publish(_apk(tmp_path / f"a{i}.apk", bytes([i])), "Dilcep", f"sürüm {i}", store=store)["id"]
        for i in range(apk_teslim.KEEP + 2)
    ]
    listed = apk_teslim.listing(store)
    assert [item["id"] for item in listed] == list(reversed(ids))[: apk_teslim.KEEP]
    assert not (store / f"{ids[0]}.apk").exists()  # en eski silindi
    item, path = apk_teslim.file_for(ids[-1], store)
    assert item["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest() and item["note"] == f"sürüm {apk_teslim.KEEP + 1}"


def test_rejects_non_apk_and_unknown_ids(tmp_path):
    store = tmp_path / "kutu"
    not_zip = tmp_path / "bozuk.apk"
    not_zip.write_bytes(b"yarim derleme")
    with pytest.raises(apk_teslim.ApkError, match="geçerli"):
        apk_teslim.publish(not_zip, "X", store=store)
    text = tmp_path / "x.txt"
    text.write_text("x")
    with pytest.raises(apk_teslim.ApkError, match=r"\.apk"):
        apk_teslim.publish(text, "X", store=store)
    no_manifest = tmp_path / "eksik.apk"
    with zipfile.ZipFile(no_manifest, "w") as archive:
        archive.writestr("classes.dex", b"x")
    with pytest.raises(apk_teslim.ApkError, match="AndroidManifest"):
        apk_teslim.publish(no_manifest, "X", store=store)
    with pytest.raises(apk_teslim.ApkError):
        apk_teslim.file_for("../../index", store)


def test_remote_endpoints_list_and_download(tmp_path, monkeypatch):
    monkeypatch.setattr(apk_teslim, "STORE_DIR", tmp_path / "kutu")
    item = apk_teslim.publish(_apk(tmp_path / "d.apk"), "Dilcep", "alt bar")
    app = FastAPI()
    app.include_router(remote_api.router)
    client = TestClient(app)

    listed = client.get("/api/remote/apk").json()["data"]["apks"]
    assert [i["id"] for i in listed] == [item["id"]]
    got = client.get(f"/api/remote/apk/{item['id']}/indir")
    assert got.status_code == 200
    assert got.headers["content-type"] == "application/vnd.android.package-archive"
    assert hashlib.sha256(got.content).hexdigest() == item["sha256"] == got.headers["x-chiron-sha256"]
    assert client.get("/api/remote/apk/yok/indir").status_code == 404


def test_cli_publishes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(apk_teslim, "STORE_DIR", tmp_path / "kutu")
    assert apk_teslim.main([str(_apk(tmp_path / "c.apk")), "--ad", "Chiron", "--not", "deneme"]) == 0
    assert "Gönderildi: Chiron" in capsys.readouterr().out
    assert apk_teslim.main([str(tmp_path / "yok.apk"), "--ad", "X"]) == 1
