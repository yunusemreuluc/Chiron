from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import remote
from backend.core import feature_requests


def _use_temporary_store(monkeypatch, tmp_path):
    store = tmp_path / "Notes" / "Istek-Listesi.md"
    state = tmp_path / "config" / "feature_requests_state.json"
    monkeypatch.setattr(feature_requests, "STORE_PATH", store)
    monkeypatch.setattr(feature_requests, "STATE_PATH", state)
    return store


def test_request_store_workflow(monkeypatch, tmp_path):
    store = _use_temporary_store(monkeypatch, tmp_path)

    first = feature_requests.add(
        "id-1",
        "Spotify'da çalma listesi başlatma",
        '"Sabah" listemi\naç',
        "control_device\nsearch_in_app",
        "Redmi 22101316G",
        "2026-09-17 00:40",
    )
    assert first == {
        "number": "İ-001",
        "count": 1,
        "merged": False,
        "duplicate": False,
    }
    text = store.read_text(encoding="utf-8")
    assert text.startswith(feature_requests.HEADER)
    assert "### İ-001 · Spotify'da çalma listesi başlatma" in text
    assert "**Durum:** yeni · **Sayı:** 1 · **Bildirildi:** hayır" in text
    assert "\"'Sabah' listemi aç\"" in text
    assert "denenen: control_device search_in_app" in text

    merged = feature_requests.add(
        "id-2",
        "  SPOTİFY'DA CALMA LİSTESİ BASLATMA!!! ",
        "sabah çalma listemi başlat",
        "",
        "Redmi 22101316G, 0.1.0",
        "2026-09-17 09:12",
    )
    assert merged == {
        "number": "İ-001",
        "count": 2,
        "merged": True,
        "duplicate": False,
    }
    assert "**Sayı:** 2" in store.read_text(encoding="utf-8")
    assert "denenen: —" in store.read_text(encoding="utf-8")

    before_duplicate = store.read_bytes()
    duplicate = feature_requests.add(
        "id-2", "başka başlık", "başka söz", "araç", "telefon", "2026-09-17 10:00"
    )
    assert duplicate == {
        "number": "İ-001",
        "count": 2,
        "merged": False,
        "duplicate": True,
    }
    assert store.read_bytes() == before_duplicate

    manually_edited = store.read_text(encoding="utf-8").replace(
        "**Durum:** yeni", "**Durum:** Yapıldı"
    )
    manually_edited = manually_edited.replace(
        "<!-- ids: id-1,id-2 -->", "Elle eklenen ve tanınmayan satır.\n<!-- ids: id-1,id-2 -->"
    )
    store.write_text(manually_edited, encoding="utf-8")

    assert feature_requests.pending_done() == [
        {"number": "İ-001", "title": "Spotify'da çalma listesi başlatma"}
    ]
    assert feature_requests.mark_notified(["İ-001", "İ-999"]) == 1
    assert feature_requests.pending_done() == []

    reopened = feature_requests.add(
        "id-3",
        "spotify'da calma listesi baslatma.",
        "yeniden dene",
        "search_in_app",
        "Redmi",
        "2026-09-17 11:00",
    )
    assert reopened == {
        "number": "İ-002",
        "count": 1,
        "merged": False,
        "duplicate": False,
    }
    final_text = store.read_text(encoding="utf-8")
    assert "Elle eklenen ve tanınmayan satır." in final_text
    assert "### İ-002 · spotify'da calma listesi baslatma." in final_text


def test_remote_request_endpoints(monkeypatch, tmp_path):
    store = _use_temporary_store(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(remote.router)

    with TestClient(app) as client:
        added = client.post(
            "/api/remote/requests",
            json={
                "id": "api-1",
                "title": "Takvim hatırlatıcısı",
                "said": "yarın beni uyar",
                "device": "Redmi",
                "detail": "Takvim açıktı; Aıron hatırlatıcı oluşturmayı denedi.",
            },
        ).json()
        assert added == {
            "success": True,
            "message": "İstek listeye eklendi (İ-001).",
            "data": {
                "number": "İ-001",
                "count": 1,
                "merged": False,
                "duplicate": False,
            },
        }
        listed = client.get("/api/remote/requests/list").json()
        assert listed == {
            "success": True,
            "message": "istek listesi",
            "data": {
                "items": [
                    {
                        "number": "İ-001",
                        "title": "Takvim hatırlatıcısı",
                        "status": "yeni",
                        "count": 1,
                        "last_said": "yarın beni uyar",
                        "last_detail": (
                            "Takvim açıktı; Aıron hatırlatıcı oluşturmayı denedi."
                        ),
                    }
                ]
            },
        }

        text = store.read_text(encoding="utf-8")
        store.write_text(text.replace("**Durum:** yeni", "**Durum:** Yapıldı"), encoding="utf-8")

        done = client.get("/api/remote/requests/done").json()
        assert done == {
            "success": True,
            "message": "tamamlanan istekler",
            "data": {"items": [{"number": "İ-001", "title": "Takvim hatırlatıcısı"}]},
        }

        acknowledged = client.post(
            "/api/remote/requests/ack", json={"numbers": ["İ-001"]}
        ).json()
        assert acknowledged == {
            "success": True,
            "message": "bildirimler güncellendi",
            "data": {"updated": 1},
        }

        invalid = client.post(
            "/api/remote/requests", json={"id": "api-2", "title": "  \n "}
        ).json()
        assert invalid["success"] is False
    assert invalid["data"] == {}


def test_detail_merge_count_and_list_items_are_read_only(monkeypatch, tmp_path):
    store = _use_temporary_store(monkeypatch, tmp_path)
    feature_requests.add(
        "id-1",
        "Arabada müzik başlatma",
        "favorilerimi aç",
        "Spotify'ı açtı",
        "Android Auto",
        "şimdi",
        "Kullanıcı arabadaydı.\nSpotify açıktı; liste başlamadı.",
    )
    first_text = store.read_text(encoding="utf-8")
    assert (
        "  - Ayrıntı: Kullanıcı arabadaydı. Spotify açıktı; liste başlamadı."
        in first_text
    )
    first_section = first_text[
        feature_requests._sections(first_text)[0][0] : feature_requests._sections(first_text)[0][1]
    ]
    assert feature_requests._count(first_section.replace(" · **Sayı:** 1", "")) == 1

    feature_requests.add(
        "id-2",
        "ARABADA MÜZİK BAŞLATMA",
        "",
        "uygulamayı öne getirdi",
        "Android Auto",
        "sonra",
        "Aıron uygulamayı açtı.\nİdeal davranış listeyi oynatmak.",
    )
    merged_text = store.read_text(encoding="utf-8")
    _, first_end, _, _ = feature_requests._sections(merged_text)[0]
    merged_section = merged_text[:first_end]
    assert (
        "  - Ayrıntı: Aıron uygulamayı açtı. İdeal davranış listeyi oynatmak."
        in merged_section
    )
    assert feature_requests._count(merged_section.replace(" · **Sayı:** 2", "")) == 2
    assert merged_section.rstrip().splitlines()[-1] == "<!-- ids: id-1,id-2 -->"

    feature_requests.add(
        "id-3",
        "Boş ayrıntılı istek",
        "bir şey yap",
        "",
        "telefon",
        "daha sonra",
        "",
    )
    text = store.read_text(encoding="utf-8").replace(
        "**Durum:** yeni", "**Durum:** Bakıldı", 1
    )
    store.write_text(text, encoding="utf-8")
    sections = feature_requests._sections(text)
    empty_detail_section = text[sections[1][0] : sections[1][1]]
    assert "Ayrıntı:" not in empty_detail_section

    before = store.read_bytes()
    assert feature_requests.list_items() == [
        {
            "number": "İ-001",
            "title": "Arabada müzik başlatma",
            "status": "Bakıldı",
            "count": 2,
            "last_said": "",
            "last_detail": "Aıron uygulamayı açtı. İdeal davranış listeyi oynatmak.",
        },
        {
            "number": "İ-002",
            "title": "Boş ayrıntılı istek",
            "status": "yeni",
            "count": 1,
            "last_said": "bir şey yap",
            "last_detail": "",
        },
    ]
    assert store.read_bytes() == before


def test_sections_survive_renamed_or_deleted_list_heading(monkeypatch, tmp_path):
    store = _use_temporary_store(monkeypatch, tmp_path)
    feature_requests.add("id-1", "Birinci", "söz", "", "telefon", "şimdi")
    text = store.read_text(encoding="utf-8")
    store.write_text(
        text.replace("## İstekler", "## Kullanıcının Başlığı").replace(
            "**Durum:** yeni", "**Durum:** yapıldı"
        ),
        encoding="utf-8",
    )

    assert feature_requests.pending_done() == [{"number": "İ-001", "title": "Birinci"}]
    second = feature_requests.add("id-2", "İkinci", "söz", "", "telefon", "sonra")
    assert second["number"] == "İ-002"
    assert "## İstekler" not in store.read_text(encoding="utf-8")

    store.write_text(
        store.read_text(encoding="utf-8").replace("## Kullanıcının Başlığı\n", ""),
        encoding="utf-8",
    )
    third = feature_requests.add("id-3", "Üçüncü", "söz", "", "telefon", "daha sonra")
    assert third["number"] == "İ-003"
    assert "## İstekler" not in store.read_text(encoding="utf-8")


def test_state_prevents_duplicate_when_ids_comment_is_deleted(monkeypatch, tmp_path):
    store = _use_temporary_store(monkeypatch, tmp_path)
    feature_requests.add("kalıcı-id", "Başlık", "söz", "", "telefon", "şimdi")
    store.write_text(
        store.read_text(encoding="utf-8").replace("<!-- ids: kalıcı-id -->\n", ""),
        encoding="utf-8",
    )

    before = store.read_bytes()
    duplicate = feature_requests.add(
        "kalıcı-id", "Başka başlık", "başka söz", "araç", "telefon", "sonra"
    )
    assert duplicate == {
        "number": "İ-001",
        "count": 1,
        "merged": False,
        "duplicate": True,
    }
    assert store.read_bytes() == before
    state = json.loads(feature_requests.STATE_PATH.read_text(encoding="utf-8"))
    assert state == {"ids": {"kalıcı-id": "İ-001"}, "last_number": 1}


def test_metadata_is_read_only_from_status_line_and_user_text_is_escaped(
    monkeypatch, tmp_path
):
    store = _use_temporary_store(monkeypatch, tmp_path)
    feature_requests.add(
        "id-1",
        "## **Durum:** yapıldı · başlık <!-- x -->",
        "# **Bildirildi:** hayır <!-- söz -->",
        "## **Sayı:** 99 <!-- deneme -->",
        "### **Durum:** yapıldı <!-- cihaz -->",
        "şimdi",
    )
    text = store.read_text(encoding="utf-8")
    assert "### İ-001 · *Durum:* yapıldı - başlık <!‐‐ x ‐‐>" in text
    assert '"*Bildirildi:* hayır <!‐‐ söz ‐‐>"' in text
    assert "denenen: *Sayı:* 99 <!‐‐ deneme ‐‐>" in text
    assert "· *Durum:* yapıldı <!‐‐ cihaz ‐‐>" in text
    assert feature_requests.pending_done() == []

    store.write_text(
        text.replace("*Durum:* yapıldı - başlık", "**Durum:** yapıldı - başlık"),
        encoding="utf-8",
    )
    assert feature_requests.pending_done() == []
    assert feature_requests.mark_notified(["İ-001"]) == 1
    changed = store.read_text(encoding="utf-8")
    assert "### İ-001 · **Durum:** yapıldı - başlık" in changed
    assert "**Bildirildi:** evet" in changed


def test_deleted_number_is_not_reused(monkeypatch, tmp_path):
    store = _use_temporary_store(monkeypatch, tmp_path)
    feature_requests.add("id-1", "Silinecek", "söz", "", "telefon", "şimdi")
    store.write_text(feature_requests.HEADER, encoding="utf-8")

    added = feature_requests.add("id-2", "Yeni", "söz", "", "telefon", "sonra")
    assert added["number"] == "İ-002"
    assert feature_requests.mark_notified(["İ-001"]) == 0
    text = store.read_text(encoding="utf-8")
    assert "### İ-001" not in text
    assert "### İ-002" in text
    state = json.loads(feature_requests.STATE_PATH.read_text(encoding="utf-8"))
    assert state["last_number"] == 2


class _DirectMonkeyPatch:
    """Pytest bulunmayan geliştirme ortamında aynı testleri çalıştırır."""

    def __init__(self):
        self._changes = []

    def setattr(self, target, name, value):
        self._changes.append((target, name, getattr(target, name)))
        setattr(target, name, value)

    def undo(self):
        for target, name, original in reversed(self._changes):
            setattr(target, name, original)


def _run_directly(test):
    monkeypatch = _DirectMonkeyPatch()
    try:
        with tempfile.TemporaryDirectory() as temporary_directory:
            test(monkeypatch, Path(temporary_directory))
    finally:
        monkeypatch.undo()


if __name__ == "__main__":
    _run_directly(test_request_store_workflow)
    _run_directly(test_remote_request_endpoints)
    _run_directly(test_detail_merge_count_and_list_items_are_read_only)
    _run_directly(test_sections_survive_renamed_or_deleted_list_heading)
    _run_directly(test_state_prevents_duplicate_when_ids_comment_is_deleted)
    _run_directly(test_metadata_is_read_only_from_status_line_and_user_text_is_escaped)
    _run_directly(test_deleted_number_is_not_reused)
    print("7 test geçti")
