"""Otonom düzeltme — Chiron gördüğü hatayı kendisi çözer.

`screen_monitor.check_for_issue` bir sorun bulduğunda burası devreye giriyor:
ekranı yeniden yakalayıp "bu tam olarak ne ve ekranda hangi adımlarla
düzeltilir" diye soruyor, sonra planı POLİTİKAYA GÖRE uyguluyor.

Kullanıcı isteği (2026-08-01): "hata buluyorsa çözümü de bulsun ve kendi
yapsın." Çözüm ÖNERME zaten vardı ([[Izleme-ve-Brifing]]); eksik olan son
adımdı — proaktif mesaj açıkça "kendiliğinden tıklama/yazma yapma" diyordu.

## Neden üç bağımsız kapı var

Bir vision modelinin kendi tahminiyle kullanıcının makinesinde tıklaması
gerçek bir risk: "Yeniden Dene" ile "Sil" aynı diyalogda yan yana durabilir ve
model hedefi yanlış eşleştirebilir. Bu yüzden otomatik uygulama üç ayrı
kapıdan geçiyor ve ÜÇÜ DE geçilmeden hiçbir şey tıklanmıyor:

1. **Eylem türü** — `safe` modda yalnızca `click`. `type`/`type_enter` asla
   otomatik değil: bir terminale yazılan metin Enter'la birlikte keyfi komut
   çalıştırmak demek.
2. **Yerel yasak listesi** — hedef metninde yıkıcı bir sözcük geçiyorsa
   (sil, biçimlendir, kaldır, satın al, devre dışı bırak...) reddediliyor.
   Bu kapı MODELDEN BAĞIMSIZ ve Python'da: modelin "risk: low" demesi burayı
   açmıyor. Tek güvenlik ağının, hakkında karar verdiğimiz şeyin kendisi
   olması kabul edilemezdi.
3. **Modelin kendi risk puanı** — yalnızca `low` otomatik geçiyor.

`all` modunda 1 ve 3 gevşiyor ama **2 gevşemiyor**: "sormadan yap" demek
"verimi yok et" demek değil.
"""

from __future__ import annotations

import logging

from google import genai
from google.genai import types

from actions.screen_monitor import _capture_active_window, _extract_json
from actions.tool_result import fail, ok
from app_config import get_app_config_value, save_app_config
from core.tool_registry import register_tool

logger = logging.getLogger("chiron")

# screen_monitor ile aynı liste — "gemini-2.5-flash" bu hesapta 404 veriyor.
FIX_MODELS = (
    "models/gemini-flash-latest",
    "models/gemini-2.5-flash-lite",
)

# Bir hatayı düzeltmek 3 tıklamadan uzunsa bu artık "düzeltme" değil, bir
# kurulum sihirbazı — orada kullanıcı olmalı.
MAX_STEPS = 3

AUTO_FIX_MODES = ("off", "safe", "all")
DEFAULT_MODE = "safe"


# ── Kapı 2: yerel yasak listesi ─────────────────────────────────────────────
# Bu sözcükler hedef tarifinde geçiyorsa OTOMATİK uygulama yok — mod ne olursa
# olsun. Geri alınamayan ya da para/veri kaybettiren şeyler.
#
# Türkçe ekleri yüzünden tam sözcük eşleşmesi yetmiyor ("silmek", "silinsin",
# "kaldırılsın"), bu yüzden alt dize araması yapılıyor. Yanlış pozitif olabilir
# (ör. "Kaldır" içeren zararsız bir düğme) ama bu yönde hata yapmak doğru
# taraf: reddedilen adım kullanıcıya soruluyor, kaybolan bir şey yok.
DESTRUCTIVE_PATTERNS = (
    "sil", "delete", "remove", "kaldır", "uninstall",
    "biçimlendir", "format", "temizle", "wipe", "erase",
    "sıfırla", "reset", "fabrika", "factory",
    "satın al", "öde", "purchase", "buy", "pay", "abone", "subscribe",
    "devre dışı", "disable", "kapat güvenlik", "turn off",
    "izin ver", "allow", "grant", "yönetici olarak", "run as admin",
    "gönder", "send", "paylaş", "share", "karşıya yükle", "upload",
    "biçimlendirme", "disk", "kayıt defteri", "registry",
    "oturumu kapat", "sign out", "log out", "hesabı", "account",
)
# NOT: burada bilerek YOK olan bir sözcük: yalın "yükle". Türkçede hem
# "install" hem "load" demek ve "Sayfayı yeniden yükle" en yaygın zararsız
# düzeltmelerden biri — listeye konsaydı asıl işe yarayacak durum bloklanırdı.
# Karşıya veri gönderen anlamı için "karşıya yükle"/"upload" yeterli.


# Türkçe harfleri ASCII'ye katlayan tablo.
#
# BU BİR GÜZELLİK DEĞİL, GÜVENLİK GEREĞİ (2026-08-01'de testte yakalandı):
# yasak listesi "satın al" yazıyordu ama model hedefi "Satin Al" diye
# diakritiksiz yazınca eşleşme olmuyor ve kapı SESSİZCE açılıyordu. Aynısı
# "gönder"/"Gonder" ve "devre dışı"/"devre disi" için de geçerliydi. LLM'ler
# Türkçe karakterleri sık atlıyor; bir güvenlik kapısının buna takılması
# kabul edilemez. Artık hem liste hem gelen metin aynı biçime indirgeniyor.
_TR_ASCII = str.maketrans("ıİşŞğĞüÜöÖçÇâÂîÎûÛ", "iissgguuooccaaiiuu")


def _normalize(text: str) -> str:
    return (text or "").translate(_TR_ASCII).casefold()


# Liste de aynı biçime indirgenmiş hâlde tutuluyor — karşılaştırma simetrik olmalı.
_DESTRUCTIVE_NORMALIZED = tuple(_normalize(k) for k in DESTRUCTIVE_PATTERNS)


def is_destructive(text: str) -> bool:
    """Hedef tarifi yıkıcı bir eylem içeriyor mu (yerel, modelden bağımsız)."""
    dusuk = _normalize(text)
    return any(kalip in dusuk for kalip in _DESTRUCTIVE_NORMALIZED)


def get_auto_fix_mode() -> str:
    mode = str(get_app_config_value("auto_fix_mode", DEFAULT_MODE) or DEFAULT_MODE).lower()
    return mode if mode in AUTO_FIX_MODES else DEFAULT_MODE


def step_is_auto_allowed(step: dict, mode: str) -> tuple[bool, str]:
    """Bu adım otomatik uygulanabilir mi? (izin, gerekçe) döner."""
    action = str(step.get("action", "click")).strip()
    target = str(step.get("target", "")).strip()
    risk = str(step.get("risk", "high")).strip().lower()

    if mode == "off":
        return False, "otomatik düzeltme kapalı"

    # Kapı 2 — her modda geçerli, en önce bakılıyor.
    if is_destructive(target) or is_destructive(str(step.get("text", ""))):
        return False, "hedef yıkıcı bir eylem içeriyor"

    if mode == "all":
        return True, "tam otonom mod"

    # ── safe modu ──
    # Kapı 1
    if action != "click":
        return False, f"'{action}' otomatik uygulanmıyor (yalnızca tıklama)"
    # Kapı 3
    if risk != "low":
        return False, f"model riski '{risk}' olarak işaretledi"
    return True, "düşük riskli tıklama"


def _plan_prompt(description: str, window_title: str) -> str:
    return (
        "Sen bir masaüstü destek uzmanısın. Aşağıdaki ekran görüntüsünde bir sorun "
        f"tespit edildi.\n\nPencere: '{window_title or 'bilinmiyor'}'\n"
        f"Tespit edilen sorun: {description}\n\n"
        "GÖREVİN: bu sorunun ekranda TIKLAMAYLA çözülüp çözülemeyeceğine karar ver ve "
        "çözülebiliyorsa adımları ver.\n\n"
        "KURALLAR:\n"
        f"- En fazla {MAX_STEPS} adım. Daha uzunsa can_fix_on_screen:false yap.\n"
        "- Her adımın hedefini ekranda GÖRÜNEN metniyle tarif et (ör. \"'Yeniden Dene' "
        "butonu\", \"sağ üstteki kapat (X) ikonu\").\n"
        "- risk alanı: geri alınabilir ve zararsızsa 'low' (diyalog kapatma, yeniden "
        "deneme, tamam'a basma); bir ayarı değiştiriyorsa 'medium'; veri silen, para "
        "harcayan, program kaldıran, güvenlik kapatan her şey 'high'.\n"
        "- RİSK KONUSUNDA TUTUCU OL. Emin değilsen 'high' yaz.\n"
        "- Ekranda çözülemiyorsa (yeniden başlatma, sürücü kurulumu, internet sorunu) "
        "can_fix_on_screen:false yap ve user_advice alanına kullanıcıya söylenecek "
        "somut tavsiyeyi yaz.\n\n"
        "SADECE şu JSON, başka metin/markdown yok:\n"
        '{"diagnosis": "sorunun tek cümlelik teşhisi", "can_fix_on_screen": true/false, '
        '"steps": [{"action": "click", "target": "görünen metniyle hedef", "text": "", '
        '"risk": "low", "why": "bu adım neden"}], "user_advice": "ekranda çözülemiyorsa tavsiye"}'
    )


def plan_fix(api_key: str, description: str, window_title: str) -> dict:
    """Ekrandaki sorun için yapılandırılmış düzeltme planı üretir.

    Teknik bir sorunda (anahtar/API/yakalama) sessizce boş plan döner —
    `check_for_issue` ile aynı sözleşme: bu fonksiyon kullanıcıyla konuşmaz.
    """
    bos = {"diagnosis": "", "can_fix_on_screen": False, "steps": [], "user_advice": ""}
    if not api_key:
        return bos

    image_path = _capture_active_window()
    if image_path is None:
        return bos

    try:
        image_part = types.Part.from_bytes(data=image_path.read_bytes(), mime_type="image/png")
        client = genai.Client(api_key=api_key)
        prompt = _plan_prompt(description, window_title)
        for model_name in FIX_MODELS:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[types.Part.from_text(text=prompt), image_part],
                    config=types.GenerateContentConfig(temperature=0.1),
                )
                parsed = _extract_json(str(getattr(response, "text", "") or ""))
                if parsed is None:
                    continue
                adimlar = parsed.get("steps")
                if not isinstance(adimlar, list):
                    adimlar = []
                return {
                    "diagnosis": str(parsed.get("diagnosis") or "").strip(),
                    "can_fix_on_screen": bool(parsed.get("can_fix_on_screen")),
                    "steps": [s for s in adimlar if isinstance(s, dict)][:MAX_STEPS],
                    "user_advice": str(parsed.get("user_advice") or "").strip(),
                }
            except Exception:
                continue
        return bos
    except Exception:
        logger.exception("[CHIRON] Düzeltme planı üretilemedi")
        return bos
    finally:
        try:
            image_path.unlink()
        except Exception:
            pass


def apply_plan(plan: dict, mode: str) -> dict:
    """Planı politikaya göre uygular.

    {"applied": [...], "blocked": [...], "failed": [...]} döner. Uygulama
    `intervene_screen` üzerinden — ekranı bulma/doğrulama mantığı tek yerde
    kalıyor ([[Ekran-Mudahale]]), burada kopyalanmıyor.

    ## İki fazlı uygulama — yasak listesinin asıl gücü burada

    Yerel yasak listesi tek başına kandırılabilir: model "Sil" düğmesini
    "kırmızı buton" diye tarif ederse kapı açılırdı, çünkü kapı yalnızca
    TARİFİ görüyor. Bu yüzden her adım iki fazda yürüyor:

      1. `confirm=False` — hiçbir şey yapmaz, yalnızca hedefi BULUR ve ne
         bulduğunu `data.target` içinde geri verir.
      2. Bulunan şeyin tarifi yasak listesinden geçirilir, temizse
         `confirm=True` ile gerçekten tıklanır.

    Yani karar, modelin ne demek istediğine değil ekranda GERÇEKTEN bulunan
    şeye göre veriliyor. Bedeli adım başına fazladan bir vision çağrısı;
    otomatik düzeltme nadir çalıştığı için kabul edilebilir bir kota maliyeti.
    """
    from actions.screen_control import intervene_screen

    sonuc: dict[str, list] = {"applied": [], "blocked": [], "failed": []}
    if not plan.get("can_fix_on_screen"):
        return sonuc

    for step in plan.get("steps", []):
        hedef = str(step.get("target", "")).strip()
        if not hedef:
            continue

        izin, gerekce = step_is_auto_allowed(step, mode)
        if not izin:
            sonuc["blocked"].append({"target": hedef, "reason": gerekce})
            # İlk engelde DURUYORUZ: adımlar sıralı, ikincisi birincinin
            # ekranı değiştirmesine bağlı. Atlayıp devam etmek, var olmayan
            # bir ekranda tıklamaya çalışmak olurdu.
            break

        eylem = str(step.get("action", "click"))
        metin = str(step.get("text", ""))

        # ── Faz 1: yalnızca bul ──
        try:
            onizleme = intervene_screen(
                instruction=hedef, action=eylem, text=metin, confirm=False
            )
        except Exception as e:
            sonuc["failed"].append({"target": hedef, "error": str(e)})
            break

        if not onizleme.get("success"):
            sonuc["failed"].append({"target": hedef, "error": onizleme.get("message", "")})
            break

        bulunan = str(onizleme.get("data", {}).get("target", "") or hedef)
        if is_destructive(bulunan):
            sonuc["blocked"].append({
                "target": hedef,
                "found": bulunan,
                "reason": f"ekranda bulunan öğe yıkıcı görünüyor: '{bulunan}'",
            })
            break

        # ── Faz 2: gerçekten uygula ──
        try:
            r = intervene_screen(
                instruction=hedef, action=eylem, text=metin, confirm=True
            )
        except Exception as e:
            sonuc["failed"].append({"target": hedef, "error": str(e)})
            break

        if r.get("success"):
            sonuc["applied"].append({"target": bulunan, "message": r.get("message", "")})
        else:
            sonuc["failed"].append({"target": hedef, "error": r.get("message", "")})
            break

    return sonuc


@register_tool("set_auto_fix")
def set_auto_fix(mode: str) -> dict:
    """Otonom düzeltme politikasını değiştirir (off / safe / all)."""
    # Eşanlamlar da normalize ediliyor: kullanıcı "güvenli" de diyebilir
    # "guvenli" de, ve konuşma tanıma ikisini de üretebiliyor.
    temiz = _normalize((mode or "").strip())
    esanlam = {
        _normalize(k): v
        for k, v in {
            "kapalı": "off", "kapat": "off", "hayır": "off", "dokunma": "off",
            "güvenli": "safe", "normal": "safe", "sor": "safe",
            "hepsi": "all", "tam": "all", "açık": "all", "aç": "all", "sorma": "all",
        }.items()
    }
    temiz = esanlam.get(temiz, temiz)
    if temiz not in AUTO_FIX_MODES:
        return fail("Geçerli modlar: off (hiç dokunma), safe (güvenli olanları kendi yap), all (hepsini kendi yap).")

    save_app_config({"auto_fix_mode": temiz})
    aciklama = {
        "off": "Otomatik düzeltme kapatıldı — hata görürsem sadece haber veririm.",
        "safe": "Otomatik düzeltme güvenli modda — geri alınabilir tıklamaları kendim yaparım, riskli olanları sana sorarım.",
        "all": "Otomatik düzeltme tam modda — sormadan uygularım. Veri silen, para harcayan adımlar yine de sana sorulur.",
    }[temiz]
    return ok(aciklama, mode=temiz)
