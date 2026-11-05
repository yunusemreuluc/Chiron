"""Canlı yükleme — kod değişiklikleri Chiron'u yeniden başlatmadan çalışan sürece uygulanır (2026-11-04).

Kullanıcı isteği: "yeniden başlatmaya gerek kalmadan değişiklikler çalışma anında uygulansın".
Chiron TEK süreç (WebView + FastAPI + ses döngüsü + Claude işleri): yeniden başlatmak süren
Claude işlerini, sesli oturumu ve Komuta sohbetini öldürür. `uvicorn --reload` da aynı şey
(süreci yeniden kurar). Bu yüzden modül yeniden YÜKLENMEZ, YAMALANIR:

    • Fonksiyon/metot: yeni kaynak derlenir, eski fonksiyon nesnesinin `__code__`'u değiştirilir.
      Nesne aynı kalır → `from x import f` yapmış modüller, kayıtlı araçlar (@register_tool),
      FastAPI rotaları, thread hedefleri hepsi yeni kodu çalıştırır.
    • Durum korunur: modülün üst düzey satırları YENİDEN ÇALIŞTIRILMAZ (`pano = Pano()` ikinci
      bir pano kurmasın, kilitler/thread'ler/önbellekler yerinde kalsın). Yalnız DEĞİŞEN satırlar
      uygulanır; değişen satır bir durum nesnesiyse dokunulmaz, "yeniden başlatma gerekir" denir.
    • Yeni fonksiyon/sınıf/import/sabit eklenir. Yeni rota (backend/api/*) uygulamaya, "/" arayüz
      mount'undan ÖNCE takılır (Starlette sırayla eşleştirir; sona eklenen rota hiç çağrılmaz).
    • Arayüz: `frontend/out` yeniden derlenince WebSocket'ten `ui_updated` gider, sayfa kendini
      yeniler (açık pencere/yazılan metin varken bekler — useLiveReload.ts).

Uygulanamayan değişiklikler sessizce yutulmaz: `restart` listesinde nedeniyle döner, durum
`GET /api/canli`'dan okunur ve `code_reload` olayıyla arayüze gider.

Bilinçli sınırlar (yeniden başlatma ister): mevcut bir FastAPI uç noktasının imzası (parametreleri
FastAPI kayıtta okuyor), değişen sınıf alanları (@dataclass/pydantic), üst düzey durum nesneleri
(`x = Sinif()`), modül gövdesindeki if/try blokları, tool_defs'in Gemini Live'a giden bildirimi
(yeni oturumda geçerli olur).
"""

from __future__ import annotations

import ast
import logging
import sys
import threading
import time
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("chiron.canli")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
WATCH_DIRS = ("backend", "actions", "core")
WATCH_FILES = ("tool_defs.py", "main.py", "app_config.py")
UI_MARKER = BASE_DIR / "frontend" / "out" / "index.html"
POLL_SECONDS = 1.0
# Dosya yazılırken (editör/Claude parça parça kaydeder) yarım kaynağı yamamamak için bekleme.
SETTLE_SECONDS = 0.6
# `npm run build` out/'u siler ve baştan yazar; index.html sona doğru gelir, yine de biraz bekle.
UI_SETTLE_SECONDS = 2.5
SKIP_PARTS = {"__pycache__", "venv", ".venv", "node_modules", "tests"}
SELF_MODULE = __name__

IMMUTABLE = (int, float, complex, str, bytes, bool, type(None), tuple, frozenset, range)


@dataclass
class PatchResult:
    module: str
    path: str
    ok: bool = True
    applied: list[str] = field(default_factory=list)
    restart: list[str] = field(default_factory=list)
    error: str = ""
    at: float = field(default_factory=time.time)

    def public(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "path": self.path,
            "ok": self.ok,
            "applied": self.applied,
            "restart": self.restart,
            "error": self.error,
            "at": self.at,
        }


# ── Yardımcılar ─────────────────────────────────────────────────────────


def _innermost(obj: Any) -> types.FunctionType | None:
    """staticmethod/classmethod/property/functools.wraps zincirinin altındaki gerçek fonksiyon."""
    seen = 0
    while obj is not None and seen < 20:
        seen += 1
        if isinstance(obj, types.FunctionType):
            wrapped = getattr(obj, "__wrapped__", None)
            if isinstance(wrapped, types.FunctionType) or hasattr(wrapped, "__func__"):
                obj = wrapped
                continue
            return obj
        if isinstance(obj, (staticmethod, classmethod)):
            obj = obj.__func__
            continue
        if isinstance(obj, property):
            obj = obj.fget
            continue
        wrapped = getattr(obj, "__wrapped__", None) or getattr(obj, "__func__", None)
        if wrapped is None:
            return None
        obj = wrapped
    return None


def _patch_function(old: types.FunctionType, new: types.FunctionType) -> bool:
    """`old`'u yerinde `new`'e çevirir. Serbest değişkenler uyuşmazsa False (çağıran nesneyi değiştirir)."""
    if old.__code__.co_freevars != new.__code__.co_freevars:
        return False
    old.__code__ = new.__code__
    old.__defaults__ = new.__defaults__
    old.__kwdefaults__ = new.__kwdefaults__
    old.__annotations__ = new.__annotations__
    old.__doc__ = new.__doc__
    return True


def _rebind_closure(new: types.FunctionType, owner_cls: type | None, module_globals: dict) -> types.FunctionType:
    """Sınıf dışında derlenmiş metodun `__class__` hücresini GERÇEK (eski) sınıfa bağlar — yoksa
    argümansız super() geçici kopya sınıfı arar ve "obj must be an instance" hatası verir."""
    if not new.__code__.co_freevars:
        return new
    cells = []
    for name, cell in zip(new.__code__.co_freevars, new.__closure__ or ()):
        cells.append(types.CellType(owner_cls) if name == "__class__" and owner_cls is not None else cell)
    fn = types.FunctionType(new.__code__, module_globals, new.__name__, new.__defaults__, tuple(cells))
    fn.__kwdefaults__ = new.__kwdefaults__
    fn.__annotations__ = new.__annotations__
    fn.__doc__ = new.__doc__
    fn.__qualname__ = new.__qualname__
    fn.__module__ = new.__module__
    fn.__dict__.update(new.__dict__)
    return fn


def _rewrap(template: Any, fn: types.FunctionType) -> Any:
    if isinstance(template, staticmethod):
        return staticmethod(fn)
    if isinstance(template, classmethod):
        return classmethod(fn)
    return fn


def _attach(old_cls: type, template: Any, inner: types.FunctionType, g: dict) -> Any:
    """Sınıfa takılacak değer: düz fonksiyon / static / classmethod ise `__class__` hücresi eski
    sınıfa bağlanır; başka bir sarmalayıcıysa (functools.wraps) olduğu gibi takılır."""
    if template is inner or (isinstance(template, (staticmethod, classmethod)) and template.__func__ is inner):
        return _rewrap(template, _rebind_closure(inner, old_cls, g))
    return template


def _body_others(tree: ast.Module) -> set[str]:
    """Fonksiyon/sınıf/import/atama/docstring DIŞINDAKİ üst düzey satırlar (if, try, çağrı…)."""
    return {
        _dump(n)
        for n in tree.body
        if not isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and not (isinstance(n, (ast.Assign, ast.AnnAssign)) and _names(n))
        and not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))
    }


def _stmt_key(node: ast.stmt) -> str | None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return f"def:{node.name}"
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return None  # import'lar anahtarsız: her yeni/değişen import çalıştırılır (idempotent)
    if isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) for t in node.targets):
        return "set:" + ",".join(t.id for t in node.targets)  # type: ignore[attr-defined]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return f"set:{node.target.id}"
    return None


def _dump(node: ast.AST) -> str:
    return ast.dump(node, include_attributes=False)


def _names(node: ast.stmt) -> list[str]:
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


def _compile(nodes: list[ast.stmt], filename: str, flags: int = 0) -> types.CodeType:
    """Tek tanımı derler. `flags` modülün __future__ bayrakları: parça derlemede miras kalmaz —
    `from __future__ import annotations` atlanırsa tip ipuçları hemen değerlendirilir, kod farklı
    çıkar (her fonksiyon "değişti" görünür) ve ileri referanslar NameError verir."""
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    return compile(module, filename, "exec", flags=flags, dont_inherit=True)


def _members(node: ast.ClassDef) -> dict[str, str]:
    """Sınıf gövdesindeki her adın AST'si (property getter+setter aynı adda birleşir)."""
    out: dict[str, list[str]] = {}
    for child in node.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [child.name]
        elif isinstance(child, (ast.Assign, ast.AnnAssign)):
            names = _names(child)
        else:
            continue
        for n in names:
            out.setdefault(n, []).append(_dump(child))
    return {k: "\n".join(v) for k, v in out.items()}


def _future_flags(tree: ast.Module) -> int:
    import __future__

    flags = 0
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            for alias in node.names:
                feature = getattr(__future__, alias.name, None)
                if feature is not None:
                    flags |= feature.compiler_flag
    return flags


# ── Yamacı ──────────────────────────────────────────────────────────────


class Patcher:
    """Bir modülün çalışan kopyasını dosyadaki yeni kaynağa göre yamalar.

    Taban: modülün en son BAŞARIYLA uygulanan kaynağının AST'si. "Değişti mi" kararı tabana göre
    verilir — kaynaktan (.pyc) ve AST'den derlenen bayt kod 3.11'de birebir aynı çıkmıyor
    (ölçüldü: 81 modülün 70'i değişmeden "değişti" göründü). Uygulanamayan tanımın tabanı ESKİ
    halinde bırakılır: bir sonraki kayıtta yeniden denenir, değişiklik sessizce kaybolmaz.

    Tabanı olmayan modülde (izleyici onu ilk kez görüyor) değişiklik UYGULANMAZ: neyin değiştiğini
    bilemeyiz, kör yama sınıf gövdelerini boşuna çalıştırır ve dekoratörleri düşürebilir. O dosya
    taban olarak kaydedilir ve "yeniden başlatma gerekir" denir. İzleyici sonradan import edilen
    modülleri her taramada tabana aldığı için bu durum pratikte yalnız ilk saniyelerde olur.

    Bir dosyanın yamaları atomik değildir: `f` yeni imzayla `g`'yi çağırırken `g` birkaç ms eski
    kalabilir. Çalışan çerçeveler eski kodla biter (CPython `__code__` takası GIL altında güvenli).
    """

    def __init__(self) -> None:
        # modül → anahtar ("def:ad", "set:ad") → AST düğümü
        self._nodes: dict[str, dict[str, ast.stmt]] = {}
        self._imports: dict[str, set[str]] = {}
        self._others: dict[str, set[str]] = {}
        self.on_api_change: Callable[[types.ModuleType], list[str]] | None = None
        self._flags = 0
        self._base: dict[str, ast.stmt] = {}
        self._failed: list[ast.stmt] = []

    # Taban
    def known(self, module_name: str) -> bool:
        return module_name in self._nodes

    def remember(self, module_name: str, source: str) -> None:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return
        self._remember_tree(module_name, tree)

    def _remember_tree(self, module_name: str, tree: ast.Module) -> None:
        self._nodes[module_name] = {k: n for n in tree.body if (k := _stmt_key(n))}
        self._imports[module_name] = {_dump(n) for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))}
        self._others[module_name] = _body_others(tree)

    def patch(self, module: types.ModuleType, path: Path, source: str | None = None) -> PatchResult:
        name = module.__name__
        result = PatchResult(module=name, path=str(path))
        try:
            source = path.read_text(encoding="utf-8") if source is None else source
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError, ValueError) as error:
            result.ok = False
            result.error = f"{type(error).__name__}: {error}"
            return result

        if not self.known(name):
            self._remember_tree(name, tree)
            result.restart.append("izleyici bu modülü ilk kez görüyor: neyin değiştiği bilinmiyor, taban kaydedildi")
            return result

        g = module.__dict__
        self._flags = _future_flags(tree)
        self._base = old_nodes = self._nodes[name]
        self._failed = []
        base_imports = self._imports.get(name, set())
        base_others = self._others.get(name, set())
        is_api = name.startswith("backend.api.")
        new_routes = False

        for node in tree.body:
            try:
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if _dump(node) not in base_imports:
                        exec(_compile([node], str(path), self._flags), g)
                        result.applied.append(f"import satırı {node.lineno}")
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    added = self._patch_def(node, g, path, result, is_api)
                    new_routes = new_routes or (added and is_api and bool(node.decorator_list))
                elif isinstance(node, ast.ClassDef):
                    self._patch_class(node, g, path, result)
                elif isinstance(node, (ast.Assign, ast.AnnAssign)) and _names(node):
                    self._patch_assign(node, g, path, result)
                elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                    continue  # docstring
                elif _dump(node) not in base_others:
                    # if/try/çağrı gibi gövde satırları: yeniden çalıştırmak yan etki doğurur.
                    result.restart.append(f"satır {node.lineno}: modül gövdesi ({type(node).__name__})")
            except Exception as error:  # tek tanımın hatası diğerlerini durdurmasın
                result.ok = False
                self._failed.append(node)
                result.restart.append(f"satır {getattr(node, 'lineno', '?')}: {type(error).__name__}: {error}")
                logger.exception("Canlı yama hatası: %s satır %s", name, getattr(node, "lineno", "?"))

        new_keys = {k for n in tree.body if (k := _stmt_key(n))}
        for key, old in old_nodes.items():
            if key.startswith("def:") and key not in new_keys:
                # Silinen/yeniden adlandırılan tanım bellekte (ve kayıtlı rota/araç olarak) duruyor.
                result.restart.append(f"{key[4:]}: dosyadan kalktı ama bellekte duruyor")

        if is_api and new_routes and self.on_api_change:
            try:
                result.applied.extend(self.on_api_change(module))
            except Exception as error:
                result.ok = False
                result.restart.append(f"rota eklenemedi: {error}")
                logger.exception("Canlı rota eşitleme hatası: %s", name)

        # Yeni taban — ama uygulanamayan tanımlar eski halinde kalır (sonraki kayıtta yeniden denenir).
        self._remember_tree(name, tree)
        for node in self._failed:
            key = _stmt_key(node)
            if key and key in old_nodes:
                self._nodes[name][key] = old_nodes[key]
            elif key:
                self._nodes[name].pop(key, None)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                self._imports[name].discard(_dump(node))
            else:
                self._others[name].discard(_dump(node))
        return result

    # Fonksiyon
    def _patch_def(self, node: ast.FunctionDef | ast.AsyncFunctionDef, g: dict, path: Path,
                   result: PatchResult, is_api: bool) -> bool:
        """True = yeni tanım eklendi (dekoratörüyle birlikte çalıştırıldı)."""
        old = g.get(node.name)
        old_fn = _innermost(old) if old is not None else None
        prev = self._base.get(f"def:{node.name}")
        if old_fn is not None and prev is not None and _dump(prev) == _dump(node):
            return False
        if old_fn is None:
            if old is not None:
                result.restart.append(f"{node.name}: aynı adlı fonksiyon olmayan nesne var")
                return False
            # Yeni tanım: dekoratörleriyle (rota/araç kaydı istenen yan etki).
            router = g.get("router") if is_api else None
            before = len(getattr(router, "routes", ()) or ())
            exec(_compile([node], str(path), self._flags), g)
            for route in list(getattr(router, "routes", ()) or ())[before:]:
                route._canli_new = True  # sync_routes etiketlesin
            result.applied.append(f"yeni: {node.name}()")
            return True

        if isinstance(prev, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if [_dump(d) for d in prev.decorator_list] != [_dump(d) for d in node.decorator_list]:
                result.restart.append(f"{node.name}(): dekoratör değişti (rota/kayıt eski halinde)")
            if is_api and node.decorator_list and (
                type(prev) is not type(node) or _dump(prev.args) != _dump(node.args)
                or _dump(prev.returns or ast.Pass()) != _dump(node.returns or ast.Pass())
            ):
                result.restart.append(f"{node.name}(): uç noktanın imzası değişti (FastAPI kayıtta okur)")

        bare = ast.copy_location(
            type(node)(**{f: getattr(node, f) for f in node._fields if f != "decorator_list"}, decorator_list=[]),
            node,
        )
        ns: dict[str, Any] = {}
        exec(_compile([bare], str(path), self._flags), g, ns)
        new_fn = ns[node.name]
        if _patch_function(old_fn, new_fn):
            result.applied.append(f"{node.name}()")
        elif old is old_fn and not old_fn.__code__.co_freevars and not node.decorator_list:
            g[node.name] = new_fn
            result.applied.append(f"{node.name}() (yeni nesne)")
            result.restart.append(f"{node.name}(): kapanış değişti, eski referanslar eski kodu çalıştırır")
        else:
            # Sarmalayıcıyı (functools.wraps'siz dekoratör) düşürmektense dokunma.
            self._failed.append(node)
            result.restart.append(f"{node.name}(): sarmalanmış fonksiyon yerinde değiştirilemedi")
        return False

    # Sınıf
    def _patch_class(self, node: ast.ClassDef, g: dict, path: Path, result: PatchResult) -> None:
        old_cls = g.get(node.name)
        prev = self._base.get(f"def:{node.name}")
        if not isinstance(old_cls, type):
            if old_cls is None:
                exec(_compile([node], str(path), self._flags), g)
                result.applied.append(f"yeni sınıf: {node.name}")
            else:
                result.restart.append(f"{node.name}: aynı adlı sınıf olmayan nesne var")
            return
        if prev is not None and _dump(prev) == _dump(node):
            return  # sınıf hiç değişmedi: gövdesini (metasınıf yan etkileri) boşuna çalıştırma
        base_members = _members(prev) if isinstance(prev, ast.ClassDef) else {}
        new_members = _members(node)
        if isinstance(prev, ast.ClassDef) and (
            [_dump(d) for d in prev.decorator_list] != [_dump(d) for d in node.decorator_list]
            or [_dump(b) for b in prev.bases] != [_dump(b) for b in node.bases]
        ):
            result.restart.append(f"{node.name}: sınıf dekoratörü/tabanı değişti")
        for name in base_members:
            if name not in new_members:
                result.restart.append(f"{node.name}.{name}: dosyadan kalktı ama bellekte duruyor")
        # Sınıf gövdesi geçici bir sınıfa derlenir; sınıf dekoratörleri (dataclass, kayıt) atlanır.
        bare = ast.ClassDef(
            name=node.name, bases=node.bases, keywords=node.keywords, body=node.body, decorator_list=[],
            **({"type_params": []} if "type_params" in ast.ClassDef._fields else {}),
        )
        ast.copy_location(bare, node)
        ns: dict[str, Any] = {}
        exec(_compile([bare], str(path), self._flags), g, ns)
        tmp_cls = ns[node.name]
        old_ann = list(old_cls.__dict__.get("__annotations__", {}))
        new_ann = list(tmp_cls.__dict__.get("__annotations__", {}))
        if old_ann != new_ann:
            result.restart.append(f"{node.name}: sınıf alanları değişti")
        for attr, new_val in tmp_cls.__dict__.items():
            if attr in ("__dict__", "__weakref__", "__module__", "__qualname__", "__annotations__", "__doc__"):
                continue
            if attr in new_members and base_members.get(attr) == new_members[attr]:
                continue
            label = f"{node.name}.{attr}"
            old_val = old_cls.__dict__.get(attr)
            if isinstance(new_val, property):
                self._patch_property(old_cls, attr, old_val, new_val, g, result, label)
                continue
            new_fn = _innermost(new_val)
            if new_fn is not None:
                self._patch_method(old_cls, attr, old_val, new_val, new_fn, g, result, label)
                continue
            # Sınıf düzeyi değer (metasınıfın ürettiği __pydantic_*__ gibi dunder'lara dokunulmaz)
            if attr.startswith("__") and attr.endswith("__"):
                continue
            if attr not in old_cls.__dict__:
                if attr in new_members:
                    setattr(old_cls, attr, new_val)
                    result.applied.append(f"yeni: {label}")
            elif isinstance(new_val, IMMUTABLE) and isinstance(old_val, IMMUTABLE):
                if old_val != new_val or type(old_val) is not type(new_val):
                    setattr(old_cls, attr, new_val)
                    result.applied.append(label)
            elif attr in new_members:
                result.restart.append(f"{label}: değiştirilebilir sınıf değeri, yerinde değiştirilmedi")

    def _patch_method(self, old_cls: type, attr: str, old_val: Any, new_val: Any, new_fn: types.FunctionType,
                      g: dict, result: PatchResult, label: str) -> None:
        old_fn = _innermost(old_val) if old_val is not None else None
        if old_fn is None:
            setattr(old_cls, attr, _attach(old_cls, new_val, new_fn, g))
            result.applied.append(f"yeni: {label}()")
            return
        wrapper_changed = type(old_val) is not type(new_val) and (
            isinstance(old_val, (staticmethod, classmethod)) or isinstance(new_val, (staticmethod, classmethod))
        )
        if not wrapper_changed and _patch_function(old_fn, new_fn):
            result.applied.append(f"{label}()")
            return
        plain = old_val is old_fn or isinstance(old_val, (staticmethod, classmethod))
        if plain and (new_val is new_fn or isinstance(new_val, (staticmethod, classmethod))):
            setattr(old_cls, attr, _attach(old_cls, new_val, new_fn, g))
            result.applied.append(f"{label}() (yeni nesne)")
            result.restart.append(f"{label}(): önceden alınmış bağlı metotlar (thread hedefi, callback) eski kodu çalıştırır")
        else:
            result.restart.append(f"{label}(): sarmalanmış metot yerinde değiştirilemedi")

    def _patch_property(self, old_cls: type, attr: str, old_val: Any, new_val: property, g: dict,
                        result: PatchResult, label: str) -> None:
        if not isinstance(old_val, property):
            fns = [_rebind_closure(f, old_cls, g) if f else None for f in (new_val.fget, new_val.fset, new_val.fdel)]
            setattr(old_cls, attr, property(*fns, new_val.__doc__))
            result.applied.append(f"yeni: {label}")
            return
        parts: list[Any] = []
        changed = rebuilt = False
        for part in ("fget", "fset", "fdel"):
            o, n = getattr(old_val, part), getattr(new_val, part)
            if o is None and n is None:
                parts.append(None)
            elif o is not None and n is not None and _patch_function(o, n):
                parts.append(o)
                changed = True
            else:
                parts.append(_rebind_closure(n, old_cls, g) if n is not None else None)
                changed = rebuilt = True
        if rebuilt:
            setattr(old_cls, attr, property(*parts, new_val.__doc__))
        if changed:
            result.applied.append(label)

    # Üst düzey atama
    def _patch_assign(self, node: ast.Assign | ast.AnnAssign, g: dict, path: Path, result: PatchResult) -> None:
        """Karar sağ taraf ÇALIŞTIRILMADAN verilir (inceleme bulgusu): `x = Pano()` değişince ikinci
        bir pano kurulup sızmasın, çalışma anında dolan kayıt defteri `{}` ile silinmesin."""
        key = _stmt_key(node)
        prev = self._base.get(key) if key else None
        names = _names(node)
        if prev is not None and _dump(prev) == _dump(node):
            return
        if isinstance(node, ast.AnnAssign) and node.value is None:
            return
        existing = [n for n in names if n in g]
        if not existing:
            exec(_compile([node], str(path), self._flags), g)
            result.applied.extend(f"yeni: {n}" for n in names)
            return
        olds = [g[n] for n in existing]
        if all(isinstance(o, IMMUTABLE) for o in olds):
            ns: dict[str, Any] = {}
            exec(_compile([node], str(path), self._flags), g, ns)
            for n in names:
                if n in ns:
                    g[n] = ns[n]
                    result.applied.append(n)
            return
        if len(names) == 1 and isinstance(olds[0], (list, dict, set)):
            # Kap yalnız iki taraf da düz literalse VE çalışma anında elle doldurulmamışsa
            # (mevcut değer eski literale eşit) yerinde güncellenir — `from x import LISTE` yapanlar da görsün.
            try:
                new_value = ast.literal_eval(node.value)  # type: ignore[arg-type]
                old_value = ast.literal_eval(prev.value) if isinstance(prev, (ast.Assign, ast.AnnAssign)) and prev.value else _MISSING
            except (ValueError, SyntaxError, TypeError):
                new_value = old_value = _MISSING
            old = olds[0]
            if old_value is not _MISSING and old == old_value and type(old) is type(new_value):
                if isinstance(old, list):
                    old[:] = new_value
                else:
                    old.clear()
                    old.update(new_value)
                result.applied.append(names[0])
                return
            result.restart.append(f"{names[0]}: çalışma anında dolan ya da literal olmayan kap, yerinde değiştirilmedi")
            return
        for n, o in zip(existing, olds):
            result.restart.append(f"{n}: durum nesnesi ({type(o).__name__}), yerinde değiştirilmedi")


_MISSING = object()


# ── FastAPI rota eşitleme ───────────────────────────────────────────────


def sync_routes(app: Any, module: types.ModuleType) -> list[str]:
    """Modülün router'ına yeni eklenen rotaları uygulamada çalışır hale getirir.

    FastAPI 0.140+ `include_router`'da alt router'ı REFERANSLA tutuyor (`_IncludedRouter`) ve
    eşleştirme listesini router değiştikçe yeniden kuruyor — yeni rota kendiliğinden görünür,
    burada yalnız etiketlenir. Eski sürümlerde rotalar kopyalanıyordu: o durumda eksikler
    "/" arayüz mount'undan ÖNCE takılır (Starlette sırayla eşleştirir, sona eklenen hiç çağrılmaz).
    """
    from fastapi import APIRouter
    from starlette.routing import Mount

    router = getattr(module, "router", None)
    if router is None:
        return []

    def label(route: Any) -> str:
        return f"rota: {' '.join(sorted(getattr(route, 'methods', None) or ()))} {getattr(route, 'path', '?')}"

    if any(getattr(r, "original_router", None) is router for r in app.router.routes):
        labels = []
        for route in router.routes:
            if getattr(route, "_canli_new", False):
                route._canli_new = False
                labels.append(f"{label(route)} (canlı)")
        return labels

    staging = APIRouter()
    staging.include_router(router)

    def key(route: Any) -> tuple:
        return (getattr(route, "path", None), frozenset(getattr(route, "methods", None) or ()))

    existing = {key(r) for r in app.router.routes}
    fresh = [r for r in staging.routes if key(r) not in existing]
    if not fresh:
        return []
    routes = app.router.routes
    index = next((i for i, r in enumerate(routes) if isinstance(r, Mount) and r.path in ("", "/")), len(routes))
    routes[index:index] = fresh
    return [label(r) for r in fresh]


# ── İzleyici ────────────────────────────────────────────────────────────


def _module_map() -> dict[Path, types.ModuleType]:
    out: dict[Path, types.ModuleType] = {}
    for module in list(sys.modules.values()):
        file = getattr(module, "__file__", None)
        if not file or not str(file).endswith(".py"):
            continue
        try:
            out[Path(file).resolve()] = module
        except OSError:
            continue
    return out


def _module_for(path: Path) -> types.ModuleType | None:
    return _module_map().get(path.resolve())


class LiveReloader:
    def __init__(self, base_dir: Path = BASE_DIR) -> None:
        self.base_dir = base_dir
        self.patcher = Patcher()
        self._mtimes: dict[Path, float] = {}
        self._pending: dict[Path, float] = {}
        self._ui_mtime: float | None = None
        self._ui_pending: float | None = None
        self._ui_version = 0.0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._history: list[dict[str, Any]] = []
        self._app: Any = None
        self._schedule: Callable[[Callable[[], Any]], Any] | None = None
        self.on_event: Callable[[str, dict], None] | None = None
        self.enabled = True
        self._module_count = 0
        # Son yaması hatalı/eksik kalan modüller: temiz bir yama gelince arayüzdeki uyarı kalksın.
        self._unhealthy: set[str] = set()

    # Yaşam döngüsü
    def start(self, app: Any = None, schedule: Callable[[Callable[[], Any]], Any] | None = None) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._app = app
        self._schedule = schedule
        self.patcher.on_api_change = self._sync_api
        self._scan(initial=True)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="canli-yukleme", daemon=True)
        self._thread.start()
        logger.info("Canlı yükleme izliyor: %d Python dosyası", len(self._mtimes))

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=3)

    def _run(self) -> None:
        while not self._stop.wait(POLL_SECONDS):
            if not self.enabled:
                continue
            try:
                self._scan()
                self._flush()
            except Exception:
                logger.exception("Canlı yükleme taraması patladı")

    # Tarama
    def _files(self):
        for name in WATCH_FILES:
            path = self.base_dir / name
            if path.is_file():
                yield path
        for folder in WATCH_DIRS:
            root = self.base_dir / folder
            if not root.is_dir():
                continue
            for path in root.rglob("*.py"):
                if SKIP_PARTS.intersection(path.parts):
                    continue
                yield path

    def _scan(self, initial: bool = False) -> None:
        now = time.time()
        # Sonradan (tembel) import edilen modüller de tabana alınsın: yoksa ilk değişiklikleri kör kalır.
        late = not initial and len(sys.modules) != self._module_count
        modules = _module_map() if initial or late else {}
        self._module_count = len(sys.modules)
        for path in self._files():
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            old = self._mtimes.get(path)
            self._mtimes[path] = mtime
            if initial:
                module = modules.get(path.resolve())
                if module is not None:
                    try:
                        self.patcher.remember(module.__name__, path.read_text(encoding="utf-8"))
                    except OSError:
                        pass
                continue
            if late:
                module = modules.get(path.resolve())
                if module is not None and not self.patcher.known(module.__name__) and path not in self._pending:
                    try:
                        self.patcher.remember(module.__name__, path.read_text(encoding="utf-8"))
                    except OSError:
                        pass
            if old is not None and mtime != old:
                self._pending[path] = now
        try:
            ui = UI_MARKER.stat().st_mtime if UI_MARKER.parent.is_dir() else None
        except OSError:
            ui = None
        if initial:
            self._ui_mtime = ui
            self._ui_version = ui or 0.0
        elif ui is not None and ui != self._ui_mtime:
            self._ui_mtime = ui
            self._ui_pending = now

    def _flush(self) -> None:
        now = time.time()
        ready = [p for p, t in self._pending.items() if now - t >= SETTLE_SECONDS]
        for path in ready:
            self._pending.pop(path, None)
            self.apply(path)
        if self._ui_pending is not None and now - self._ui_pending >= UI_SETTLE_SECONDS:
            self._ui_pending = None
            if UI_MARKER.is_file():
                self._ui_version = self._ui_mtime or time.time()
                logger.info("Arayüz yeniden derlendi — pencereye yenileme gönderiliyor")
                self._emit("ui_updated", {"version": self._ui_version})

    def apply(self, path: Path) -> PatchResult | None:
        """Bir dosyayı çalışan sürece uygular. Yüklenmemiş modül → None (ilk import'ta zaten yeni hali gelir)."""
        module = _module_for(path)
        if module is None or module.__name__ == SELF_MODULE:
            return None
        with self._lock:
            result = self.patcher.patch(module, path)
        was_unhealthy = result.module in self._unhealthy
        if result.restart or result.error:
            self._unhealthy.add(result.module)
        else:
            self._unhealthy.discard(result.module)
        if result.applied or result.restart or result.error or was_unhealthy:
            self._history.insert(0, result.public())
            del self._history[30:]
            level = logging.WARNING if (result.restart or result.error) else logging.INFO
            logger.log(level, "Canlı yama %s: %s%s%s", result.module, ", ".join(result.applied) or "—",
                       f" | yeniden başlatma: {'; '.join(result.restart)}" if result.restart else "",
                       f" | hata: {result.error}" if result.error else "")
            self._emit("code_reload", result.public())
        return result

    def _sync_api(self, module: types.ModuleType) -> list[str]:
        if self._app is None:
            return []
        if self._schedule is None:
            return sync_routes(self._app, module)
        # Eski FastAPI'de rota listesi kopyalanıyordu: listeyi istekleri eşleştiren asyncio döngüsünde
        # değiştir. 0.140+'da sync_routes yalnız etiketler (FastAPI kendi kilidiyle yeniden kurar).
        done = threading.Event()
        out: list[str] = []

        def run() -> None:
            try:
                out.extend(sync_routes(self._app, module))
            finally:
                done.set()

        self._schedule(run)
        done.wait(5)
        return out

    def _emit(self, event: str, data: dict) -> None:
        if self.on_event:
            try:
                self.on_event(event, data)
            except Exception:
                logger.debug("Canlı yükleme olayı yayınlanamadı", exc_info=True)

    def status(self) -> dict[str, Any]:
        return {
            "running": bool(self._thread and self._thread.is_alive()),
            "enabled": self.enabled,
            "watching": len(self._mtimes),
            "ui_version": self._ui_version,
            "history": list(self._history),
        }


reloader = LiveReloader()
