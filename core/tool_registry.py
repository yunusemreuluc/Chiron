"""
Araç kayıt defteri (Tool Registry) — dekoratör tabanlı, MCP-uyumlu şekle
hazırlanmış (bkz. modül sonundaki not).

Eskiden main.py içinde 20+ dallı, elle yazılmış bir if/elif zinciri vardı: her
yeni araç için hem tool_defs.py'ye şema eklemek hem BURAYA elle bir dal (isim
kontrolü + pozisyonel argüman çıkarma + tip dönüştürme) eklemek gerekiyordu —
iki dosyayı senkron tutmak, derleyicinin yakalayamadığı, insanın unutabileceği
bir riskti (bu projede intervene_screen'e app_hint eklenirken tam olarak
yaşandı). Artık bir araç fonksiyonu sadece `@register_tool("adi")` ile
işaretleniyor; `dispatch_tool()` Gemini'den gelen düz {"param": değer}
sözlüğünü fonksiyonun GERÇEK imzasına (inspect.signature) göre otomatik
eşleştirip tipe göre dönüştürüyor (kwarg-binding) — isim/sıra hatası riski
ortadan kalkıyor.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable

from actions.tool_result import fail

_REGISTRY: dict[str, Callable[..., Any]] = {}


def register_tool(name: str):
    """Dekoratör: fonksiyonu (veya `self` alan bir metodu) `name` altında
    kayıt defterine ekler. Fonksiyonun kendisini değiştirmeden döner."""
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        _REGISTRY[name] = func
        return func
    return decorator


def get_tool(name: str) -> Callable[..., Any] | None:
    return _REGISTRY.get(name)


def _annotation_kind(annotation: Any) -> str:
    """Tip anotasyonunu kaba bir 'bool | int | float | str | any' sınıfına
    indirger. `str | None` / `Optional[str]` gibi union'ları da (get_origin/
    get_args ile uğraşmadan) yakalamak için metin tabanlı, bilinçli olarak
    basit bir yaklaşım — bu bir genel-amaçlı tip kütüphanesi değil, sadece
    Gemini'nin gönderdiği JSON değerlerini araç fonksiyonunun beklediği
    Python tipine çevirmek için yeterli bir sezgisel."""
    text = str(annotation)
    if "bool" in text:
        return "bool"
    if "float" in text:
        return "float"
    if "int" in text:
        return "int"
    if "str" in text:
        return "str"
    return "any"


def _coerce(value: Any, kind: str, default: Any) -> Any:
    if value is None:
        return default
    try:
        if kind == "bool":
            return bool(value)
        if kind == "int":
            return int(value)
        if kind == "float":
            return float(value)
        if kind == "str":
            return str(value)
    except (TypeError, ValueError):
        return default
    return value


def bind_args(func: Callable[..., Any], raw_args: dict) -> dict:
    """Gemini'den gelen düz {"param": değer} sözlüğünü, `func`'ın GERÇEK
    parametre imzasına (ad + tip + varsayılan) göre tip-güvenli bir kwargs
    sözlüğüne çevirir. `self` parametresi (varsa) atlanır — dispatch_tool()
    onu ayrıca enjekte eder."""
    sig = inspect.signature(func)
    bound: dict[str, Any] = {}
    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue
        has_default = param.default is not inspect.Parameter.empty
        default = param.default if has_default else None
        kind = _annotation_kind(param.annotation) if param.annotation is not inspect.Parameter.empty else (
            _annotation_kind(type(default)) if has_default and default is not None else "str"
        )
        raw_value = raw_args.get(param_name, default)
        if raw_value is None and kind == "str":
            raw_value = ""
        bound[param_name] = _coerce(raw_value, kind, default)
    return bound


async def dispatch_tool(name: str, raw_args: dict, *, instance: Any = None, loop: asyncio.AbstractEventLoop | None = None) -> dict:
    """Kayıtlı bir aracı bulur, argümanlarını bağlar ve çalıştırır.

    - `instance` verilirse ve fonksiyonun imzasında `self` varsa, ilk argüman
      olarak enjekte edilir (ChironLive metodu olan araçlar için — bkz. main.py).
    - Fonksiyon zaten async ise doğrudan awaitlenir; değilse (çoğu araç bloklayıcı
      I/O yaptığı için) run_in_executor ile ayrı bir thread'de çalıştırılır.
    - Kayıtlı değilse veya çalıştırma sırasında exception fırlatırsa standart
      {"success": False, ...} şeması ile döner — çağıran taraf (main.py) tek
      bir kontrol noktasından (result["success"]) karar verebilir.
    """
    func = get_tool(name)
    if func is None:
        return fail(f"Bilinmeyen araç: {name}")

    sig = inspect.signature(func)
    needs_self = "self" in sig.parameters
    kwargs = bind_args(func, raw_args)

    def _call_sync():
        return func(instance, **kwargs) if needs_self else func(**kwargs)

    if inspect.iscoroutinefunction(func):
        return await (func(instance, **kwargs) if needs_self else func(**kwargs))

    active_loop = loop or asyncio.get_event_loop()
    return await active_loop.run_in_executor(None, _call_sync)


# ── MCP (Model Context Protocol) notu ────────────────────────────────────────
# Bu registry BİLEREK Gemini'ye özel bir şey içermiyor: isim -> çağrılabilir
# fonksiyon eşlemesi ve şema-bağımsız kwarg-binding. tool_defs.py'deki
# TOOL_DECLARATIONS (Gemini'nin function-calling şeması) ile bu registry'nin
# anahtarları (araç adları) birebir örtüşüyor ama registry'nin kendisi Gemini
# API'sinden habersiz. İleride harici bir MCP sunucusuna bağlanmak istenirse,
# o sunucunun tools/list çağrısından dönen şemalar TOOL_DECLARATIONS'a
# eklenip, karşılık gelen çağrı fonksiyonları (bir MCP client çağrısını sarmalayan
# ince fonksiyonlar) aynı @register_tool(...) dekoratörüyle buraya kaydedilebilir
# — main.py'deki dispatch mantığı hiç değişmeden yeni araçları kaldırır.
