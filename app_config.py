# Alp Ünlü tarafından yapılmıştır — @alppunlu
from __future__ import annotations

import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
CONFIG_PATH = CONFIG_DIR / "api_keys.json"


DEFAULT_CONFIG = {
    "gemini_api_key": "",
    "voice": "Algieba",
    "youtube_api_key": "",
    "youtube_channel_handle": "",
    # Ses cihazı tercihleri — cihaz ADININ bir parçası (ör. "Microphone Array").
    # Boş bırakılırsa Windows'un varsayılan cihazı kullanılır. İndeks yerine isim
    # tutuluyor: PortAudio indeksleri yeniden başlatmada/cihaz takılınca kayar.
    # Bkz. core/audio_devices.py ve ses_testi.py.
    "mic_device": "",
    "speaker_device": "",
    # Ses efektleri (SFX/*.mp3). Tkinter sürümü bunları yalnızca bellekte
    # tutuyordu — 3D arayüzde diske yazılıyor ki uygulama kapanınca kaybolmasın.
    "sfx_enabled": True,
    "sfx_volume": 0.2,
}


def load_app_config() -> dict:
    config = dict(DEFAULT_CONFIG)
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            config.update(raw)
    except Exception:
        pass
    return config


def save_app_config(updates: dict) -> dict:
    config = load_app_config()
    for key, value in (updates or {}).items():
        if value is None:
            continue
        config[key] = value
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(config, indent=4, ensure_ascii=False),
        encoding="utf-8",
    )
    return config


def get_app_config_value(key: str, default=None):
    return load_app_config().get(key, default)


# Asistanın adı seçili sese göre (kullanıcı kararı, 2026-10-28): erkek sesler
# Chiron, kadın sesler Daphne. Uygulamanın adı her durumda Chiron; değişen yalnız
# asistanın kendini tanıttığı ad, sohbet satırının öneki ve uyandırma sözü.
# Sesler (2026-10-30, dinleyerek seçildi): Chiron = Algieba, Daphne = Achernar;
# Iapetus ve Despina yedek. Gemini Live yalnız hazır sesleri kabul ediyor.
VOICES = ["Algieba", "Achernar", "Iapetus", "Despina"]
DEFAULT_VOICE = "Algieba"
FEMALE_VOICES = {"Achernar", "Despina"}


# Hazır sesin tınısını değiştirmiyor, konuşma tarzını belirliyor (Live modeli
# sistem komutunda tarif edilen tona uyuyor).
SPEAKING_STYLE = {
    "Chiron": "Sakin, ağırbaşlı ve kendinden emin konuş; kibar ama yaltaklanmadan, yerinde kuru bir espriyle. Acele etme, cümleleri net bitir.",
    "Daphne": "Yumuşak, sıcak ve yavaş konuş; samimi, hafif oyuncu ve içten bir tonla. Cümleleri acele etmeden, yumuşak bitir.",
}


def current_voice() -> str:
    """Kayıtlı ses; listeden çıkarılmış eski bir ses (ör. Charon) varsayılana düşer."""
    voice = str(get_app_config_value("voice", DEFAULT_VOICE) or DEFAULT_VOICE)
    return voice if voice in VOICES else DEFAULT_VOICE


def assistant_name(voice: str | None = None) -> str:
    """Seçili sesin (ya da verilen sesin) asistan adı: "Chiron" veya "Daphne"."""
    if voice is None:
        voice = current_voice()
    return "Daphne" if voice in FEMALE_VOICES else "Chiron"
