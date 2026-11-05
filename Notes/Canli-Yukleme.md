# Canlı yükleme

2026-11-04, kullanıcı isteği: "yeniden başlatmaya gerek kalmadan değişiklikler çalışma anında uygulansın".
Kod: `backend/core/canli_yukleme.py`, durum `GET /api/canli`, arayüz `components/canli/CanliYukleme.tsx`.

## Neden yamalama, neden `--reload` değil

Chiron tek süreç: WebView + FastAPI + ses döngüsü + Claude iş alt süreçleri. `uvicorn --reload` ve
`importlib.reload` ikisi de durumu yeniden kurar: süren Claude işleri, sesli oturum, pano singleton'u,
kilitler gider ya da ikinci kopyası doğar. Bu yüzden modül yeniden yüklenmez, **yamalanır**:

- Fonksiyon/metot → eski nesnenin `__code__`'u değişir. Nesne aynı kalır: `from x import f` yapanlar,
  `@register_tool` kaydı, FastAPI rotası, thread hedefi hepsi yeni kodu çalıştırır.
- Yeni fonksiyon/sınıf/import/sabit eklenir. Yeni rota FastAPI 0.140'ta kendiliğinden görünür
  (`include_router` alt router'ı referansla tutuyor); eski sürümde "/" mount'undan önce takılır.
- Modül gövdesi yeniden çalıştırılmaz; yalnız değişen satırlar uygulanır.
- Arayüz: `frontend/out/index.html` değişince `ui_updated` olayı gider, sayfa yenilenir. Açık pencere
  (`role="dialog"`) ya da içi dolu bir `textarea` varsa bekler, "Şimdi yenile" sunar. Olay kaçarsa
  30 sn'de bir `/api/canli`'daki `ui_version`'a bakar.

İzlenen yerler: `backend/`, `actions/`, `core/`, `tool_defs.py`, `main.py`, `app_config.py`
(`tests/` hariç). Saniyede bir mtime taraması, dosya 0,6 sn durulunca uygulanır.

## Ne yeniden başlatma ister (bildirimde kehribar)

Bunlar sessizce yutulmaz, `restart` listesinde nedeniyle gelir:

- FastAPI uç noktasının imzası (parametre, tip, sync↔async). FastAPI bunu kayıtta okur.
- Dekoratör değişikliği (rota yolu, araç adı). Gövde yamalanır, kayıt eski kalır.
- Durum nesnesi: `x = Sinif()` değişirse sağ taraf **çalıştırılmaz** (ikinci istemci/pano kurulmasın).
- Çalışma anında dolan kap (`_REGISTRY = {}` gibi): yalnız iki taraf düz literal ve mevcut değer eski
  literale eşitse yerinde güncellenir, yoksa dokunulmaz (kayıt defteri silinmesin).
- Sınıf alanları (@dataclass/pydantic), sınıf dekoratörü/tabanı, modül gövdesindeki if/try/çağrı.
- `functools.wraps` kullanmayan bir dekoratörle sarılmış fonksiyon. Sarmalayıcıyı düşürmektense dokunulmaz.
- Silinen ya da yeniden adlandırılan tanım bellekte durur (eski rota/araç ilk eşleşme olarak kalır).
- tool_defs'in Gemini Live bildirimi yeni sesli oturumda geçerli olur.

## Tuzaklar (ölçüldü)

- **Bayt kod karşılaştırması işe yaramaz.** 3.11'de .pyc'den ve AST'den derlenen kod birebir aynı
  çıkmıyor. Değişmemiş 81 modülün 70'i "değişti" göründü. Karar AST tabanıyla verilir, taban son
  başarılı kaynağın ağacıdır.
- **`__future__` bayrakları parça derlemeye geçmez.** `compile(..., flags=..., dont_inherit=True)` ile
  taşınmazsa `from __future__ import annotations` atlanır, tip ipuçları hemen değerlendirilir.
- **Argümansız `super()`.** Geçici sınıfta derlenen metodun `__class__` hücresi gerçek sınıfa yeniden
  bağlanır (`_rebind_closure`), yoksa "obj must be an instance" hatası verir.
- **Uygulanamayan tanımın tabanı eski kalır.** Sonraki kayıtta yeniden denenir, değişiklik kaybolmaz.
- **Tabanı olmayan modül.** İzleyici onu ilk kez görüyorsa değişiklik uygulanmaz, yalnız taban
  kaydedilir. Tembel import edilen modüller her taramada tabana alınır.
- Bir dosyanın yamaları atomik değil: birkaç ms boyunca `f` yeni, `g` eski olabilir.

## Doğrulama

`tests/test_canli_yukleme.py` (19 test). Gerçek uygulamada uçtan uca denendi: `pano` singleton'una yeni
metot eklendi (aynı örnek, durum korundu), `backend/api/canli.py`'ye yeni uç eklendi ve TestClient ile
cevap verdi. Bütün yüklü modüller kendi kaynağıyla yamalandığında 81'de 0 değişiklik (yanlış alarm yok).

İlk kurulum bir kez yeniden başlatma ister: izleyici, Chiron açılırken lifespan'de başlıyor.
