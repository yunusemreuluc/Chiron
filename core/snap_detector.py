"""Parmak şıklatma algılayıcısı (2026-11-01, kullanıcı isteği).

Çift şıklatma İnsan görünümünü (frontend/three/HumanoidBust.tsx) açıp kapatıyor.
Model yok, eğitim yok: şıklatma sinyal olarak çok belirgin bir şey.

Bir şıklatmanın imzası — konuşmadan ve masa vuruşundan ayıran üç şey:
  1. ANİ ATAK: enerji bir iki çerçevede (8 ms) gürültü tabanının ~15 dB üstüne çıkar.
     Konuşmanın hecesi 30-60 ms'de yükselir.
  2. TİZ: enerji 1-5 kHz'de. Ardışık örnek farkının enerjisi / sinyal enerjisi
     ("hf oranı") şıklatmada yüksek, masaya vuruşta (gümbürtü) düşük.
  3. KISA: ~50 ms içinde tepe değerin %10'unun altına söner ve ardından yeniden
     yükselmez. Konuşmadaki patlamalı ünsüz (p, t, k) hemen ardından bir ünlüyle
     yeniden yükseldiği için burada elenir.

Tek şıklatma yanlış tetiklemeye fazla açık (klavye, kapı, alkış), bu yüzden
varsayılan İKİ şıklatma: 120-800 ms arayla. Alkış da aynı imzayı taşır; iki
alkış da modu açar — bu bilinçli olarak kabul edildi.

Akış 16 kHz int16 mono bekliyor (main.py'nin Gemini'ye gönderdiği tampon).
Saf numpy, çerçeve başına birkaç vektör işlemi: ses döngüsünü yavaşlatmaz.
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

FRAME = 128  # 8 ms @ 16 kHz

# Eşikler enerji (ortalama kare, int16 ölçeğinde) cinsinden.
ONSET_OVER_FLOOR = 30.0  # ~15 dB gürültü tabanının üstü
ATTACK_RATIO = 8.0  # iki çerçeve önceye göre ~9 dB sıçrama
ABS_MIN_ENERGY = 3.0e5  # RMS ≈ 550 — uzaktaki tıkırtılar sayılmasın
HF_MIN = 0.35  # 2 kHz sinüs ≈ 0.59, 300 Hz ≈ 0.03, beyaz gürültü ≈ 2
FLOOR_MIN = 400.0  # sessiz odada tabanın çökmesini önler (RMS 20)

DECAY_FRAMES = 7  # ~56 ms içinde sönmüş olmalı
DECAY_RATIO = 0.10
RERISE_RATIO = 0.30  # sönümden sonra bunun üstüne çıkmak = konuşma
CONFIRM_FRAMES = 14  # ~112 ms sessizlikle onaylanır

PAIR_MIN_S = 0.12
PAIR_MAX_S = 0.80
COOLDOWN_S = 1.2


class SnapDetector:
    """`feed()` her ses tamponunda çağrılır; istenen sayıda şıklatma tamamlanınca True döner."""

    def __init__(self, sample_rate: int = 16000, required: int = 2) -> None:
        self.sample_rate = sample_rate
        self.required = max(1, int(required))
        self._frame_s = FRAME / sample_rate
        self._pending = np.empty(0, dtype=np.int16)
        self._floor = 1.0e4
        self._history = [self._floor, self._floor]  # iki önceki, bir önceki
        self._candidate: dict | None = None
        self._snaps: list[float] = []
        self._cooldown_until = 0.0
        self._t = 0.0  # akış zamanı (s) — duvar saati değil, test edilebilir olsun

    def reset(self) -> None:
        self._candidate = None
        self._snaps.clear()

    def feed(self, data: bytes) -> bool:
        samples = np.frombuffer(data, dtype=np.int16)
        if self._pending.size:
            samples = np.concatenate((self._pending, samples))
        whole = samples.size - samples.size % FRAME
        self._pending = samples[whole:].copy()
        fired = False
        for start in range(0, whole, FRAME):
            if self._process(samples[start:start + FRAME]):
                fired = True
        return fired

    # ── çerçeve ────────────────────────────────────────────────────────────
    def _process(self, frame: np.ndarray) -> bool:
        x = frame.astype(np.float32)
        energy = float(np.mean(x * x)) + 1.0
        diff = np.diff(x)
        hf = float(np.mean(diff * diff)) / energy
        self._t += self._frame_s
        fired = False

        cand = self._candidate
        if cand is not None:
            cand["age"] += 1
            age = cand["age"]
            # Tepe bazen atağın bir sonraki çerçevesine düşer.
            if age <= 1 and energy > cand["peak"]:
                cand["peak"] = energy
                cand["hf"] = max(cand["hf"], hf)
            elif not cand["decayed"]:
                if energy < cand["peak"] * DECAY_RATIO:
                    cand["decayed"] = True
                elif age >= DECAY_FRAMES:
                    self._reject("sönmedi", cand)
            elif energy > cand["peak"] * RERISE_RATIO:
                self._reject("yeniden yükseldi", cand)
            if self._candidate is not None and age >= CONFIRM_FRAMES:
                self._candidate = None
                fired = self._register(cand["t"])
        else:
            prior = min(self._history)
            if (
                energy > max(self._floor * ONSET_OVER_FLOOR, ABS_MIN_ENERGY)
                and energy > prior * ATTACK_RATIO
                and hf > HF_MIN
            ):
                self._candidate = {"t": self._t, "peak": energy, "hf": hf, "age": 0, "decayed": False}
            else:
                # Taban yavaş öğrenir; ani yükselmeye neredeyse hiç kapılmaz.
                rate = 0.02 if energy < self._floor * 4 else 0.002
                self._floor = max(FLOOR_MIN, self._floor * (1 - rate) + energy * rate)

        self._history = [self._history[1], energy]
        return fired

    def _reject(self, why: str, cand: dict) -> None:
        logger.debug("[SNAP] aday elendi (%s) tepe=%.0f hf=%.2f", why, cand["peak"], cand["hf"])
        self._candidate = None

    def _register(self, t: float) -> bool:
        if t < self._cooldown_until:
            return False
        self._snaps = [s for s in self._snaps if t - s <= PAIR_MAX_S * (self.required - 1)]
        if self._snaps and t - self._snaps[-1] < PAIR_MIN_S:
            return False  # aynı şıklatmanın yankısı
        self._snaps.append(t)
        logger.debug("[SNAP] şıklatma %d/%d", len(self._snaps), self.required)
        if len(self._snaps) >= self.required:
            self._snaps.clear()
            self._cooldown_until = t + COOLDOWN_S
            return True
        return False
