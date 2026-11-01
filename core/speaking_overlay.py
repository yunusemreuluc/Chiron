"""Tepsideyken konuşma göstergesi.

2026-11-01: asıl gösterge artık `core/tray_indicator.py` — gerçek saydam (per-pixel alpha) pencerede beş stil
(parçacık, kayan kart, imleç, osiloskop, 2D çekirdek), `tray_indicator` ayarıyla seçilir. Önce 3D çekirdek
WebView2 penceresinde denendi; saydamlık alınamadı, köşesi kesik koyu daire oldu, Yunus "çok kötü" dedi —
kaldırıldı. Aşağıdaki Tk ses dalgası `tray_indicator = "dalga"` ile hâlâ seçilebilir.

Kullanıcı isteği (2026-08-01): Chiron tepsiye alındığında pencere görünmüyor,
dolayısıyla konuştuğunu anlamanın hiçbir görsel yolu kalmıyor. Konuşurken sağ
üstte bir dalga çıksın, susunca kapansın.

## Dalga GERÇEK sesten besleniyor

Süslemek için döngüye alınmış bir animasyon değil: çubuklar Chiron'un o an
çaldığı ses parçasının genliğinden geliyor (`main.py._play_audio` içindeki
PCM parçası → `_mic_level` ile RMS). Sustuğunda düzleşiyor, yüksek sesle
konuşurken yükseliyor.

Bu bilinçli bir tercih — [[Bilinen-Tuzaklar]] § Arayüzde dürüstlük: "gerçekten
konuşuyor" diyen bir göstergenin gerçekten sesi göstermesi gerekir. Sahte bir
döngü, bağlantı koptuğunda da neşeyle oynamaya devam ederdi.

## Neden Tkinter — 2026-07-29'da kaldırılmıştı

Tkinter arayüzü (`ui.py`, 3108 satır) bilerek silinmişti: Canvas gerçek
blur/bloom/parçacık üretemediği için orb'u yaklaşık çiziyordu ve CPU'yu tek
çekirdekte ~%100 yakıyordu ([[Home]] § Kaldırılan: Tkinter arayüzü).

Buradaki iş o değil. 14 dikdörtgenin yüksekliğini saniyede 25 kez güncellemek
Canvas'ın zorlanmadan yaptığı bir şey; ölçülen maliyet ihmal edilebilir. Karar
"Tkinter kötüdür" değildi, "shader kalitesinde bir sahneyi Canvas ile taklit
etmek kötüdür"di.

Elenen alternatif: ikinci bir pywebview penceresi. Görsel olarak HUD'un geri
kalanıyla tutarlı olurdu ama küçücük bir gösterge için ayrı bir WebView2
örneği (~50-150 MB) açmak gerekiyordu; Chiron'un bellek profili zaten ~1.25 GB
([[Kurulum-ve-Baslatma]]).

## İş parçacığı kuralı

Tk kendi thread'inde yaşıyor ve Tk nesnelerine SADECE o thread dokunuyor.
Dışarıdan gelen çağrılar (`set_speaking`, `push_level`) kilitli bir duruma
yazıyor; Tk döngüsü onu `after()` ile okuyor. Tkinter iş parçacığı güvenli
değil — widget'lara başka thread'den dokunmak Windows'ta sessiz donmalara yol
açıyor.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque

logger = logging.getLogger("chiron")

# Görünüm
BAR_COUNT = 14
BAR_WIDTH = 4
BAR_GAP = 4
PANEL_W = BAR_COUNT * (BAR_WIDTH + BAR_GAP) + 20
PANEL_H = 46
MARGIN_TOP = 18
MARGIN_RIGHT = 18
FPS = 25

# Renkler — three/palette.ts'teki konuşma paletiyle (PLASMA_TEAL) aynı aile.
# Çekirdek konuşurken turkuaz-yeşile dönüyor; tepsi göstergesi de aynı dili
# konuşsun ki iki yüzey birbirinden kopuk görünmesin.
PANEL_BG = "#0b1a18"
PANEL_EDGE = "#1e3f38"
BAR_COLOR = "#4fd6a8"
BAR_DIM = "#1d4d44"
# Şeffaflık anahtarı: bu renk tamamen saydam çiziliyor. Panelde ya da
# çubuklarda kullanılmayan bir ton olmalı.
TRANSPARENT_KEY = "#ff00fe"

# Ses gelmediğinde çubuklar donmasın diye her karede uygulanan sönme.
DECAY = 0.82

# Yeni göstergeler: ses parçaları arasındaki kısa sessizliklerde sönüp yanmasın — son parçadan bu kadar sonra
# "sustu" sayılır (sönme ayrıca yumuşak). Gemini cümle aralarında ~0.3-0.8 sn boşluk bırakıyor.
HOLD_SECONDS = 0.5
# Evreler (2026-11-01, Yunus: "konuşma başlamadan önce belirsin, konuşsun, sonra biraz daha durup gitsin; beni
# dinlerken de görünsün"). Kullanıcı konuşması giriş transkriptinden anlaşılıyor, ham mikrofon seviyesinden DEĞİL:
# oda gürültüsü göstergeyi boşuna açardı. Seviye yalnız "dinliyor" evresinde dalgalanma için kullanılıyor.
USER_HOLD_SECONDS = 1.2      # son transkript parçasından sonra hâlâ "dinliyor"
THINK_MAX_SECONDS = 12.0     # kullanıcı sustu, cevap gelmedi: en fazla bu kadar "düşünüyor"
TOOL_HOLD_SECONDS = 4.0      # araç çalıştı: bu kadar "düşünüyor"
LINGER_SECONDS = 3.0         # konuşma bittikten sonra kalış
# Altyazı: bu kadar süre yeni metin gelmezse sıradaki konuşma yeni bir cümle başlatır.
CAPTION_RESET_SECONDS = 3.0
# Stil ayarı her karede dosyadan okunmasın.
STYLE_REFRESH_SECONDS = 2.0


class SpeakingOverlay:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._enabled = False        # tepside mi
        self._speaking = False       # şu an konuşuyor mu
        self._level = 0.0            # en son ses seviyesi (0..1)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_spoke = 0.0
        self._caption = ""
        self._caption_at = 0.0
        self._mic = 0.0
        self._user_at = 0.0
        self._tool_at = 0.0
        self._style = ""
        self._style_at = 0.0

    # ── Dışarıdan çağrılanlar (herhangi bir thread'den güvenli) ────────────

    def set_enabled(self, enabled: bool) -> None:
        """Tepsiye alındı/geri getirildi. Yalnızca tepsideyken gösteriliyor —
        pencere açıkken zaten 3D sahnedeki çekirdek konuşmayı gösteriyor."""
        with self._lock:
            self._enabled = enabled
        if enabled:
            self._ensure_thread()

    def set_speaking(self, speaking: bool) -> None:
        with self._lock:
            self._speaking = speaking
            if speaking:
                self._last_spoke = time.monotonic()
            else:
                self._level = 0.0

    def push_mic(self, level: float) -> None:
        """Mikrofon seviyesi (main.py dinleme döngüsü) — yalnız "dinliyor" evresinde dalgalanma."""
        self._mic = max(0.0, min(1.0, float(level)))

    def mark_user(self) -> None:
        """Kullanıcı konuşuyor (giriş transkripti geldi)."""
        with self._lock:
            self._user_at = time.monotonic()

    def mark_thinking(self) -> None:
        """Bir araç çalışmaya başladı — cevap gecikecek, "düşünüyor" göster."""
        with self._lock:
            self._tool_at = time.monotonic()

    def _phase(self) -> tuple[str, float]:
        """(evre, seviye) — kilit ALTINDA çağrılır. Bkz. core/tray_indicator.run."""
        now = time.monotonic()
        if self._speaking or now - self._last_spoke < HOLD_SECONDS:
            return "konusuyor", self._level
        if now - self._user_at < USER_HOLD_SECONDS:
            return "dinliyor", self._mic
        if (self._user_at > self._last_spoke and now - self._user_at < THINK_MAX_SECONDS)                 or now - self._tool_at < TOOL_HOLD_SECONDS:
            return "dusunuyor", 0.0
        if self._last_spoke and now - self._last_spoke < LINGER_SECONDS:
            return "bitti", 0.0
        return "", 0.0

    def push_caption(self, text: str) -> None:
        """Chiron'un o an söylediği metin (çıkış transkripti, main.py) — kayan kart bunu gösterir."""
        text = " ".join(str(text or "").split())
        if not text:
            return
        now = time.monotonic()
        with self._lock:
            if now - self._caption_at > CAPTION_RESET_SECONDS:
                self._caption = ""
            self._caption = f"{self._caption} {text}".strip()[-400:]
            self._caption_at = now

    def _style_name(self) -> str:
        now = time.monotonic()
        if now - self._style_at > STYLE_REFRESH_SECONDS or not self._style:
            try:
                from app_config import get_app_config_value

                self._style = str(get_app_config_value("tray_indicator", "") or "")
            except Exception:
                self._style = ""
            from core import tray_indicator

            if self._style not in tray_indicator.STYLES and self._style != "dalga":
                self._style = tray_indicator.DEFAULT_STYLE
            self._style_at = now
        return self._style

    def push_level(self, level: float) -> None:
        with self._lock:
            self._level = max(0.0, min(1.0, float(level)))

    def shutdown(self) -> None:
        self._stop.set()

    # ── Tk tarafı ───────────────────────────────────────────────────────────

    def _ensure_thread(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run if self._style_name() == "dalga" else self._run_indicator,
            name="chiron-speaking-overlay", daemon=True,
        )
        self._thread.start()

    def _run_indicator(self) -> None:
        """core/tray_indicator.py döngüsü; tepsiden çıkınca (enabled=False) biter."""
        from core import tray_indicator

        def state() -> tuple[bool, str, float, str]:
            with self._lock:
                phase, level = self._phase()
                self._level *= 0.85  # yeni parça gelmezse sön
                return self._enabled, phase, level, self._caption

        try:
            tray_indicator.run(state, self._style_name, lambda: self._stop.is_set() or not self._enabled)
        except Exception:
            logger.exception("[CHIRON] Tepsi göstergesi çöktü")

    def _run(self) -> None:
        try:
            import tkinter as tk
        except Exception:
            logger.warning("[CHIRON] Tkinter yok, konuşma göstergesi devre dışı")
            return

        try:
            root = tk.Tk()
            root.overrideredirect(True)          # başlık çubuğu yok
            root.attributes("-topmost", True)    # her şeyin üstünde
            root.configure(bg=TRANSPARENT_KEY)
            try:
                root.attributes("-transparentcolor", TRANSPARENT_KEY)
            except Exception:
                # Şeffaflık desteklenmiyorsa panel opak kalır — gösterge yine
                # çalışır, sadece dikdörtgen kenarı görünür. Sessizce vazgeçme.
                logger.info("[CHIRON] Şeffaf kaplama desteklenmiyor, opak devam")

            ekran_w = root.winfo_screenwidth()
            x = ekran_w - PANEL_W - MARGIN_RIGHT
            root.geometry(f"{PANEL_W}x{PANEL_H}+{x}+{MARGIN_TOP}")

            canvas = tk.Canvas(
                root, width=PANEL_W, height=PANEL_H,
                bg=TRANSPARENT_KEY, highlightthickness=0,
            )
            canvas.pack()

            # Geçmiş: en yeni sağda. Kaydırmalı dalga görüntüsü bundan çıkıyor —
            # sabit bir ekolayzer değil, gerçekten "az önce ne söyledi"nin izi.
            gecmis: deque[float] = deque([0.0] * BAR_COUNT, maxlen=BAR_COUNT)
            gorunur = False
            root.withdraw()

            def yuvarlak_panel(x1, y1, x2, y2, r, fill, outline="") -> None:
                """Yuvarlatılmış dikdörtgen — Canvas'ta yerleşik karşılığı yok.

                Köşe noktaları iki kez tekrarlanıp `smooth=True` verilince Tk
                aradaki eğriyi kendisi çiziyor. Keskin köşeli bir kutu
                masaüstünde 'sistem uyarısı' gibi duruyordu; Chiron'un geri
                kalanı yuvarlak (bkz. Notes/Tasarim-Kurallari.md § Arayüz stili).
                """
                noktalar = [
                    x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
                    x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
                    x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
                ]
                canvas.create_polygon(
                    noktalar, fill=fill, outline=outline, smooth=True
                )

            def cizim() -> None:
                canvas.delete("all")
                # Dış hat çok kısık: panelin açık bir masaüstünde kaybolmaması
                # için kenar gerekiyor ama belirgin bir çerçeve dikkat çekerdi.
                yuvarlak_panel(0, 0, PANEL_W - 1, PANEL_H - 1, 14, PANEL_BG, PANEL_EDGE)
                orta = PANEL_H / 2
                for i, seviye in enumerate(gecmis):
                    bx = 10 + i * (BAR_WIDTH + BAR_GAP)
                    # Taban yükseklik: sessizken bile ince bir çizgi kalsın,
                    # yoksa gösterge "kapandı" gibi görünüyor.
                    h = 2 + seviye * (PANEL_H - 14)
                    canvas.create_rectangle(
                        bx, orta - h / 2, bx + BAR_WIDTH, orta + h / 2,
                        fill=BAR_COLOR if seviye > 0.04 else BAR_DIM, outline="",
                    )

            def tick() -> None:
                nonlocal gorunur
                if self._stop.is_set():
                    try:
                        root.destroy()
                    except Exception:
                        pass
                    return

                with self._lock:
                    goster = self._enabled and self._speaking
                    seviye = self._level
                    self._level *= DECAY  # yeni parça gelmezse sön

                if goster != gorunur:
                    gorunur = goster
                    if goster:
                        root.deiconify()
                        root.attributes("-topmost", True)
                    else:
                        root.withdraw()
                        gecmis.extend([0.0] * BAR_COUNT)

                if gorunur:
                    gecmis.append(seviye)
                    cizim()

                root.after(int(1000 / FPS), tick)

            root.after(0, tick)
            root.mainloop()
        except Exception:
            logger.exception("[CHIRON] Konuşma göstergesi çöktü")


# Tek örnek: hem ses döngüsü (main.py) hem tepsi (desktop.py) buna dokunuyor.
# Ayrı ayrı örneklenselerdi biri diğerinin durumunu göremezdi.
overlay = SpeakingOverlay()
