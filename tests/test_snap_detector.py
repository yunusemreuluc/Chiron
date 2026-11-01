"""core/snap_detector.py — yapay seslerle şıklatma / şıklatma-olmayan ayrımı."""

import numpy as np

from core.snap_detector import SnapDetector

SR = 16000
RNG = np.random.default_rng(7)


def silence(seconds: float, rms: float = 40.0) -> np.ndarray:
    return RNG.normal(0, rms, int(SR * seconds))


def snap(amplitude: float = 9000.0) -> np.ndarray:
    """Tiz, ~5 ms'de sönen gürültü patlaması (gerçek şıklatmanın kaba modeli)."""
    n = int(SR * 0.04)
    t = np.arange(n) / SR
    burst = np.diff(RNG.normal(0, 1, n + 1))  # yüksek geçiren beyaz gürültü
    return amplitude * burst / np.std(burst) * np.exp(-t / 0.005)


def thump(amplitude: float = 12000.0) -> np.ndarray:
    """Masaya vuruş: düşük frekanslı, aynı hızda sönen gümbürtü."""
    n = int(SR * 0.08)
    t = np.arange(n) / SR
    return amplitude * np.sin(2 * np.pi * 90 * t) * np.exp(-t / 0.02)


def syllable(amplitude: float = 6000.0) -> np.ndarray:
    """Patlamalı ünsüz + ünlü: 't' benzeri tiz atak, hemen ardından 180 ms harmonik ses."""
    plosive = snap(amplitude)[: int(SR * 0.012)]
    n = int(SR * 0.18)
    t = np.arange(n) / SR
    vowel = sum(np.sin(2 * np.pi * 140 * k * t) / k for k in range(1, 6))
    vowel = amplitude * vowel / np.max(np.abs(vowel)) * np.sin(np.pi * t / t[-1])
    return np.concatenate((plosive, vowel))


def run(*parts: np.ndarray, required: int = 2) -> int:
    """Sesi main.py gibi 1024'lük parçalarla besler, kaç kez tetiklendiğini sayar."""
    audio = np.clip(np.concatenate(parts), -32768, 32767).astype(np.int16).tobytes()
    detector = SnapDetector(SR, required=required)
    chunk = 1024 * 2
    return sum(detector.feed(audio[i:i + chunk]) for i in range(0, len(audio), chunk))


def test_double_snap_fires_once():
    assert run(silence(1.0), snap(), silence(0.3), snap(), silence(1.0)) == 1


def test_single_snap_does_not_fire_by_default():
    assert run(silence(1.0), snap(), silence(1.5)) == 0


def test_single_snap_fires_when_one_required():
    assert run(silence(1.0), snap(), silence(1.0), required=1) == 1


def test_snaps_too_far_apart_do_not_pair():
    assert run(silence(1.0), snap(), silence(1.2), snap(), silence(1.0)) == 0


def test_speech_does_not_fire():
    speech = []
    for _ in range(12):
        speech += [syllable(), silence(0.06, rms=150)]
    assert run(silence(1.0), *speech, silence(1.0)) == 0


def test_table_knock_does_not_fire():
    assert run(silence(1.0), thump(), silence(0.3), thump(), silence(1.0)) == 0


def test_quiet_snaps_far_from_mic_are_ignored():
    assert run(silence(1.0), snap(300), silence(0.3), snap(300), silence(1.0)) == 0


def test_snaps_over_background_noise():
    noisy = lambda s: silence(s, rms=300)  # noqa: E731 — fan/klima gürültüsü
    assert run(noisy(1.5), snap(), noisy(0.35), snap(), noisy(1.0)) == 1


def test_cooldown_blocks_immediate_retrigger():
    pair = [snap(), silence(0.25), snap()]
    assert run(silence(1.0), *pair, silence(0.3), *pair, silence(1.0)) == 1
