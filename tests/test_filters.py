"""Filters: band-pass behavior, envelope, BPM estimation, notch."""

import numpy as np
import pytest

from better_stethoscope import filters as F

FS = 48000.0


def sine(freq, seconds=2.0, amp=0.5, fs=FS):
    t = np.arange(int(fs * seconds)) / fs
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def rms_db(x):
    x = np.asarray(x, dtype=np.float64)
    val = float(np.sqrt(np.mean(x**2)))
    return 20 * np.log10(val) if val > 0 else -np.inf


def steady_db(x, keep=0.25):
    """RMS of the middle portion only.

    WHY: zero-phase filtering (sosfiltfilt) mirrors the signal at the
    edges, and the resulting transient ringing can dominate a whole-signal
    RMS -- hiding how deeply the filter actually attenuates in steady
    state. Judge the filter on the steady middle, not the edges.
    """
    n = x.size
    lo, hi = int(n * keep), int(n * (1 - keep))
    return rms_db(x[lo:hi])


class TestBandpass:
    def test_passes_in_band_sine(self):
        x = sine(40.0)  # S1 territory
        y = F.bandpass(x, FS, 20.0, 2000.0)
        assert abs(rms_db(y) - rms_db(x)) < 1.0

    def test_passes_murmur_band_sine(self):
        x = sine(400.0)
        y = F.bandpass(x, FS, 20.0, 2000.0)
        assert abs(rms_db(y) - rms_db(x)) < 1.0

    def test_rejects_below_band(self):
        x = sine(5.0)
        y = F.bandpass(x, FS, 20.0, 2000.0)
        assert steady_db(y) - steady_db(x) < -20  # >20 dB down at DC/rumble

    def test_rejects_above_band(self):
        x = sine(9000.0)
        y = F.bandpass(x, FS, 20.0, 2000.0)
        assert steady_db(y) - steady_db(x) < -25


class TestNotch:
    def test_removes_60hz(self):
        y = F.notch(sine(60.0), FS)
        assert steady_db(y) < -40  # the 60 Hz component is gone

    def test_leaves_45hz_alone(self):
        x = sine(45.0)
        y = F.notch(x, FS)
        assert steady_db(y) - steady_db(x) > -3


class TestEnvelope:
    def test_positive_and_bounded(self):
        x = F.demo_heart_signal(seconds=5.0)
        env = F.envelope(x, FS)
        assert env.shape == x.shape
        assert float(env.min()) >= 0.0


class TestBpm:
    @pytest.mark.parametrize("bpm", [55, 75, 120, 150])
    def test_synthetic_train(self, bpm):
        x = F.demo_heart_signal(bpm=bpm, seconds=14.0)
        est, conf = F.estimate_bpm(x, FS)
        assert est is not None, "no rhythm found in a clean synthetic train"
        assert est == pytest.approx(bpm, abs=4)
        assert conf > 0.2

    def test_silence_returns_none(self):
        x = np.zeros(int(FS * 10), dtype=np.float32)
        est, conf = F.estimate_bpm(x, FS)
        assert est is None
        assert conf == 0.0

    def test_too_short_returns_none(self):
        est, conf = F.estimate_bpm(np.zeros(1000, dtype=np.float32), FS)
        assert est is None


class TestDemoSignal:
    def test_shape_and_bounds(self):
        x = F.demo_heart_signal(bpm=75, seconds=3.0)
        assert x.dtype == np.float32
        assert x.size == int(3.0 * FS)
        assert float(np.max(np.abs(x))) <= 0.4 + 1e-6