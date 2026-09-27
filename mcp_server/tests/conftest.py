"""
Testler server'ı GERÇEK MCP protokolü üzerinden çağırıyor (süreç içi `Client`):
şema doğrulaması, argüman bağlama ve hata dönüşü dahil, istemcinin göreceği
her şey test ediliyor — sadece Python fonksiyonları değil.

Deterministiklik:
- Ekran, pencere, bildirim ve hafıza gibi makineye bağlı kaynaklar monkeypatch
  ile sabit verilere bağlanıyor. Gerçek memory.json'a hiçbir test dokunmuyor.
- OCR gerçek EasyOCR modeliyle, repodaki sabit görüntüler üzerinde çalışıyor.
- Ağ kapalı: loopback dışındaki her bağlantı denemesi testi düşürür.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest
from mcp import Client

from mcp_server.server import server

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def anyio_backend():
    return "asyncio"


LOOPBACK = ("127.0.0.1", "::1", "localhost")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Loopback dışı bağlantı ve DNS çözümlemesini engeller VE kaydeder.

    Sadece exception atmak yetmiyor: OCR gibi hatayı yutan bir katman denemeyi
    sessizce "boş sonuç"a çevirip testi geçirebilir. Bu yüzden her deneme bir
    listeye yazılıyor ve test bitince liste boş değilse test düşüyor.
    """
    attempts: list[str] = []
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_sendto = socket.socket.sendto
    real_getaddrinfo = socket.getaddrinfo

    def _check(what: str, host) -> None:
        if host not in LOOPBACK:
            attempts.append(f"{what} {host!r}")
            raise RuntimeError(f"Testte ağ erişimi yasak: {what} {host!r}")

    def _host(address):
        return address[0] if isinstance(address, tuple) else address

    def guarded_connect(sock, address):
        _check("connect", _host(address))
        return real_connect(sock, address)

    def guarded_connect_ex(sock, address):
        _check("connect_ex", _host(address))
        return real_connect_ex(sock, address)

    def guarded_sendto(sock, data, *args):
        _check("sendto", _host(args[-1]))
        return real_sendto(sock, data, *args)

    def guarded_getaddrinfo(host, *args, **kwargs):
        _check("getaddrinfo", host)
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket.socket, "sendto", guarded_sendto)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    yield attempts
    assert not attempts, f"Test ağa çıkmaya çalıştı: {attempts}"


@pytest.fixture
async def client():
    async with Client(server) as c:
        yield c


def error_text(result) -> str:
    assert result.is_error, f"Hata bekleniyordu, başarı döndü: {result.structured_content}"
    return result.content[0].text
