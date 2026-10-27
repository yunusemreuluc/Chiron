from __future__ import annotations

import json

import pytest

from memory import memory_manager
from mcp_server.tests.conftest import error_text

pytestmark = pytest.mark.anyio

FAKE_MEMORY = {
    "identity": {"name": {"value": "Test User", "_updated_at": "2026-09-01T10:00:00"}},
    "preferences": {
        "drink": {"value": "Türk kahvesi, şekersiz"},
        "music": {"value": "lo-fi while coding"},
    },
    "projects": {"chiron": {"value": "Windows voice assistant with local OCR"}},
    "whatsapp_contacts": {"annem": {"display_name": "Annem", "value": "+90 555 000 00 00", "aliases": ["kahve"]}},
}


@pytest.fixture(autouse=True)
def fake_memory_file(monkeypatch, tmp_path):
    path = tmp_path / "memory.json"
    path.write_text(json.dumps(FAKE_MEMORY, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(memory_manager, "MEMORY_FILE", path)
    return path


async def test_finds_matching_entry(client):
    result = await client.call_tool("search_memory", {"query": "kahve"})
    assert not result.is_error
    matches = result.structured_content["matches"]
    assert matches == [{"category": "preferences", "key": "drink", "value": "Türk kahvesi, şekersiz"}]


async def test_matching_ignores_turkish_accents_and_case(client):
    result = await client.call_tool("search_memory", {"query": "TURK KAHVESI"})
    assert [m["key"] for m in result.structured_content["matches"]] == ["drink"]


async def test_contact_phone_numbers_are_never_returned(client):
    for query in ("annem", "555", "kahve", "whatsapp"):
        result = await client.call_tool("search_memory", {"query": query})
        assert not result.is_error
        # Sorgunun kendisi sonuçta geri yansıyor ("query": "555") — sadece eşleşmelere bak.
        dumped = json.dumps(result.structured_content["matches"], ensure_ascii=False)
        assert "555" not in dumped and "whatsapp_contacts" not in dumped, query


async def test_no_match_is_empty_list_not_error(client):
    result = await client.call_tool("search_memory", {"query": "bisiklet"})
    assert not result.is_error
    assert result.structured_content["matches"] == []


async def test_limit_is_respected(client):
    # "in" üç kayıtta geçiyor: drINk, codINg, WINdows.
    everything = await client.call_tool("search_memory", {"query": "in"})
    assert len(everything.structured_content["matches"]) == 3
    result = await client.call_tool("search_memory", {"query": "in", "limit": 1})
    assert len(result.structured_content["matches"]) == 1


async def test_missing_memory_file_is_not_a_crash(client, fake_memory_file):
    fake_memory_file.unlink()
    result = await client.call_tool("search_memory", {"query": "kahve"})
    assert not result.is_error
    assert result.structured_content["matches"] == []


async def test_too_short_query_rejected(client):
    assert "at least 2" in error_text(await client.call_tool("search_memory", {"query": "k"}))


async def test_punctuation_only_query_rejected(client):
    # Şemayı geçer (2 karakter) ama normalize edilince boş kalır.
    assert "en az 2 karakter" in error_text(await client.call_tool("search_memory", {"query": "  "}))


async def test_limit_out_of_range_rejected(client):
    result = await client.call_tool("search_memory", {"query": "kahve", "limit": 500})
    assert "limit" in error_text(result)


async def test_search_never_writes_memory(client, fake_memory_file):
    before = fake_memory_file.read_bytes()
    await client.call_tool("search_memory", {"query": "kahve"})
    assert fake_memory_file.read_bytes() == before


async def test_phone_numbers_masked_in_any_category(client, fake_memory_file):
    data = dict(FAKE_MEMORY)
    data["notes"] = {"annem_tel": {"value": "Annemin numarası 0 (532) 111-22-33, akşam ara"}}
    data["_archived_summary"] = {"eski_kayitlar": {"value": "notes/dayi: dayının cebi +905441234567"}}
    fake_memory_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    for query in ("annem", "dayi"):
        result = await client.call_tool("search_memory", {"query": query})
        values = [m["value"] for m in result.structured_content["matches"]]
        assert values, query
        joined = " ".join(values)
        assert "[telefon gizlendi]" in joined
        assert "532" not in joined and "5441234567" not in joined


async def test_dates_and_short_numbers_are_not_masked(client, fake_memory_file):
    data = {"notes": {"sinav": {"value": "Sınav 28.09.2026 saat 14:05, salon 204"}}}
    fake_memory_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    result = await client.call_tool("search_memory", {"query": "sinav"})
    assert result.structured_content["matches"][0]["value"] == "Sınav 28.09.2026 saat 14:05, salon 204"
