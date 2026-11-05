"""Canlı oturumun sustuyken ayakta kalması ve olağan kapanışın hata sayılmaması."""
import asyncio
from pathlib import Path

import pytest
from google.genai import errors

from core.live_oturum import (
    KEEPALIVE_SECONDS,
    SILENCE_CHUNK,
    is_expected_close,
    keep_session_alive,
)


def _api_error(code: int, reason: str) -> errors.APIError:
    """SDK'nın canlı oturumda yükselttiği hatanın aynısı (genai/live.py)."""
    with pytest.raises(errors.APIError) as info:
        errors.APIError.raise_error(code, reason, None)
    return info.value


@pytest.mark.parametrize(
    "code, reason",
    [
        (1008, "Session closed due to client inactivity."),
        (1011, "The session duration limit was reached. Connection closed."),
    ],
)
def test_olagan_kapanis_hata_sayilmaz(code, reason):
    exc = _api_error(code, reason)
    assert is_expected_close(exc)
    assert is_expected_close(ExceptionGroup("tg", [exc]))


@pytest.mark.parametrize(
    "code, reason",
    [
        (1011, "You exceeded your current quota, please check your plan."),
        (1011, "The service is currently unavailable."),
        (1008, "Operation is not implemented, or supported, or enabled."),
    ],
)
def test_gercek_ariza_saklanmaz(code, reason):
    assert not is_expected_close(_api_error(code, reason))


def test_olagan_kapanis_yanindaki_arizayi_saklamaz():
    closed = _api_error(1008, "Session closed due to client inactivity.")
    group = ExceptionGroup("tg", [closed, RuntimeError("mikrofon öldü")])
    assert not is_expected_close(group)
    assert not is_expected_close(ExceptionGroup("dış", [group]))


def test_sessizlik_gercekten_sessiz_ve_40_ms():
    assert set(SILENCE_CHUNK) == {0}
    assert len(SILENCE_CHUNK) == 1280


class _Oturum:
    """Sahte saat: her kontrol bir saniye ilerler, `gonderim` kez sonra görev iptal edilir."""

    def __init__(self, gonderim=None, patla=False, adim=None):
        self.now = 1000.0
        self.son = self.now
        self.gidenler: list[float] = []
        self.gonderim = gonderim
        self.patla = patla
        self.adim = adim
        self.kontrol = 0

    def clock(self):
        self.kontrol += 1
        self.now += 1.0
        if self.adim is not None and self.kontrol >= self.adim:
            raise asyncio.CancelledError
        return self.now

    async def send(self, chunk):
        assert chunk == SILENCE_CHUNK
        self.gidenler.append(self.now)
        if self.patla:
            raise ConnectionError("oturum öldü")
        self.son = self.now
        if self.gonderim is not None and len(self.gidenler) >= self.gonderim:
            raise asyncio.CancelledError

    def calistir(self):
        async def _run():
            with pytest.raises(asyncio.CancelledError):
                await keep_session_alive(
                    self.send, lambda: self.son, lambda: False, clock=self.clock, tick=0
                )

        asyncio.run(_run())


def test_uzun_sessizlikte_duzenli_gonderir():
    oturum = _Oturum(gonderim=3)
    oturum.calistir()
    assert oturum.gidenler[0] - 1000.0 == KEEPALIVE_SECONDS
    assert oturum.gidenler[1] - oturum.gidenler[0] == KEEPALIVE_SECONDS
    assert oturum.gidenler[2] - oturum.gidenler[1] == KEEPALIVE_SECONDS


def test_sunucunun_kesme_suresinden_cok_once_gonderir():
    assert KEEPALIVE_SECONDS * 2 < 120


def test_ses_akarken_sessizlik_gondermez():
    oturum = _Oturum(adim=100)
    original_clock = oturum.clock

    def _hep_taze():
        now = original_clock()
        oturum.son = now  # mikrofon sürekli gönderiyor
        return now

    oturum.clock = _hep_taze
    oturum.calistir()
    assert oturum.gidenler == []


def test_engelliyken_gondermez():
    """Duraklatma ya da süren araç çağrısı: ne kadar beklenirse beklensin giriş gitmez."""
    oturum = _Oturum()
    oturum.son = 0.0  # son sesin üstünden çok geçmiş: engel olmasa hemen giderdi
    kontroller = []

    def _engelli():
        kontroller.append(1)
        if len(kontroller) >= 50:
            raise asyncio.CancelledError
        return True

    async def _run():
        with pytest.raises(asyncio.CancelledError):
            await keep_session_alive(oturum.send, lambda: oturum.son, _engelli, clock=oturum.clock, tick=0)

    asyncio.run(_run())
    assert oturum.gidenler == []


def test_gonderim_hatasi_gorevi_dusurmez_ve_tekrar_dener():
    """Patlarsa TaskGroup'u yıkıp gerçek kapanış sebebinin önüne geçmemeli."""
    oturum = _Oturum(patla=True, adim=30)
    oturum.calistir()
    assert len(oturum.gidenler) >= 2  # `son` güncellenmedi: "gitti" sayılmadı


def test_run_dongusune_bagli():
    """main.py testte yüklenemiyor (ses aygıtı); bağlantı kaynaktan doğrulanıyor."""
    source = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
    assert "tg.create_task(keep_session_alive(" in source
    assert source.count("is_expected_close(e)") == 2
