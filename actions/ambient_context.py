"""Ambient bağlam — Chiron'un "kullanıcı şu an ne yapıyor" farkındalığı.

Chiron'un en büyük boşluğu şuydu: "bunu kaydet", "şurayı kapat", "burada ne
yazıyor" dendiğinde neyden bahsedildiğini bilmiyordu. Tek çare `analyze_screen`
çağırmaktı — o da Gemini kotası harcıyor ([[Bilinen-Tuzaklar]] § Gemini yerine
yerel modeli tercih et). Bu modül aynı sorunun **kotasız** cevabı: aktif
pencere, onu çalıştıran program ve kullanıcının klavye/fareye en son ne zaman
dokunduğu — hepsi Win32'den, saniyenin binde biri sürede.

## Neden ÇEKME (araç), sürekli enjeksiyon değil

İlk tasarım bağlamı oturuma sürekli beslemekti: pencere değişince
`send_client_content(turn_complete=False)` ile sessizce bildir. google-genai
SDK'sı (2.12.1) `send_client_content` docstring'inde bunu açıkça uyarıyor:

    Caution: Interleaving `send_client_content` and `send_realtime_input`
      in the same conversation is not recommended and can lead to
      unexpected results.

Chiron'un TÜM ses döngüsü `send_realtime_input` üzerinde. `turn_complete=False`
ayrıca turu AÇIK bırakıyor ("will not return until you send
turn_complete=True") — en kötü senaryoda model sese cevap veremez, yani Chiron
susar. Bu, bir bağlam özelliği için alınacak risk değil:
[[Bilinen-Tuzaklar]] § Live oturum yapılandırmasına yeni alan eklemek riskli
maddesindeki kural aynen geçerli — *bir arayüz özelliği, sesli asistanın
çalışmasından önce gelmez.*

Bu yüzden bağlam **itilmiyor, çekiliyor**: model ihtiyaç duyduğunda
`get_context` aracını çağırıyor (bkz. core/prompt.txt). Oturuma hiç dokunmuyor,
kullanılmadığında sıfır token, ve araç Gemini'ye HİÇ istek atmıyor — tamamen
yerel. Karşılığında bir tur gidiş-dönüş gecikmesi var; makul takas.
"""

from __future__ import annotations

import ctypes
import datetime
from ctypes import wintypes

from actions.tool_result import fail, ok
from core.tool_registry import register_tool

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:  # pragma: no cover — requirements.txt'te var
    HAS_PSUTIL = False


# Bu eşiğin üstünde kullanıcı "masasında değil" sayılıyor. 90 sn: bir kahve
# molası değil ama düşünme duraklamasından da uzun.
AWAY_AFTER_S = 90.0

# Pencere başlıkları çok uzun olabiliyor (tarayıcı sekmeleri, dosya yolları).
MAX_TITLE_CHARS = 120


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def _idle_seconds() -> float:
    """Klavye/fareye en son dokunulalı kaç saniye geçti.

    `GetLastInputInfo` SİSTEM GENELİ çalışıyor — Chiron'un kendi penceresi
    odakta olmasa da doğru cevap veriyor. Bu önemli: kullanıcı başka bir
    uygulamadayken de "orada mı" bilgisini istiyoruz.
    """
    try:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        # GetTickCount 49.7 günde bir sarıyor; fark negatif çıkarsa 0'a çek.
        delta_ms = ctypes.windll.kernel32.GetTickCount() - info.dwTime
        return max(0.0, delta_ms / 1000.0)
    except Exception:
        return 0.0


def _active_window() -> tuple[str, str]:
    """(pencere başlığı, programın adı). Okunamayan alan boş dize döner."""
    baslik, program = "", ""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return "", ""

        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            baslik = buf.value.strip()[:MAX_TITLE_CHARS]

        # Program adı başlıktan DAHA güvenilir: başlık uygulamaya göre değişiyor
        # ("main.py - Chiron - Visual Studio Code" / "Chiron" / bazen boş), süreç
        # adı ise sabit. Model "hangi uygulamadasın" sorusuna buradan cevap veriyor.
        if HAS_PSUTIL:
            pid = wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value:
                program = psutil.Process(pid.value).name()
    except Exception:
        pass
    return baslik, program


# Süreç adı → insanın kullandığı ad. Yalnızca sık karşılaşılanlar; listede
# olmayan için ".exe" atılıp ham ad gösteriliyor (uydurma yapılmıyor).
_PROGRAM_ADLARI = {
    "code.exe": "Visual Studio Code",
    "chrome.exe": "Google Chrome",
    "msedge.exe": "Microsoft Edge",
    "firefox.exe": "Firefox",
    "explorer.exe": "Dosya Gezgini",
    "windowsterminal.exe": "Windows Terminal",
    "powershell.exe": "PowerShell",
    "cmd.exe": "Komut İstemi",
    "notepad.exe": "Not Defteri",
    "winword.exe": "Word",
    "excel.exe": "Excel",
    "powerpnt.exe": "PowerPoint",
    "spotify.exe": "Spotify",
    "discord.exe": "Discord",
    "obsidian.exe": "Obsidian",
    "python.exe": "Python",
    "pythonw.exe": "Chiron",
}


def _program_adi(surec: str) -> str:
    if not surec:
        return ""
    return _PROGRAM_ADLARI.get(surec.lower(), surec.rsplit(".exe", 1)[0])


# `strftime("%A")` C yerelini kullanıyor ve "Saturday" döndürüyor — Chiron
# Türkçe konuşuyor. Sistem yereline (`locale.setlocale`) dokunulmadı: o
# süreç geneli bir yan etki ve başka modülleri (sayı/tarih ayrıştırma)
# sessizce etkileyebilir.
_GUNLER = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")


def _baslik_sadelestir(baslik: str, uygulama: str) -> str:
    """Pencere başlığının sonundaki program adını atar.

    Windows uygulamalarının çoğu başlığa kendi adını ekliyor
    ("... - Google Chrome"). Program adı zaten ayrı gösterildiği için bu
    tekrar oluyordu: `Google Chrome ("... - Google Chrome")`.
    """
    if not baslik or not uygulama:
        return baslik
    for ek in (f" - {uygulama}", f" — {uygulama}", f" | {uygulama}"):
        if baslik.endswith(ek):
            return baslik[: -len(ek)].strip()
    return baslik


def read_context() -> dict:
    """Ham bağlam sözlüğü — hem `get_context` aracı hem arayüz bunu kullanıyor."""
    baslik, surec = _active_window()
    uygulama = _program_adi(surec)
    bosta = _idle_seconds()
    simdi = datetime.datetime.now()
    return {
        "window_title": _baslik_sadelestir(baslik, uygulama),
        "process": surec,
        "app": uygulama,
        "idle_seconds": round(bosta, 1),
        "away": bosta >= AWAY_AFTER_S,
        "time": simdi.strftime("%H:%M"),
        "date": f"{simdi.strftime('%d.%m.%Y')} {_GUNLER[simdi.weekday()]}",
    }


def describe_context(ctx: dict | None = None) -> str:
    """Bağlamın tek satırlık, modele/kullanıcıya okunacak hâli."""
    c = ctx if ctx is not None else read_context()
    parcalar = []

    if c["app"] and c["window_title"]:
        parcalar.append(f'{c["app"]} ("{c["window_title"]}")')
    elif c["app"]:
        parcalar.append(c["app"])
    elif c["window_title"]:
        parcalar.append(f'"{c["window_title"]}"')
    else:
        # Uydurma yok: okunamadıysa okunamadığını söyle.
        parcalar.append("aktif pencere okunamadı")

    if c["away"]:
        dakika = int(c["idle_seconds"] // 60)
        parcalar.append(f"kullanıcı {dakika} dakikadır klavyeye dokunmadı")
    else:
        parcalar.append("kullanıcı aktif")

    return f'{c["time"]} · ' + " · ".join(parcalar)


@register_tool("get_context")
def get_context() -> dict:
    """Kullanıcının şu an ne yaptığı — hangi program, hangi pencere, orada mı."""
    try:
        ctx = read_context()
    except Exception as e:
        return fail(f"Bağlam okunamadı: {e}")
    # `ok` **kwargs alıyor (data= değil) — sözlük olduğu gibi açılıyor.
    return ok(describe_context(ctx), **ctx)
