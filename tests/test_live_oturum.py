"""Canlı oturumun sustuyken ayakta kalması ve olağan kapanışın hata sayılmaması."""
import ast
import asyncio
import logging
import time
from pathlib import Path

import pytest
from google.genai import errors, types
from google.genai._live_converters import _LiveConnectConfig_to_mldev

from backend.core.canli_yukleme import _patch_function
from core.live_oturum import (
    KEEPALIVE_SECONDS,
    RESUME_MAX_AGE_SECONDS,
    RESUME_MAX_FAILURES,
    RESUME_PROOF_SECONDS,
    RENEW_AFTER_SECONDS,
    RENEW_QUIET_SECONDS,
    RENEW_QUIET_SECONDS_GOING_AWAY,
    SILENCE_CHUNK,
    PlannedRenewal,
    SessionResume,
    is_expected_close,
    keep_session_alive,
    wait_for_quiet_renewal,
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


class _Saat:
    def __init__(self):
        self.simdi = 1000.0

    def __call__(self):
        return self.simdi


def _guncelleme(handle="anahtar-1", resumable=True):
    return types.LiveServerSessionResumptionUpdate(new_handle=handle, resumable=resumable)


def _anahtarli(saat=None):
    saat = saat or _Saat()
    devam = SessionResume(clock=saat)
    devam.seen(_guncelleme())
    return devam, saat


def test_ilk_baglanti_anahtarsiz_acilir():
    assert SessionResume().next_handle() is None


def test_kopunca_ayni_konusma_surer():
    devam, _ = _anahtarli()
    assert devam.next_handle() == "anahtar-1"


def test_en_yeni_anahtar_kullanilir():
    devam, _ = _anahtarli()
    devam.seen(_guncelleme("anahtar-2"))
    assert devam.next_handle() == "anahtar-2"


@pytest.mark.parametrize("guncelleme", [_guncelleme("", resumable=False), _guncelleme("x", resumable=False), None])
def test_devam_edilemeyen_an_son_iyi_anahtari_silmez(guncelleme):
    """Model konuşurken ya da araç çalışırken sunucu boş anahtar yollar."""
    devam, _ = _anahtarli()
    devam.seen(guncelleme)
    assert devam.next_handle() == "anahtar-1"


def test_sifirlama_eski_konusmaya_dondurmez():
    devam, _ = _anahtarli()
    devam.start_fresh()
    assert devam.next_handle() is None
    assert devam.next_handle() is None


def test_sifirlama_sirasinda_gelen_guncelleme_eski_konusmayi_geri_getirmez():
    """Alım görevi iptal edilirken araya güncelleme girebilir."""
    devam, _ = _anahtarli()
    devam.start_fresh()
    devam.seen(_guncelleme("gec-gelen"))
    assert devam.next_handle() is None


def test_sifirlamadan_sonraki_konusma_yine_surer():
    devam, _ = _anahtarli()
    devam.start_fresh()
    assert devam.next_handle() is None
    devam.seen(_guncelleme("yeni-konusma"))
    assert devam.next_handle() == "yeni-konusma"


def test_cok_eski_konusma_geri_gelmez():
    devam, saat = _anahtarli()
    saat.simdi += RESUME_MAX_AGE_SECONDS + 1
    assert devam.next_handle() is None


def test_gecersiz_anahtar_chironu_acilmaz_birakmaz(caplog):
    """Sunucu anahtarı hep reddederse hata ekranına varmadan yeni oturum açılmalı."""
    devam, saat = _anahtarli()
    with caplog.at_level(logging.WARNING, logger="chiron"):
        for _ in range(RESUME_MAX_FAILURES):
            assert devam.next_handle() == "anahtar-1"
            saat.simdi += 2
        assert devam.next_handle() is None
    assert "yeni oturum" in caplog.text
    assert devam.next_handle() is None


def test_mesaj_alan_baglanti_basarisiz_sayilmaz():
    devam, saat = _anahtarli()
    for _ in range(RESUME_MAX_FAILURES + 2):
        assert devam.next_handle() == "anahtar-1"
        devam.seen(None)
        saat.simdi += 2
    assert devam.next_handle() == "anahtar-1"


def test_uzun_yasayan_sessiz_baglanti_basarisiz_sayilmaz():
    """Sessizlikle saatlerce duran oturumda sunucu hiç mesaj göndermeyebilir."""
    devam, saat = _anahtarli()
    for _ in range(RESUME_MAX_FAILURES + 2):
        assert devam.next_handle() == "anahtar-1"
        saat.simdi += RESUME_PROOF_SECONDS + 1
    assert devam.next_handle() == "anahtar-1"


def test_kisa_ag_kesintisi_konusmayi_silmez():
    devam, saat = _anahtarli()
    for _ in range(RESUME_MAX_FAILURES - 1):
        assert devam.next_handle() == "anahtar-1"
        saat.simdi += 2
    assert devam.next_handle() == "anahtar-1"
    devam.seen(None)
    saat.simdi += 2
    assert devam.next_handle() == "anahtar-1"


def test_anahtarsiz_ve_anahtarli_ayar_sunucuya_gider():
    """Anahtar yokken de alan gitmeli: sunucu devam anahtarını ancak bu alan varsa gönderir."""
    def _kurulum(handle):
        ayar = types.LiveConnectConfig(session_resumption=types.SessionResumptionConfig(handle=handle))
        kurulum: dict = {}
        _LiveConnectConfig_to_mldev(None, ayar, kurulum)
        return kurulum["setup"]["sessionResumption"]

    assert _kurulum(None) == {}
    assert _kurulum("anahtar-1") == {"handle": "anahtar-1"}


class _SifirlanacakNesne:
    def __init__(self):
        self._reset_event = asyncio.Event()
        self.devam, _ = _anahtarli()

    async def _renew_when_quiet(self):
        await asyncio.Event().wait()

    def _session_resume(self):
        return self.devam


def test_sifirla_dugmesi_ve_ses_degisimi_yeni_oturum_ister():
    """Hepsi `_watch_reset`ten geçiyor; metot kaynaktan derlenip gerçekten çalıştırılıyor."""
    class _ConversationReset(Exception):
        pass

    modul = ast.Module(body=[_chiron_metodu("_watch_reset")], type_ignores=[])
    ortam = {"_ConversationReset": _ConversationReset, "asyncio": asyncio}
    exec(compile(modul, "main.py", "exec"), ortam)

    async def _run():
        nesne = _SifirlanacakNesne()
        nesne._reset_event.set()
        with pytest.raises(_ConversationReset):
            await ortam["_watch_reset"](nesne)
        return nesne

    assert asyncio.run(_run()).devam.next_handle() is None


def test_devam_kodu_canli_yamanin_ulasabildigi_yerde():
    """run() süreç boyunca bitmiyor; bağlantı başına çağrılan metotlar yamayla yenilenir."""
    assert "_session_resume" not in ast.unparse(_chiron_metodu("run"))
    assert "self._session_resume().seen(response.session_resumption_update)" in ast.unparse(
        _chiron_metodu("_receive_audio")
    )
    assert "session_resumption=types.SessionResumptionConfig(handle=self._session_resume().next_handle())" in MAIN_SOURCE


# --- 60. dakikadan önce sessiz anda yenileme ---


def _yenileme_ani(monkeypatch, saat, blocked, last_activity, going_away):
    """Beklemeyi gerçek zaman harcamadan sürer: her turda saat bir saniye ilerler."""
    baslangic = saat.simdi

    async def _uyu(_sure):
        saat.simdi += 1.0

    async def _run():
        monkeypatch.setattr("core.live_oturum.asyncio.sleep", _uyu)
        try:
            await wait_for_quiet_renewal(blocked, last_activity, going_away, clock=saat)
        finally:
            monkeypatch.undo()

    asyncio.run(_run())
    return saat.simdi - baslangic


def test_yenileme_sure_dolmadan_baslamaz(monkeypatch):
    saat = _Saat()
    ani = _yenileme_ani(monkeypatch, saat, lambda: False, lambda: 0.0, lambda: False)
    assert ani == RENEW_AFTER_SECONDS


def test_yenileme_konusma_bitip_sessizlik_olana_kadar_bekler(monkeypatch):
    saat = _Saat()
    son_ses = saat.simdi + RENEW_AFTER_SECONDS + 100
    ani = _yenileme_ani(monkeypatch, saat, lambda: False, lambda: son_ses, lambda: False)
    assert ani == RENEW_AFTER_SECONDS + 100 + RENEW_QUIET_SECONDS


def test_yenileme_chiron_mesgulken_baslamaz(monkeypatch):
    saat = _Saat()
    serbest = saat.simdi + RENEW_AFTER_SECONDS + 50
    ani = _yenileme_ani(monkeypatch, saat, lambda: saat.simdi < serbest, lambda: 0.0, lambda: False)
    assert ani == RENEW_AFTER_SECONDS + 50


def test_sunucu_kapanacagini_soylerse_kisa_sessizlik_yeter(monkeypatch):
    saat = _Saat()
    son_ses = saat.simdi + 10
    ani = _yenileme_ani(monkeypatch, saat, lambda: False, lambda: son_ses, lambda: True)
    assert ani == 10 + RENEW_QUIET_SECONDS_GOING_AWAY


def test_planli_yenileme_olagan_kapanis_sayilir():
    """Çalışan run() yamayla değişmiyor: sessiz yeniden bağlanma ancak bu dalla mümkün."""
    assert is_expected_close(PlannedRenewal())
    assert is_expected_close(ExceptionGroup("g", [PlannedRenewal()]))
    assert not is_expected_close(ExceptionGroup("g", [PlannedRenewal(), RuntimeError("mikrofon")]))


def _izleme_ortami():
    """`_watch_reset` ve `_renew_when_quiet` kaynaktan derlenip gerçekten çalıştırılıyor."""

    class _ConversationReset(Exception):
        pass

    govde = [_chiron_metodu("_watch_reset"), _chiron_metodu("_renew_when_quiet")]
    ortam = {
        "_ConversationReset": _ConversationReset,
        "asyncio": asyncio,
        "logger": logging.getLogger("test"),
        "time": time,
    }
    exec(compile(ast.Module(body=govde, type_ignores=[]), "main.py", "exec"), ortam)
    return ortam


class _AnindaYenilenen(_SifirlanacakNesne):
    """Bekleme bitmiş: asıl `_renew_when_quiet` çalışır, hemen döner."""

    def _renewal_blocked(self):
        return False


def _beklemesiz(monkeypatch):
    async def _hemen(*_a, **_k):
        return None

    monkeypatch.setattr("core.live_oturum.wait_for_quiet_renewal", _hemen)


def test_planli_yenileme_konusmayi_silmez(monkeypatch):
    """Asıl fark: aynı olaydan geçen sıfırlama anahtarı siler, yenileme silmez."""
    _beklemesiz(monkeypatch)
    ortam = _izleme_ortami()

    class _Nesne(_AnindaYenilenen):
        def _renew_when_quiet(self):
            return ortam["_renew_when_quiet"](self)

    async def _run():
        nesne = _Nesne()
        nesne.devam.seen(types.LiveServerSessionResumptionUpdate(new_handle="anahtar", resumable=True))
        with pytest.raises(PlannedRenewal):
            await ortam["_watch_reset"](nesne)
        return nesne

    nesne = asyncio.run(_run())
    assert nesne.devam.next_handle() == "anahtar"
    assert not nesne._reset_event.is_set()


def test_ayni_anda_gelen_sifirlama_yenilemenin_onune_gecer(monkeypatch):
    """Sıfırlama sinyali varken bayrak kalkmaz: eski konuşma geri gelmesin."""
    _beklemesiz(monkeypatch)
    ortam = _izleme_ortami()

    async def _run():
        nesne = _AnindaYenilenen()
        nesne._renew_due = False
        nesne._reset_event.set()
        await ortam["_renew_when_quiet"](nesne)
        return nesne

    assert asyncio.run(_run())._renew_due is False


def test_yenileme_gorevi_baglanti_kapaninca_biter():
    """Kalırsa her bağlantıda bir görev birikir ve yeni oturumu vaktinden önce keser."""
    ortam = _izleme_ortami()

    async def _run():
        nesne = _SifirlanacakNesne()
        oncesi = asyncio.all_tasks()
        gorev = asyncio.create_task(ortam["_watch_reset"](nesne))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        gorev.cancel()
        with pytest.raises(asyncio.CancelledError):
            await gorev
        await asyncio.sleep(0)
        return asyncio.all_tasks() - oncesi

    assert asyncio.run(_run()) == set()


def test_yenileme_kodu_canli_yamanin_ulasabildigi_yerde():
    assert "_renew_when_quiet" not in ast.unparse(_chiron_metodu("run"))
    assert "self._renew_when_quiet()" in ast.unparse(_chiron_metodu("_watch_reset"))
    assert "tg.create_task(self._watch_reset())" in MAIN_SOURCE
