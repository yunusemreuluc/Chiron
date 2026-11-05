"""Çalan medyayı kontrol etme (2026-11-06, kendini geliştirme K-016).

"Müziği durdur", "devam ettir", "sonraki şarkı", "önceki", "ne çalıyor?". `play_media` yalnız yeni bir şey
açabiliyordu, `set_volume` yalnız sesi ayarlıyordu; çalan şeyi durduracak ya da değiştirecek araç PC'deki sesli
Chiron'da hiç yoktu.

Yol: Windows'un genel medya oturumu API'si (`Windows.Media.Control`, Win10 1809+) — görev çubuğundaki medya
kartının kullandığı kaynak. Yeni bağımlılık yok: PowerShell 5.1 WinRT türlerini doğrudan yükleyebiliyor, `await`
yerine `AsTask` köprüsü kullanılıyor. Bir çağrı bu makinede ~0,5 sn.

Neden medya tuşu değil: `keybd_event` (telefon yolu, `backend/core/desktop_control.py`) kör bir aç/kapa — sonucu
okutmaz, "durdur" derken duran şeyi başlatabilir, hangi uygulamaya gideceği belli değildir. Burada önce durum
okunur, komut doğru oturuma gider ve sonuç GERİ OKUNUR; "durdurdum" cümlesi yalnız oturum gerçekten durunca kurulur.

Seçim Python'da (`choose`), PowerShell yalnız okur ve söyleneni uygular — seçim mantığı böylece testle sınanır.
Kaynak: learn.microsoft.com/uwp/api/windows.media.control.globalsystemmediatransportcontrolssession ·
devblogs.microsoft.com/oldnewthing/20231108-00/?p=108980
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Any

from actions.tool_result import fail, ok
from core.tool_registry import register_tool

logger = logging.getLogger("chiron.medya_kontrol")

ACTIONS = ("status", "pause", "play", "next", "previous")
_SYNONYMS = {"stop": "pause", "resume": "play", "skip": "next", "prev": "previous", "get": "status"}
_NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW: pythonw altında konsol yanıp sönmesin
_TIMEOUT = 15
_TITLE_LIMIT = 120

# Chiron'un kendi WebView2 sesi (düşünme sesi) oturum açarsa "müziği durdur" onu hedef almasın.
_OWN_APPS = ("chiron", "python", "msedgewebview")
# "YouTube'u durdur": YouTube bir uygulama değil, oturum tarayıcının adıyla görünür.
_BROWSER_WORDS = ("youtube", "tarayıcı", "tarayici", "browser", "netflix", "twitch")
_BROWSERS = ("chrome", "msedge", "edge", "firefox", "brave", "opera", "vivaldi")

_STATUS_WORDS = {"Playing": "çalıyor", "Paused": "duraklatılmış", "Stopped": "durmuş"}

# Kullanıcıdan/modelden gelen hiçbir değer betiğe gömülmez: hedef ve komut ortam değişkeninden okunur.
_PRELUDE = r"""
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask=[System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
function Await($op,[type]$t){ $task=$asTask.MakeGenericMethod($t).Invoke($null,@($op)); if(-not $task.Wait(4000)){throw 'zaman asimi'}; $task.Result }
$M=[Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager,Windows.Media.Control,ContentType=WindowsRuntime]
$P=[Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties,Windows.Media.Control,ContentType=WindowsRuntime]
$mgr=Await ($M::RequestAsync()) $M
function Snap {
  $cur=$mgr.GetCurrentSession()
  foreach($x in $mgr.GetSessions()){
    $t='';$a=''
    try{$p=Await ($x.TryGetMediaPropertiesAsync()) $P;$t=$p.Title;$a=$p.Artist}catch{}
    [pscustomobject]@{app=$x.SourceAppUserModelId;status=[string]$x.GetPlaybackInfo().PlaybackStatus;title=$t;artist=$a;current=[bool]($cur -and $cur.SourceAppUserModelId -eq $x.SourceAppUserModelId)}
  }
}
"""

_LIST = _PRELUDE + r"""
$o=@(Snap)
ConvertTo-Json -InputObject $o -Compress
"""

_ACT = _PRELUDE + r"""
$targets=@($env:CHIRON_MEDIA_TARGETS | ConvertFrom-Json | ForEach-Object { $_ })
$verb=$env:CHIRON_MEDIA_VERB
$errors=@()
function Sign { $s=@(Snap | Where-Object { $targets -contains $_.app }); ($s | ForEach-Object { if($verb -eq 'next' -or $verb -eq 'previous'){$_.title}else{$_.status} }) -join '|' }
$before=Sign
$accepted=@()
foreach($x in $mgr.GetSessions()){
  if($targets -notcontains $x.SourceAppUserModelId){continue}
  $done=$false
  try{
    $op=switch($verb){ 'pause'{$x.TryPauseAsync()} 'play'{$x.TryPlayAsync()} 'next'{$x.TrySkipNextAsync()} 'previous'{$x.TrySkipPreviousAsync()} }
    $done=Await $op ([bool])
  }catch{$errors+=[string]$_.Exception.Message}
  if($done){$accepted+=$x.SourceAppUserModelId}
}
if($accepted.Count){ for($i=0;$i -lt 14;$i++){ Start-Sleep -Milliseconds 150; if((Sign) -ne $before){break} } }
$o=@(Snap)
ConvertTo-Json -InputObject ([pscustomobject]@{accepted=@($accepted);errors=@($errors);sessions=$o}) -Compress -Depth 4
"""


def _powershell(script: str, env: dict[str, str] | None = None) -> Any:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, encoding="utf-8", errors="replace", timeout=_TIMEOUT, creationflags=_NO_WINDOW,
        env={**os.environ, **(env or {})},
    )
    if result.returncode != 0:
        error = (result.stderr or "").strip()
        raise OSError(error.splitlines()[0] if error else f"powershell çıkış kodu {result.returncode}")
    return json.loads(result.stdout)


def _clean(text: Any) -> str:
    """Başlık dış içerik: tek satıra indir, kısalt (video başlığı sesle okunacak ve modele gidecek)."""
    return " ".join(str(text or "").split())[:_TITLE_LIMIT]


def _usable(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ham oturumlardan kapalıları ve Chiron'un kendisini ayıklar, metinleri temizler."""
    sessions = []
    for item in raw or []:
        app = str(item.get("app") or "")
        if item.get("status") == "Closed" or any(own in app.casefold() for own in _OWN_APPS):
            continue
        sessions.append({**item, "app": app, "title": _clean(item.get("title")), "artist": _clean(item.get("artist"))})
    return sessions


def read_sessions() -> list[dict[str, Any]]:
    return _usable(_powershell(_LIST))


def apply(verb: str, targets: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    """Komutu hedef oturumlara gönderir. (komutu kabul eden uygulamalar, geri okunan oturumlar)."""
    data = _powershell(_ACT, {"CHIRON_MEDIA_VERB": verb, "CHIRON_MEDIA_TARGETS": json.dumps(targets)})
    if data.get("errors"):
        logger.warning("Medya komutu %s hata verdi: %s", verb, data["errors"])
    return [str(app) for app in data.get("accepted") or []], _usable(data.get("sessions") or [])


def friendly(app: str) -> str:
    """Uygulama kimliğini söylenebilir ada çevirir: 'SpotifyAB.SpotifyMusic_x!Spotify' → Spotify, 'msedge.exe' → Edge."""
    name = app.rsplit("!", 1)[-1].replace("\\", "/").rsplit("/", 1)[-1]
    if name.casefold().endswith(".exe"):
        name = name[:-4]
    name = name.split(".", 1)[0] or app  # 'Chrome._crx_abc' (yüklü web uygulaması) → Chrome
    return "Edge" if name.casefold() in ("msedge", "microsoftedge") else (name[:1].upper() + name[1:])


def matches(app_query: str, session: dict[str, Any]) -> bool:
    query = app_query.strip().casefold()
    app = session["app"].casefold()
    if any(word in query for word in _BROWSER_WORDS):
        return any(browser in app for browser in _BROWSERS)
    return query in app or query in friendly(session["app"]).casefold()


def _first(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """Tek hedef gereken komutlarda: çalan > Windows'un güncel saydığı > ilk."""
    playing = [s for s in sessions if s["status"] == "Playing"]
    pool = playing or sessions
    return next((s for s in pool if s.get("current")), pool[0])


def choose(action: str, sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Komutun hedefleri. Boş liste = yapılacak iş yok (ör. zaten duruyor)."""
    if not sessions:
        return []
    playing = [s for s in sessions if s["status"] == "Playing"]
    if action == "pause":
        return playing  # "durdur" = sessizlik: iki kaynak çalıyorsa biri bağırmaya devam etmesin
    if action == "play":
        return [] if playing else [_first(sessions)]
    return [_first(sessions)]


def describe(session: dict[str, Any]) -> str:
    what = f"«{session['title']}»" if session["title"] else "başlık bilgisi yok"
    if session["artist"]:
        what += f", {session['artist']}"
    return what


def _status_line(session: dict[str, Any]) -> str:
    word = _STATUS_WORDS.get(session["status"], "açık")
    return f"{friendly(session['app'])}: {word} — {describe(session)}"


def _names(sessions: list[dict[str, Any]]) -> str:
    return ", ".join(dict.fromkeys(friendly(s["app"]) for s in sessions))


def _report(action: str, targets: list[dict[str, Any]], accepted: list[str], after: list[dict[str, Any]]) -> dict:
    """Geri okunan duruma bakıp cümleyi kurar: kabul edilmeyen ya da gerçekleşmeyen iş 'yaptım' diye söylenmez."""
    names = _names(targets)
    if not accepted:
        hint = " Tek video açıksa sonraki/önceki olmayabilir." if action in ("next", "previous") else ""
        return fail(f"{names} bu komutu kabul etmedi.{hint}")

    now = [s for s in after if s["app"] in accepted]
    if action == "pause":
        still = [s for s in now if s["status"] == "Playing"]
        if still:
            return fail(f"Durdurma isteği gitti ama {_names(still)} hâlâ çalıyor görünüyor.")
        return ok(f"Durduruldu: {names}.", apps=[friendly(s["app"]) for s in targets])
    if action == "play":
        playing = [s for s in now if s["status"] == "Playing"]
        if not playing:
            return fail(f"Devam isteği gitti ama {names} çalmaya başlamadı.")
        return ok(f"Devam ediyor: {describe(playing[0])}.", title=playing[0]["title"], artist=playing[0]["artist"])

    # next / previous: başarı ölçütü başlığın değişmesi
    before = targets[0]
    current = next((s for s in now if s["app"] == before["app"]), None)
    if current is None:
        return fail(f"Geçiş isteği gitti ama {names} oturumu artık görünmüyor.")
    if current["title"] == before["title"]:
        note = " Çoğu uygulama önceki komutunda parçayı başa sarar." if action == "previous" else ""
        return ok(f"Geçiş isteği gitti ama parça adı değişmedi: {describe(current)}.{note}",
                  title=current["title"], changed=False)
    return ok(f"Şimdi: {describe(current)}.", title=current["title"], artist=current["artist"], changed=True)


@register_tool("control_media")
def control_media(action: str = "status", app: str = "") -> dict:
    action = (action or "status").strip().lower()
    action = _SYNONYMS.get(action, action)
    if action not in ACTIONS:
        return fail(f"Bilinmeyen eylem: {action}. Geçerli: {', '.join(ACTIONS)}.")
    app = (app or "").strip()
    try:
        sessions = read_sessions()
        pool = [s for s in sessions if matches(app, s)] if app else sessions
        if app and not pool:
            present = f" Şu an açık olanlar: {_names(sessions)}." if sessions else ""
            return fail(f"{app} için açık bir medya bulamadım.{present}")
        if not pool:
            if action == "status":
                return ok("Şu an çalan ya da duraklatılmış bir medya yok.", sessions=[])
            return fail("Kontrol edebileceğim açık bir medya yok. Ne çalmamı istersin?")
        if action == "status":
            lines = [_status_line(s) for s in sorted(pool, key=lambda s: s["status"] != "Playing")]
            return ok("; ".join(lines) + ".", sessions=[
                {"app": friendly(s["app"]), "status": s["status"], "title": s["title"], "artist": s["artist"]}
                for s in pool
            ])

        targets = choose(action, pool)
        if not targets:
            if action == "pause":
                return ok(f"Zaten çalmıyor: {_names(pool)}.", changed=False)
            return ok(f"Zaten çalıyor: {describe(_first(pool))}.", changed=False)
        accepted, after = apply(action, list(dict.fromkeys(s["app"] for s in targets)))
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:  # json.JSONDecodeError bir ValueError
        logger.warning("Medya kontrolü başarısız: %s", error)
        return fail(f"Medya kontrolü çalışmadı: {error}")
    return _report(action, targets, accepted, after)
