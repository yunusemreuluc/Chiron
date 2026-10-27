"""
Ses cihazı seçimi ve mikrofon sağlık kontrolü.

NEDEN VAR (2026-07-29): Chiron sessiz kalıyordu ve hiçbir yerde nedeni
görünmüyordu. Teşhis: mikrofon uç noktası Windows'ta AKTİF ve sesi açık (%97)
görünmesine rağmen hiçbir host API'de gerçek ses üretmiyordu. PyAudio bu durumda
hata vermez — akışı açar ve içi boş tamponlar döndürür. Gemini Live hiç konuşma
duymadığı için hiç yanıt vermez; kullanıcıya bu "Chiron'un sesi gelmiyor" olarak
görünür. Sessiz arıza, en pahalı arıza türüdür — bu modül onu sesli hale getiriyor.

İKİ TÜR ARIZA VAR ve ikisi de "sıfır ses" gibi görünmez:

  1. SESSİZ  — tamponlar sıfır dolu (ölü mikrofon / susturulmuş donanım).
  2. DONMUŞ  — tamponlar sıfır DEĞİL ama her tamponda birebir aynı değer.
     Bu makinede DirectSound yolu tam olarak bunu yapıyordu: her okumada aynı
     sabit çöp tamponu döndürüyor. Sadece "seviye > 0" bakan naif bir kontrol
     bunu "çalışan mikrofon" sanır. Gerçek ses her zaman DEĞİŞİR — bu yüzden
     canlılık kararı seviyeye değil, seviyenin DEĞİŞİMİNE bakar.
"""

from __future__ import annotations

import logging
import math
import statistics
import struct
from dataclasses import dataclass

logger = logging.getLogger("chiron")

# ── SESSİZLİK ARIZA DEĞİLDİR ────────────────────────────────────────────────
#
# Bu modülün kurucu varsayımı 2026-08-06'da ölçümle ÇÜRÜDÜ. Eskiden şöyle
# yazıyordu: "Çalışan bir mikrofon sessiz odada bile gürültü tabanı üretir;
# gerçekten ölü bir akış tam sıfır döndürür" — ve medyan RMS 3.0'ın altındaysa
# kullanıcıya "mikrofonun BOZUK" deniyordu.
#
# Realtek kulaklık, WASAPI, aynı gün, aynı cihaz:
#   sessizken   → medyan 0.00, tepe 5.6, yayılım 1.13
#   sessizken   → medyan 0.00, tepe 0.0, yayılım 0.00   (ikinci ölçüm!)
#   konuşurken  → tepe 19771
# Yani ÇALIŞAN bir mikrofon, sessiz odada tam dijital sıfır döndürebiliyor.
# WASAPI, MME'nin aksine sahte bir gürültü tabanı uydurmuyor.
#
# İlk düzeltme denemesi "seviye değil DEĞİŞİM'e bak" idi (yayılım 1.13 vs 0.01).
# İkinci ölçüm onu da çürüttü: yayılım da 0.00 çıkabiliyor.
#
# **Kalıcı sonuç: ses olmadan, çalışan mikrofonla ölü mikrofon AYIRT EDİLEMEZ.**
# Bu bir eşik ayarı sorunu değil, bilgi eksikliği. Bu yüzden sonda artık
# sessizliğe "arıza" DEMİYOR — yalnızca "bu ölçümde sinyal yoktu" diyor ve
# kullanıcıya hangi durumda endişelenmesi gerektiğini söylüyor.
#
# Gerçekten teşhis edilebilen iki şey kaldı ve ikisi de korunuyor:
# akışın hiç AÇILAMAMASI ve fiziksel olarak inandırıcı OLMAYAN bir seviye.

# Tepe bunun altında kaldıysa ölçüm boyunca hiç ses gelmemiş demektir. Ölü bir
# mikrofonu değil, SESSİZLİĞİ işaretliyor — ikisi ayırt edilemiyor.
SIGNAL_PEAK_THRESHOLD = 50.0

# Medyan bunun üstündeyse akış fiziksel olarak inandırıcı değil: tam ölçeğin
# (32767) dörtte biri, SÜREKLİ. Gerçek bir oda böyle okumaz.
#
# Bu kapı DirectSound çöpü için var ama GARANTİ DEĞİL, itiraf edilmesi gereken
# bir sınırı var: aynı DirectSound cihazı ardışık iki ölçümde medyan 12612 ve
# 838 döndürdü (ikincisinde tepe 27070 — sivri, düzensiz çöp). Yani eşik bazen
# yakalıyor bazen kaçırıyor.
#
# Asıl koruma bu eşik değil, CİHAZ SEÇİMİ: `resolve_input_device` WASAPI'yi
# tercih ettiği için DirectSound normalde hiç seçilmiyor. Bu kapı yalnızca
# kullanıcı config'te açıkça bir DirectSound cihazı seçerse devreye giren
# ikinci savunma hattı.
GARBAGE_LEVEL_THRESHOLD = 8000.0

# Sürücüler akış açılışında geçici çöp/klik üretebiliyor — ilk bu kadar saniye atılır.
WARMUP_SECONDS = 0.75

# Windows'ta giriş için tercih edilen host API. MME ve DirectSound birer taklit
# katmanı; WASAPI Vista'dan beri gerçek yol. Bu makinede fark hayat memat:
# MME hiçbir cihazdan ses vermiyor, DirectSound çöp veriyor, WASAPI çalışıyor.
PREFERRED_INPUT_HOST_APIS = ("Windows WASAPI",)


@dataclass
class InputProbe:
    """Bir mikrofon akışının kısa süreli ölçümü."""

    verdict: str  # "live" | "silent" | "garbage" | "unopenable"
    peak: float = 0.0
    median: float = 0.0
    spread: float = 0.0
    rate: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        """Yalnızca KANITLANMIŞ arızalar başarısızlık sayılıyor.

        `silent` başarısızlık DEĞİL: sessiz odada çalışan bir mikrofon da tam
        sıfır okuyor (bkz. yukarıdaki eşik notu). Onu arıza saymak, ölçülmemiş
        bir şeyi iddia etmek olurdu.
        """
        return self.verdict in ("live", "silent")


def rms_int16(data: bytes) -> float:
    """16-bit mono PCM tamponunun RMS'i. (audioop Python 3.13'te kaldırıldığı için
    standart kütüphaneye bağlı kalmadan hesaplanıyor.)"""
    count = len(data) // 2
    if count == 0:
        return 0.0
    samples = struct.unpack(f"<{count}h", data[: count * 2])
    return math.sqrt(sum(s * s for s in samples) / count)


def downsample_int16(data: bytes, src_rate: int, dst_rate: int) -> bytes:
    """16-bit mono PCM'i `src_rate`'ten `dst_rate`'e indirir.

    NEDEN GEREKLİ: Gemini Live girişi 16 kHz istiyor ama WASAPI paylaşımlı modda
    16 kHz'i REDDEDİYOR (`Invalid sample rate`) — cihazın kendi hızını dayatıyor
    (genellikle 48 kHz). Bu makinede çalışan tek yol WASAPI olduğu için dönüşüm
    olmadan Chiron hiç duyamıyor.

    Tam sayı oranda (48000→16000 = 3) blok ORTALAMASI alınıyor, örnek atlama
    değil: atlamak takma ada (aliasing) yol açar, ortalama kaba ama bedava bir
    alçak geçiren filtre görevi görür. Tam sayı değilse doğrusal aradeğerleme.
    """
    if src_rate == dst_rate or not data:
        return data

    count = len(data) // 2
    if count == 0:
        return b""
    samples = struct.unpack(f"<{count}h", data[: count * 2])

    if src_rate % dst_rate == 0:
        factor = src_rate // dst_rate
        out_count = count // factor
        out = [
            int(sum(samples[i * factor : (i + 1) * factor]) / factor) for i in range(out_count)
        ]
    else:
        out_count = int(count * dst_rate / src_rate)
        step = count / out_count if out_count else 1
        out = []
        for i in range(out_count):
            pos = i * step
            left = int(pos)
            right = min(left + 1, count - 1)
            frac = pos - left
            out.append(int(samples[left] * (1 - frac) + samples[right] * frac))

    if not out:
        return b""
    return struct.pack(f"<{len(out)}h", *out)


def open_input_stream(pya, device_index: int | None, target_rate: int, chunk: int):
    """Giriş akışını açar ve GERÇEK örnekleme hızını da döndürür: `(stream, rate)`.

    Önce istenen hız denenir (çoğu cihazda çalışır ve dönüşüm gerekmez), olmazsa
    cihazın kendi varsayılan hızı, o da olmazsa yaygın hızlar. Çağıran taraf
    dönen hız `target_rate`ten farklıysa `downsample_int16` uygulamak zorunda.
    """
    import pyaudio  # type: ignore[reportMissingModuleSource]

    candidates = [target_rate]
    if device_index is not None:
        try:
            native = int(pya.get_device_info_by_index(device_index).get("defaultSampleRate", 0))
            if native:
                candidates.append(native)
        except Exception:
            pass
    candidates += [48000, 44100]

    kwargs = {"input_device_index": device_index} if device_index is not None else {}
    last_error: Exception | None = None
    for rate in dict.fromkeys(candidates):
        try:
            stream = pya.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=rate,
                input=True,
                frames_per_buffer=chunk,
                **kwargs,
            )
        except Exception as exc:
            last_error = exc
            continue
        if rate != target_rate:
            logger.info(
                "[CHIRON] 🎚 Mikrofon %d Hz'i kabul etmedi, %d Hz'de açıldı (aşağı örnekleniyor).",
                target_rate,
                rate,
            )
        return stream, rate

    raise last_error or RuntimeError("giriş akışı açılamadı")


def _iter_devices(pya, kind: str):
    channel_key = "maxInputChannels" if kind == "input" else "maxOutputChannels"
    for index in range(pya.get_device_count()):
        try:
            info = pya.get_device_info_by_index(index)
        except Exception:
            continue
        if int(info.get(channel_key, 0)) < 1:
            continue
        yield index, info


def resolve_device_index(pya, kind: str, name_hint: str) -> int | None:
    """Config'teki isim ipucuna uyan cihazın indeksini döndürür.

    None dönerse çağıran taraf parametreyi hiç geçmemeli — PortAudio kendi
    varsayılanını kullanır. (İpucu boşsa veya eşleşme yoksa istenen davranış budur:
    yapılandırma hatası uygulamayı sessize almamalı.)
    """
    hint = (name_hint or "").strip().lower()
    if not hint:
        return None

    for index, info in _iter_devices(pya, kind):
        if hint in str(info.get("name", "")).lower():
            logger.info("[CHIRON] 🎚 %s cihazı seçildi: [%s] %s", kind, index, info.get("name"))
            return index

    logger.warning(
        "[CHIRON] ⚠ config'teki %s cihazı bulunamadı (%r) — varsayılan cihaz kullanılıyor.",
        kind,
        name_hint,
    )
    return None


def probe_input(pya, device_index: int | None, rate: int, seconds: float = 2.5) -> InputProbe:
    """Mikrofonu kısa süre dinler ve akışın CANLI olup olmadığına karar verir.

    "Ses duydu mu" değil "akış yaşıyor mu" sorusunu cevaplıyor — ikisi aynı şey
    değil ve bu ayrım 2026-08-06'da ölçümle öğrenildi (bkz. modül başındaki
    eşik notu). Kullanıcı sessizse çalışan bir mikrofon da sıfıra yakın okur.
    """
    chunk = 1024
    try:
        stream, actual_rate = open_input_stream(pya, device_index, rate, chunk)
    except Exception as exc:
        return InputProbe(verdict="unopenable", error=str(exc))

    warmup_buffers = int(actual_rate / chunk * WARMUP_SECONDS)
    levels: list[float] = []
    try:
        for i in range(int(actual_rate / chunk * seconds)):
            data = stream.read(chunk, exception_on_overflow=False)
            if i >= warmup_buffers:
                levels.append(rms_int16(data))
    except Exception as exc:
        return InputProbe(verdict="unopenable", error=str(exc), rate=actual_rate)
    finally:
        try:
            stream.close()
        except Exception:
            pass

    if len(levels) < 3:
        return InputProbe(verdict="unopenable", error="yeterli örnek alınamadı", rate=actual_rate)

    median = statistics.median(levels)
    spread = statistics.pstdev(levels)
    peak = max(levels)

    if median > GARBAGE_LEVEL_THRESHOLD:
        verdict = "garbage"
    elif peak <= SIGNAL_PEAK_THRESHOLD:
        # Ölçüm boyunca hiç ses gelmedi. Bu "mikrofon bozuk" DEMEK DEĞİL —
        # kullanıcı susuyor olabilir ve ikisi ayırt edilemiyor.
        verdict = "silent"
    else:
        verdict = "live"

    return InputProbe(
        verdict=verdict, peak=peak, median=median, spread=spread, rate=actual_rate
    )


def resolve_input_device(pya, name_hint: str) -> int | None:
    """Giriş cihazını host API'ye DUYARLI şekilde seçer.

    `resolve_device_index` isim ipucuna uyan ilk indeksi alıyordu ve bu Windows'ta
    sessiz bir tuzak: aynı mikrofon MME, DirectSound ve WASAPI altında ayrı ayrı
    listeleniyor, indeks sırası da MME'yi öne koyuyor. Bu makinede
    `"Microphone Array"` yazmak ÖLÜ olan MME kopyasını seçiyordu — kullanıcı
    config'i doğru yazsa bile sonuç değişmiyordu.

    Sıra:
      1. İpucu varsa: önce tercih edilen host API içinde ara, sonra her yerde.
      2. İpucu yoksa: Windows'un VARSAYILAN giriş cihazının adını al ve aynı
         adı tercih edilen host API altında bul. Kullanıcının işletim sisteminde
         yaptığı seçime saygı gösterir, yalnızca yolu değiştirir.
      3. O da yoksa: tercih edilen host API'deki ilk giriş cihazı.
      4. Hiçbiri yoksa None — PortAudio kendi varsayılanını kullanır.
    """
    devices = []
    for index, info in _iter_devices(pya, "input"):
        try:
            api = str(pya.get_host_api_info_by_index(int(info["hostApi"])).get("name", ""))
        except Exception:
            api = ""
        devices.append((index, str(info.get("name", "")), api))

    preferred = [d for d in devices if d[2] in PREFERRED_INPUT_HOST_APIS]

    def _log(choice, why: str) -> int:
        logger.info("[CHIRON] 🎚 Mikrofon seçildi (%s): [%s] %s — %s", why, choice[0], choice[1], choice[2])
        return choice[0]

    hint = (name_hint or "").strip().lower()
    if hint:
        for pool, why in ((preferred, "config + tercihli API"), (devices, "config")):
            for device in pool:
                if hint in device[1].lower():
                    return _log(device, why)
        logger.warning(
            "[CHIRON] ⚠ config'teki mikrofon bulunamadı (%r) — otomatik seçime düşülüyor.",
            name_hint,
        )

    default_name = ""
    try:
        default_name = str(pya.get_default_input_device_info().get("name", "")).lower()
    except Exception:
        pass
    if default_name:
        for device in preferred:
            if device[1].lower() == default_name or default_name in device[1].lower():
                return _log(device, "sistem varsayılanı, tercihli API")

    if preferred:
        return _log(preferred[0], "tercihli API'deki ilk cihaz")
    return None


def describe_input_problem(probe: InputProbe) -> str:
    """Ölçümü kullanıcının uygulayabileceği bir mesaja çevirir. Sorun yoksa boş string."""
    if probe.ok:
        return ""

    if probe.verdict == "unopenable":
        return (
            f"Mikrofon akışı açılamadı ({probe.error[:120]}). Başka bir uygulama cihazı "
            "özel (exclusive) modda tutuyor olabilir."
        )

    # garbage
    return (
        f"Mikrofon akışı inandırıcı değil (sürekli medyan {probe.median:.0f}/32767) — "
        "sürücü ses yerine çöp üretiyor. Bu genellikle DirectSound yolunda olur; "
        'config/api_keys.json içine "mic_device" ile WASAPI altındaki cihazı seç.'
    )


def describe_input_observation(probe: InputProbe) -> str:
    """Sessizlik için GÖZLEM metni — arıza iddiası değil.

    `describe_input_problem`ten ayrı durması bilinçli: o fonksiyon "şu bozuk"
    diyor, bu fonksiyon "şunu gördüm, şu durumda endişelen" diyor. İkisini tek
    metne karıştırmak, ölçülmemiş bir arızayı ölçülmüş gibi göstermek olurdu.
    """
    if probe.verdict != "silent":
        return ""
    return (
        "Mikrofon açılışta hiç sinyal üretmedi. O sırada sessizdiysen bu NORMAL — "
        "sessiz odada çalışan bir mikrofon da sıfır okur. Ama konuştuğun hâlde Chiron "
        "yanıt vermiyorsa sırayla kontrol et: kulaklığın üzerindeki fiziksel susturma "
        "düğmesi, Windows > Ayarlar > Ses > Giriş'te doğru cihaz ve seviyesi. Farklı "
        'bir mikrofon için config/api_keys.json içine "mic_device": "<cihaz adının bir '
        'parçası>" ekle. Her hâlükârda yazı kutusuna yazarsan Chiron sana SESLİ cevap verir.'
    )
