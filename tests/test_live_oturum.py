"""Canlı oturumun sustuyken ayakta kalması ve olağan kapanışın hata sayılmaması."""
import ast
import asyncio
import logging
import time
from pathlib import Path

import pytest
from google.genai import errors

from backend.core.canli_yukleme import _patch_function
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


def test_ilk_gonderim_baglanti_basina_bir_kez_gunluge_yazilir(caplog):
    """Düzeltmenin devrede olduğunu günlükten görmenin tek yolu; 20 sn'de bir de tekrarlamamalı."""
    oturum = _Oturum(gonderim=3)
    with caplog.at_level(logging.INFO, logger="chiron"):
        oturum.calistir()
    assert len([r for r in caplog.records if "sessizlikle ayakta" in r.getMessage()]) == 1


def test_basarisiz_gonderim_devrede_gibi_yazilmaz(caplog):
    oturum = _Oturum(patla=True, adim=30)
    with caplog.at_level(logging.INFO, logger="chiron"):
        oturum.calistir()
    assert not [r for r in caplog.records if "sessizlikle ayakta" in r.getMessage()]


MAIN_SOURCE = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")


def _chiron_metodu(ad: str) -> ast.AsyncFunctionDef:
    tree = ast.parse(MAIN_SOURCE)
    sinif = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ChironLive")
    return next(n for n in sinif.body if isinstance(n, ast.AsyncFunctionDef) and n.name == ad)


class _CanliNesne:
    """__init__'i yamadan ÖNCE çalışmış nesne: `_last_audio_sent` ve `_tool_call_pending` yok."""

    def __init__(self):
        self.out_queue = asyncio.Queue()
        self.sessizlik = 0
        self.session = self

    async def send_realtime_input(self, media):
        pass

    async def _send_silence(self, chunk):
        self.sessizlik += 1
        self._last_audio_sent = 0.0

    def _keepalive_blocked(self):
        return self._tool_call_pending


def _gonderim_metodu(canli_kod=keep_session_alive):
    """main.py testte yüklenemiyor (ses aygıtı); metot kaynaktan derlenip gerçekten çalıştırılıyor."""
    modul = ast.Module(body=[_chiron_metodu("_send_realtime")], type_ignores=[])
    ortam = {"asyncio": asyncio, "time": time, "keep_session_alive": canli_kod}
    exec(compile(modul, "main.py", "exec"), ortam)
    return ortam["_send_realtime"]


def test_yamadan_once_dogmus_nesnede_de_sessizlik_baslar():
    """Asıl arıza buydu: canlı nesnede de ilk gönderim hatasız çıkmalı, görev ölmemeli."""

    def _hizli(send, last_sent, blocked):
        return keep_session_alive(send, last_sent, blocked, clock=lambda: 10_000_000.0, tick=0)

    async def _run():
        nesne = _CanliNesne()
        gorev = asyncio.create_task(_gonderim_metodu(_hizli)(nesne))
        await asyncio.sleep(0.01)
        gorev.cancel()
        with pytest.raises(asyncio.CancelledError):
            await gorev
        return nesne

    nesne = asyncio.run(_run())
    assert nesne.sessizlik >= 1
    assert nesne._tool_call_pending is False


def test_baglanti_kapaninca_sessizlik_gorevi_de_biter():
    """Kalırsa eski oturuma göndermeye devam eder, her bağlantıda bir görev birikir."""

    async def _run():
        nesne = _CanliNesne()
        oncesi = asyncio.all_tasks()
        gorev = asyncio.create_task(_gonderim_metodu()(nesne))
        await asyncio.sleep(0)
        gorev.cancel()
        with pytest.raises(asyncio.CancelledError):
            await gorev
        await asyncio.sleep(0)
        return asyncio.all_tasks() - oncesi

    assert asyncio.run(_run()) == set()


def test_sessizlik_canli_yamanin_ulasamadigi_dongude_degil():
    """run() süreç boyunca bitmiyor: oraya eklenen görev yeniden başlatmaya kadar hiç başlamaz."""
    assert "keep_session_alive" not in ast.unparse(_chiron_metodu("run"))
    assert "keep_session_alive" in ast.unparse(_chiron_metodu("_send_realtime"))
    assert "tg.create_task(self._send_realtime())" in MAIN_SOURCE
    assert MAIN_SOURCE.count("is_expected_close(e)") == 2


def test_canli_yama_yeni_govdeyi_eski_metoda_yerinde_uygular():
    """Çalışan süreç bu yolla düzelecek: yerinde yama olmazsa eski bağlı metot eski kodu çalıştırır."""

    async def _eski(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    yeni = _gonderim_metodu()
    assert _patch_function(_eski, yeni) is True
    assert _eski.__code__ is yeni.__code__
