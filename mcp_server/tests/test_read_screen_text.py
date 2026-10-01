from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from actions import screen_vision
from mcp_server.tests.conftest import FIXTURES, error_text

pytestmark = pytest.mark.anyio

TEXT_IMAGE = FIXTURES / "text_sample.png"


async def test_reads_text_from_image_file(client):
    result = await client.call_tool("read_screen_text", {"source": "image", "image_path": str(TEXT_IMAGE)})
    assert not result.is_error
    data = result.structured_content
    assert data["text"] == "AIRON MCP TEST Kahve 42 TL"
    assert [line["text"] for line in data["lines"]] == ["AIRON MCP TEST", "Kahve 42 TL"]
    for line in data["lines"]:
        assert all(0.0 <= v <= 1.0 for v in line["box"])


async def test_blank_image_returns_empty_text_not_error(client):
    result = await client.call_tool("read_screen_text", {"source": "image", "image_path": str(FIXTURES / "blank.png")})
    assert not result.is_error
    assert result.structured_content["text"] == ""
    assert result.structured_content["lines"] == []


async def test_screen_source_reads_capture_and_deletes_temp_file(client, monkeypatch, tmp_path):
    shot = tmp_path / "airon-screen-test.png"
    shutil.copy(TEXT_IMAGE, shot)
    monkeypatch.setattr(screen_vision, "_capture_active_window", lambda: (True, str(shot), "Test Window"))

    result = await client.call_tool("read_screen_text", {"source": "screen"})

    assert not result.is_error
    assert result.structured_content["source"] == "screen"
    assert result.structured_content["window_title"] == "Test Window"
    assert "AIRON MCP TEST" in result.structured_content["text"]
    assert not shot.exists(), "Ekran görüntüsü diskte bırakılmamalı"


async def test_screen_capture_failure_is_reported(client, monkeypatch):
    monkeypatch.setattr(screen_vision, "_capture_active_window", lambda: (False, "Ekran görüntüsü alınamadı: test", ""))
    result = await client.call_tool("read_screen_text", {"source": "screen"})
    assert "Ekran görüntüsü alınamadı" in error_text(result)


async def test_missing_file(client):
    result = await client.call_tool("read_screen_text", {"source": "image", "image_path": str(FIXTURES / "yok.png")})
    assert "bulunamadı" in error_text(result)


async def test_image_source_requires_path(client):
    result = await client.call_tool("read_screen_text", {"source": "image"})
    assert "image_path zorunlu" in error_text(result)


async def test_relative_path_rejected(client):
    result = await client.call_tool("read_screen_text", {"source": "image", "image_path": "text_sample.png"})
    assert "mutlak" in error_text(result)


async def test_unsupported_extension(client, tmp_path):
    note = tmp_path / "notes.txt"
    note.write_text("hello", encoding="utf-8")
    result = await client.call_tool("read_screen_text", {"source": "image", "image_path": str(note)})
    assert "Desteklenmeyen dosya türü" in error_text(result)


async def test_corrupt_image(client):
    result = await client.call_tool("read_screen_text", {"source": "image", "image_path": str(FIXTURES / "corrupt.png")})
    assert "okunabilir bir görüntü değil" in error_text(result)


async def test_invalid_source_value_rejected_by_schema(client):
    result = await client.call_tool("read_screen_text", {"source": "webcam"})
    assert "source" in error_text(result)


# ── Çapraz inceleme sonrası eklenenler ──────────────────────────────────────

# Ters eğik çizgiler chr(92) ile kuruluyor: kaçış karakteri karmaşası olmasın.
BS = chr(92)
UNC_PATHS = [
    BS * 2 + "evil-host" + BS + "share" + BS + "shot.png",
    "//evil-host/share/shot.png",
    BS * 2 + "?" + BS + "UNC" + BS + "evil-host" + BS + "share" + BS + "a.png",
]


@pytest.mark.parametrize("unc", UNC_PATHS)
async def test_network_paths_rejected_without_touching_them(client, no_network, unc):
    result = await client.call_tool("read_screen_text", {"source": "image", "image_path": unc})
    assert "Ağ yolları" in error_text(result)
    assert no_network == []


async def test_link_pointing_to_network_share_rejected(client, monkeypatch):
    from mcp_server import tools

    link = FIXTURES / "text_sample.png"
    real_readlink = tools.os.readlink

    def fake_readlink(p):
        if Path(p) == FIXTURES:
            return BS * 2 + "evil-host" + BS + "share"
        return real_readlink(p)

    monkeypatch.setattr(tools.os, "readlink", fake_readlink)
    result = await client.call_tool("read_screen_text", {"source": "image", "image_path": str(link)})
    assert "Ağ konumuna yönlenen bağlantı" in error_text(result)


async def test_decompression_bomb_rejected(client, tmp_path):
    from PIL import Image

    bomb = tmp_path / "bomb.png"
    Image.new("1", (10_000, 5_000)).save(bomb)  # 50 MP, dosya birkaç KB
    assert bomb.stat().st_size < 200_000
    result = await client.call_tool("read_screen_text", {"source": "image", "image_path": str(bomb)})
    assert "çözünürlüğü çok yüksek" in error_text(result)


async def test_permission_error_has_readable_message(client, monkeypatch):
    def denied(self):
        raise PermissionError(13, "Erişim engellendi")

    monkeypatch.setattr(Path, "read_bytes", denied)
    result = await client.call_tool("read_screen_text", {"source": "image", "image_path": str(TEXT_IMAGE)})
    assert "Dosya okunamadı (PermissionError)" in error_text(result)


async def test_missing_ocr_model_is_an_error_not_empty_text(client, monkeypatch):
    import easyocr

    from actions import ocr

    def no_model(*args, **kwargs):
        assert kwargs.get("download_enabled") is False, "MCP tarafı modeli asla indirmemeli"
        raise FileNotFoundError("craft_mlt_25k.pth bulunamadı")

    ocr._reader.release()  # okuyucu boş başlasın (core/idle_model.py)
    monkeypatch.setattr(easyocr, "Reader", no_model)
    result = await client.call_tool("read_screen_text", {"source": "image", "image_path": str(TEXT_IMAGE)})
    assert "OCR modeli yüklenemedi" in error_text(result)
