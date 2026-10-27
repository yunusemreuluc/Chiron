#!/usr/bin/env python3
"""
Chiron uygulama ikonu — prosedürel üretim.

KOMPOZİSYON: sıcak plazma çekirdeği + etrafında segmentli yörünge halkaları +
halka üzerinde düğüm noktaları. Yani 3D sahnenin (Energy Core + OrbitNodes)
tepeden görünüşü.

Halkalar bilerek ÖNE DÖNÜK (tam daire), eğik değil: eğik tek halka + opak küre
kombinasyonu kaçınılmaz olarak "Satürn" gibi okunuyor — bir yapay zekâ
çekirdeği gibi değil. Öne dönük eş merkezli halkalar ise reaktör/diyafram
dilini konuşuyor ve 16px'te de ayakta kalıyor.

NEDEN KOD, NEDEN TEK BİR ÇİZİM DEĞİL: ikon 16px'ten 256px'e kadar on ayrı
boyutta görünüyor (görev çubuğu, pencere başlığı, masaüstü kısayolu, Alt-Tab,
sistem tepsisi). Tek bir büyük görseli küçültmek 16px'te lapa üretir — orada
ince dış halka tek piksellik gri bir bulaşmaya dönüşür. Bu yüzden İKİ AYRI
kompozisyon var (bkz. `_render` içindeki `detailed`):

  büyük (40-256px)  çekirdek + iki halka + üç düğüm, ince hatlar
  küçük (16-32px)   büyük çekirdek + TEK kalın halka, düğüm yok

Palet app/globals.css ile birebir aynı; ikon arayüzün devamı gibi okunmalı,
ayrı bir marka gibi değil. Çekirdeğin gövde gradyanı + platin fresnel kenarı
3D sahnedeki Energy Core'un (three/shaders/energyCore.ts) iki boyutlu özeti.

Çalıştırma:  venv\\Scripts\\python.exe make_icon.py
Çıktı:       Icon/chiron.ico          — pencere, görev çubuğu, kısayol
             Icon/chiron.png          — 256px, genel kullanım
             Icon/chiron-tray.png     — 32px, sistem tepsisi (küçük varyant)
             frontend/app/favicon.ico — tarayıcı geliştirme modunda aynı ikon
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent
ICON_DIR = BASE_DIR / "Icon"
FAVICON_PATH = BASE_DIR / "frontend" / "app" / "favicon.ico"

# ── Palet — app/globals.css ─────────────────────────────────────────────────
PLATE_INNER = "#0a1322"  # plakanın merkezi: mavimsi siyah
PLATE_OUTER = "#02040a"  # plakanın kenarı: neredeyse saf siyah
ORB_CORE = "#f4f8ff"  # çekirdeğin en parlak noktası
ORB_MID = "#6aa6ff"  # --color-primary (buz mavisi)
ORB_DEEP = "#14336b"  # --color-primary-deep'in koyusu — gölgede kalan yarı
PLATINUM = "#e8eef7"  # --color-cyan (platin) — fresnel kenarı ve halkalar
GLOW = "#7fb2ff"  # ışıma rengi = birincil vurgu

# ── Ölçüler ─────────────────────────────────────────────────────────────────
# Hepsi ikonun YARIM genişliğine (1.0) göre normalize. Piksel karşılığı:
# kalınlık_px ≈ 2 * W * (boyut / 2). Küçük varyantın halkası bu yüzden çok daha
# kalın: 16px'te W=0.030 yarım pikselden ince kalırdı, yani görünmezdi.
PLATE_RADIUS = 0.86

CORE_RADIUS_LARGE = 0.235
CORE_RADIUS_SMALL = 0.285

# (yarıçap, gauss yarı-genişliği, parlaklık) — dış halka plakanın kenarına
# yakın duruyor: aralarında geniş bir ölü boşluk kalırsa kompozisyon
# "ortada küçük bir şey" gibi çekingen görünüyor.
RINGS_LARGE = ((0.545, 0.030, 0.95), (0.748, 0.021, 0.55))
RINGS_SMALL = ((0.585, 0.098, 0.95),)

# Halkalardaki boşluklar (merkez açı°, yarı genişlik°) — kesintisiz bir daire
# "logo" gibi duruyor; boşluklar onu dönen bir mekanizmaya çeviriyor. Her halkanın
# boşlukları farklı yerde: hizalanırsa tek bir kesik gibi okunur.
GAPS_RING_1 = ((58.0, 15.0), (196.0, 11.0), (300.0, 8.0))
GAPS_RING_2 = ((132.0, 22.0), (268.0, 16.0))
GAPS_SMALL = ((64.0, 17.0), (244.0, 17.0))

# Düğümler: birinci halka üzerinde, boşluklara denk GELMEYEN açılar.
NODE_ANGLES_DEG = (118.0, 250.0, 18.0)
NODE_RADIUS = 0.050

# Işık yönü — sol üst. Küredeki terminatör (aydınlık/karanlık sınırı) bu
# noktadan çıkıyor; DAR tutulması kritik: geniş bırakılırsa kürenin tamamı
# aydınlanıp soluk bir bilye gibi görünüyor, enerji çekirdeği gibi değil.
LIGHT_OFFSET = (-0.24, 0.28)
LIGHT_SPREAD = 1.06

# Boyut listesi: Windows'un istediği tüm kademeler. 20/40/96 yüksek DPI
# (%125/%150/%200 ölçekleme) için — atlanırsa Windows aradaki boyutu kendisi
# üretir ve sonuç bulanık olur.
SMALL_SIZES = (16, 20, 24, 32)
LARGE_SIZES = (40, 48, 64, 96, 128, 256)

# Supersampling: her varyant yüksek çözünürlükte bir kez çizilip her hedef
# boyuta LANCZOS ile indiriliyor — piksel ızgarasında kenar kırılması olmasın.
MASTER_SMALL = 512
MASTER_LARGE = 1024


def _rgb(hex_color: str) -> np.ndarray:
    value = hex_color.lstrip("#")
    return np.array([int(value[i : i + 2], 16) for i in (0, 2, 4)], dtype=np.float64) / 255.0


def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _over(
    dst_rgb: np.ndarray, dst_a: np.ndarray, src_rgb: np.ndarray, src_a: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Standart "source over" — düz (premultiplied olmayan) alfa."""
    out_a = src_a + dst_a * (1.0 - src_a)
    divisor = np.where(out_a > 1e-6, out_a, 1.0)[..., None]
    sa, da = src_a[..., None], dst_a[..., None]
    out_rgb = (src_rgb * sa + dst_rgb * da * (1.0 - sa)) / divisor
    return out_rgb, out_a


def _add_glow(
    rgb: np.ndarray, alpha: np.ndarray, color: np.ndarray, amount: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Toplamalı ışıma: bloom ışık EKLER, altındakini örtmez."""
    return (
        np.clip(rgb + color * amount[..., None], 0.0, 1.0),
        np.clip(np.maximum(alpha, amount), 0.0, 1.0),
    )


def _plasma_noise(pixels: int, seed: int = 7) -> np.ndarray:
    """Çekirdeğin yüzeyi için iki oktavlı yumuşak gürültü, [-1, 1].

    3D shader'daki `vNoise`in (simplex) ikondaki karşılığı: gövde rengini
    hafifçe dalgalandırıyor. Bu olmadan küre düzgün bir gradyan, yani plastik
    bir bilye gibi görünüyor — plazma değil. Kaba ızgara BICUBIC ile
    büyütülerek yumuşatılıyor; ikon için gerçek simplex'e gerek yok.

    Sabit tohum: ikon her üretimde birebir aynı çıkmalı (git diff'i gürültüyle
    dolmasın).
    """
    rng = np.random.default_rng(seed)
    total = np.zeros((pixels, pixels))
    for cells, weight in ((6, 0.65), (13, 0.35)):
        coarse = (rng.random((cells, cells)) * 255).astype(np.uint8)
        smooth = Image.fromarray(coarse, mode="L").resize((pixels, pixels), Image.BICUBIC)
        total += np.asarray(smooth, dtype=np.float64) / 255.0 * weight
    return total * 2.0 - 1.0


def _gap_gate(angle: np.ndarray, gaps: tuple[tuple[float, float], ...]) -> np.ndarray:
    """Verilen açılarda halkayı kesen yumuşak kenarlı boşluk maskesi."""
    gate = np.ones_like(angle)
    for center_deg, half_deg in gaps:
        center, half = np.radians(center_deg), np.radians(half_deg)
        # En kısa açısal mesafe (±π sarmasını doğru hesaplar).
        distance = np.abs(((angle - center + np.pi) % (2.0 * np.pi)) - np.pi)
        gate *= _smoothstep(half * 0.55, half, distance)
    return gate


def _render(pixels: int, *, detailed: bool) -> Image.Image:
    lin = (np.arange(pixels) + 0.5) / pixels * 2.0 - 1.0
    x, y = np.meshgrid(lin, -lin)  # y yukarı
    r = np.sqrt(x * x + y * y)
    angle = np.arctan2(y, x)
    aa = 2.4 / pixels  # kenar yumuşatma bandı ≈ 2 piksel

    rgb = np.zeros((pixels, pixels, 3))
    alpha = np.zeros((pixels, pixels))

    # ── Dış hale ────────────────────────────────────────────────────────────
    # Plakanın hemen dışında sönen mavi ışık. Görev çubuğunda ikonun "canlı"
    # görünmesinin tek kaynağı bu — kenarı zemine bağlıyor, kesik durmuyor.
    halo = np.where(r > PLATE_RADIUS, np.exp(-(((r - PLATE_RADIUS) / 0.13) ** 2)) * 0.30, 0.0)
    rgb, alpha = _over(rgb, alpha, _rgb(GLOW), halo)

    # ── Plaka ───────────────────────────────────────────────────────────────
    # Merkezi hafif mavi, kenarı siyaha düşen disk. `- y * 0.10` üst yarıyı bir
    # tık aydınlatıyor: tek ışık kaynağı hissi buradan başlıyor.
    plate = _smoothstep(PLATE_RADIUS + aa, PLATE_RADIUS - aa, r)
    depth = np.clip(r / PLATE_RADIUS * 0.92 - y * 0.10, 0.0, 1.0)[..., None]
    plate_rgb = _rgb(PLATE_INNER) * (1.0 - depth) + _rgb(PLATE_OUTER) * depth
    rgb, alpha = _over(rgb, alpha, plate_rgb, plate)

    # ── Plakanın kenar hattı ────────────────────────────────────────────────
    # Işığı yakalayan ince platin hat: sol üstte parlak, sağ altta sönük.
    # (globals.css'teki --shadow-inset-top'un ikondaki karşılığı.)
    edge = np.exp(-(((r - PLATE_RADIUS) / (aa * 1.6)) ** 2))
    facing = np.clip((-x * 0.45 + y * 0.89) * 0.5 + 0.5, 0.0, 1.0)
    rgb, alpha = _over(rgb, alpha, _rgb(PLATINUM), edge * (0.20 + 0.75 * facing) * plate)

    # ── Yörünge halkaları ───────────────────────────────────────────────────
    # Parlaklık çevre boyunca değişiyor (`facing`): tek ışık kaynağı altında
    # duran fiziksel bir hat gibi, düz çizilmiş bir daire gibi değil.
    rings = RINGS_LARGE if detailed else RINGS_SMALL
    gap_sets = (GAPS_RING_1, GAPS_RING_2) if detailed else (GAPS_SMALL,)
    for (radius, width, strength), gaps in zip(rings, gap_sets):
        band = np.exp(-(((r - radius) / width) ** 2))
        lighting = 0.45 + 0.55 * facing
        rgb, alpha = _over(
            rgb, alpha, _rgb(PLATINUM), band * _gap_gate(angle, gaps) * strength * lighting * plate
        )
        # Halkanın kendi ışıması — hattın etrafına sızan hafif mavi.
        rgb, alpha = _add_glow(
            rgb, alpha, _rgb(GLOW), np.exp(-(((r - radius) / (width * 3.2)) ** 2)) * 0.14 * plate
        )

    # ── Düğümler ────────────────────────────────────────────────────────────
    if detailed:
        ring_radius = RINGS_LARGE[0][0]
        for angle_deg in NODE_ANGLES_DEG:
            theta = np.radians(angle_deg)
            node_x, node_y = ring_radius * np.cos(theta), ring_radius * np.sin(theta)
            to_node = np.sqrt((x - node_x) ** 2 + (y - node_y) ** 2)
            rgb, alpha = _add_glow(
                rgb, alpha, _rgb(GLOW), np.exp(-((to_node / (NODE_RADIUS * 2.1)) ** 2)) * 0.34 * plate
            )
            rgb, alpha = _over(
                rgb,
                alpha,
                _rgb(ORB_CORE),
                _smoothstep(NODE_RADIUS + aa, NODE_RADIUS - aa, to_node) * plate,
            )

    # ── Çekirdek ────────────────────────────────────────────────────────────
    # 3D Energy Core'un iki boyutlu özeti: içten ışıyan gövde gradyanı +
    # gövdeden keskince ayrılan platin fresnel kenarı. En son çiziliyor —
    # halkaların iç kenarı çekirdeğin ARKASINDA kalsın diye.
    core_radius = CORE_RADIUS_LARGE if detailed else CORE_RADIUS_SMALL
    core = _smoothstep(core_radius + aa, core_radius - aa, r)
    light_x, light_y = LIGHT_OFFSET[0] * core_radius, LIGHT_OFFSET[1] * core_radius
    falloff = np.clip(
        np.sqrt((x - light_x) ** 2 + (y - light_y) ** 2) / (core_radius * LIGHT_SPREAD), 0.0, 1.0
    )
    # Gürültü terminatörü dalgalandırıyor — sınır matematiksel bir daire değil,
    # akan bir plazma kenarı gibi kırılıyor.
    lit = np.clip(1.0 - falloff + _plasma_noise(pixels) * 0.09, 0.0, 1.0)
    body = _rgb(ORB_DEEP) + (_rgb(ORB_MID) - _rgb(ORB_DEEP)) * (lit**0.7)[..., None]
    # Sıcak merkez bilerek DAR (yüksek üs): geniş bırakılırsa küre beyaza doyup
    # hacmini kaybediyor. Üs düştükçe merkez büyür ve söner.
    body += (_rgb(ORB_CORE) - body) * (lit**3.6)[..., None]
    # Fresnel: keskin ve DAR bir silüet hattı (üs yüksek), gövdeyi yıkayan geniş
    # bir yıkama değil — 3D shader'da da kenar gövdeden keskince ayrılıyor.
    fresnel = (np.clip(r / core_radius, 0.0, 1.0) ** 6.0 * 0.62)[..., None]
    body += (_rgb(PLATINUM) - body) * fresnel
    rgb, alpha = _over(rgb, alpha, body, core)

    # Çekirdeğin bloom'u — kenarında yoğunlaşıp dışa sönen ışık. Küçük varyantta
    # daha geniş: 16px'te ışıma, ayrıntıdan çok daha iyi okunuyor.
    bloom = np.exp(-(((r - core_radius) / (0.17 if detailed else 0.21)) ** 2))
    rgb, alpha = _add_glow(rgb, alpha, _rgb(GLOW), bloom * (0.46 if detailed else 0.54) * plate)

    rgba = np.concatenate([rgb, alpha[..., None]], axis=-1)
    return Image.fromarray(np.clip(rgba * 255.0 + 0.5, 0, 255).astype(np.uint8), mode="RGBA")


def build() -> Path:
    """Tüm ikon dosyalarını üretir; .ico yolunu döndürür."""
    small_master = _render(MASTER_SMALL, detailed=False)
    large_master = _render(MASTER_LARGE, detailed=True)

    frames = {size: small_master.resize((size, size), Image.LANCZOS) for size in SMALL_SIZES}
    frames.update({size: large_master.resize((size, size), Image.LANCZOS) for size in LARGE_SIZES})

    ICON_DIR.mkdir(parents=True, exist_ok=True)
    ico_path = ICON_DIR / "chiron.ico"

    # Pillow'un ICO yazıcısı `append_images` içinde TAM boyut eşleşmesi arıyor;
    # eşleşen bulunca kendisi küçültmüyor, verdiğimiz kareyi olduğu gibi gömüyor.
    # Küçük/büyük varyant ayrımı bu sayede .ico'nun içine kadar korunuyor.
    ordered = sorted(frames)
    frames[256].save(
        ico_path,
        format="ICO",
        sizes=[(size, size) for size in ordered],
        append_images=[frames[size] for size in ordered if size != 256],
    )

    frames[256].save(ICON_DIR / "chiron.png")
    # Sistem tepsisi ikonu 16-24px arasında çiziliyor (bkz. desktop.py
    # TrayController) — oraya büyük kompozisyonun ezilmiş hâli değil, küçük
    # varyantın 32'liği gidiyor.
    frames[32].save(ICON_DIR / "chiron-tray.png")

    if FAVICON_PATH.parent.is_dir():
        shutil.copyfile(ico_path, FAVICON_PATH)

    if REMOTE_ICON_DIR.parent.is_dir():
        _build_remote_icons(large_master)

    return ico_path


# Telefon arayüzünün ana ekran ikonları (2026-09-15, bkz. frontend/app/m ve
# Notes/Uzaktan-Erisim.md). Şeffaf değil, zemin rengine basılı: iOS şeffaf
# ikonu siyaha, bazı Android başlatıcıları beyaza boyuyor. "maskable" varyantta
# çizim küçük tutuluyor — başlatıcı ikonu daireye/damlaya kırpıyor ve güvenli
# alan ortadaki %80.
REMOTE_ICON_DIR = BASE_DIR / "frontend" / "public" / "m" / "icons"
REMOTE_BACKGROUND = (5, 7, 12, 255)  # globals.css --background


def _build_remote_icons(master: Image.Image) -> None:
    REMOTE_ICON_DIR.mkdir(parents=True, exist_ok=True)

    def on_background(size: int, scale: float) -> Image.Image:
        canvas = Image.new("RGBA", (size, size), REMOTE_BACKGROUND)
        inner = int(size * scale)
        offset = (size - inner) // 2
        canvas.alpha_composite(master.resize((inner, inner), Image.LANCZOS), (offset, offset))
        return canvas

    on_background(192, 0.92).save(REMOTE_ICON_DIR / "chiron-192.png")
    on_background(512, 0.92).save(REMOTE_ICON_DIR / "chiron-512.png")
    on_background(512, 0.66).save(REMOTE_ICON_DIR / "chiron-maskable-512.png")
    on_background(180, 0.86).convert("RGB").save(REMOTE_ICON_DIR / "apple-touch-icon.png")


if __name__ == "__main__":
    path = build()
    print(f"İkon üretildi: {path}")
    print(f"Boyutlar: {', '.join(str(size) for size in sorted((*SMALL_SIZES, *LARGE_SIZES)))}")
