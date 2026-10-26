"""DSP primitives tuned for phonocardiography (heart-sound recording).

The heart-sound band used across the whole project is 20-2000 Hz
(see ``config.py`` and ``docs/microphone-differential.md`` for the
literature). Inside that band:

* S1/S2 ("lub-dub") fundamentals live at ~20-150 Hz
* Most murmurs concentrate at ~150-600 Hz
* Valve clicks and high harmonics extend toward ~2 kHz

Every function here is pure (same input -> same output) and testable
without any audio hardware, which keeps the whole suite runnable on a
development machine -- the Raspberry Pi only matters for the recorder
modules themselves.
"""

from __future__ import annotations

from typing import Optional

import numpy as np


def _sp():
    """Import scipy.signal on demand with a friendly error if absent.

    WHY on demand instead of module level: importing this package must
    never fail on a box without scipy (plain ``--help`` should work), and
    a lazy import gives a better message than ImportError deep in numpy.
    """
    try:
        from scipy import signal

        return signal
    except ImportError as exc:  # pragma: no cover - dev machines only
        raise RuntimeError(
            "scipy is required for better_stethoscope.filters. "
            "Install it with: pip install scipy"
        ) from exc


# --------------------------------------------------------------------------
# Filter design (SOS = second-order sections: numerically stable at low freqs)
# --------------------------------------------------------------------------


def butter_bandpass_sos(fs: float, low: float = 20.0, high: float = 2000.0, order: int = 4) -> np.ndarray:
    """4th-order Butterworth band-pass, returned as second-order sections.

    WHY SOS and not plain b/a coefficients: a 4th-order Butterworth with a
    20 Hz corner at 48 kHz makes transfer-function coefficients so tiny
    that float b/a forms lose precision; SOS cascades stay stable.
    """
    sp = _sp()
    return sp.butter(order, [low, high], btype="bandpass", fs=fs, output="sos")


def butter_highpass_sos(fs: float, low: float = 20.0, order: int = 4) -> np.ndarray:
    """High-pass (rumble/DC drift removal)."""
    sp = _sp()
    return sp.butter(order, low, btype="highpass", fs=fs, output="sos")


def butter_lowpass_sos(fs: float, high: float, order: int = 4) -> np.ndarray:
    """Low-pass (anti-alias when downsampling, or envelope smoothing)."""
    sp = _sp()
    return sp.butter(order, high, btype="lowpass", fs=fs, output="sos")


def notch_sos(fs: float, freq: float = 60.0, q: float = 30.0) -> np.ndarray:
    """Very narrow notch at ``freq`` Hz -- 60 Hz mains hum in the US.

    NOTE: on a battery-powered Pi with a short cable run this is usually
    unnecessary; it exists for bench setups with switch-mode supplies.
    """
    sp = _sp()
    result = sp.iirnotch(freq, q, fs=fs)
    if isinstance(result, tuple):  # scipy returns (b, a) or sos by version
        b, a = result
        return sp.tf2sos(b, a)
    return result


def apply_sos(x: np.ndarray, sos: np.ndarray) -> np.ndarray:
    """Zero-phase (forward-backward) filtering.

    WHY sosfiltfilt and not a streaming filter: S1/S2 timing matters
    clinically (split S2, S4-to-S1 interval), and a one-pass IIR filter
    would delay the heart sounds by tens of milliseconds. Filfilt has zero
    phase distortion at the cost of being offline -- fine, since we filter
    after the take is captured, and we keep the raw file unfiltered anyway.
    """
    sp = _sp()
    x64 = np.asarray(x, dtype=np.float64)
    if x64.size == 0:
        return x64.astype(np.float32)
    return sp.sosfiltfilt(sos, x64).astype(np.float32)


def bandpass(
    x: np.ndarray, fs: float, low: float = 20.0, high: float = 2000.0, order: int = 4
) -> np.ndarray:
    """Band-pass a signal to the heart-sound band (default 20-2000 Hz)."""
    return apply_sos(x, butter_bandpass_sos(fs, low, high, order))


def highpass(x: np.ndarray, fs: float, low: float = 20.0, order: int = 4) -> np.ndarray:
    """High-pass only (keeps murmurs untouched above ``low``)."""
    return apply_sos(x, butter_highpass_sos(fs, low, order))


def notch(x: np.ndarray, fs: float, freq: float = 60.0, q: float = 30.0) -> np.ndarray:
    """Notch out a single frequency (default 60 Hz hum)."""
    return apply_sos(x, notch_sos(fs, freq, q))


# --------------------------------------------------------------------------
# Envelope + heart-rate estimation
# --------------------------------------------------------------------------


def envelope(
    x: np.ndarray, fs: float, low: float = 20.0, high: float = 150.0, smooth_hz: float = 5.0
) -> np.ndarray:
    """Smooth magnitude envelope of the S1/S2 band.

    Rectify the 20-150 Hz band, then low-pass at ``smooth_hz``. One beat
    becomes one gentle hill; the BPM estimator then only has to find the
    spacing between hills. Smoothing at 5 Hz is fast enough to keep beats
    at up to ~180 bpm distinct (180 bpm = 3 Hz beat rate + margin).
    """
    sp = _sp()
    xb = bandpass(x, fs, low, high)
    env = np.abs(xb)
    sos = butter_lowpass_sos(fs, smooth_hz, order=2)
    # sosfiltfilt can ring slightly below zero at the edges; envelopes are
    # a magnitude, so clip the tiny negative excursions.
    return np.clip(sp.sosfiltfilt(sos, env), 0.0, None).astype(np.float32)


def estimate_bpm(
    x: np.ndarray,
    fs: float,
    low: float = 20.0,
    high: float = 150.0,
    min_bpm: float = 30.0,
    max_bpm: float = 180.0,
) -> tuple[Optional[float], float]:
    """Estimate heart rate (bpm) from a phonocardiogram via autocorrelation.

    Returns ``(bpm, confidence)``; bpm is ``None`` when no convincing
    periodicity exists. Confidence (0..1) is the normalized autocorrelation
    peak -- how much the signal looks like itself one beat later. The
    quality gate uses it to warn "rhythm estimate uncertain" instead of
    silently shipping a nonsense number.

    WHY autocorrelation and not peak counting: peak counting breaks on
    murmurs, movement artifact, and split sounds; autocorrelation is robust
    to missing/extra beats because it measures the dominant period.
    """
    _sp()
    if x is None or x.size < int(fs * (60.0 / max_bpm)) + 2:
        return None, 0.0

    env = envelope(x, fs, low, high)
    env = env - env.mean()
    if np.dot(env, env) <= 1e-20:  # flat line: silence, no beats
        return None, 0.0

    # FFT-based autocorrelation: O(n log n), fine for 15 s at 48 kHz.
    n = env.size
    nfft = 1 << int(np.ceil(np.log2(2 * n)))
    spec = np.fft.rfft(env, nfft)
    ac = np.fft.irfft(spec * np.conj(spec), nfft)[: n // 2]
    ac0 = float(ac[0])
    if ac0 <= 1e-20:
        return None, 0.0

    lag_min = max(1, int(fs / (max_bpm / 60.0)))   # 180 bpm -> 0.333 s lag
    lag_max = int(fs / (min_bpm / 60.0))           # 30 bpm  -> 2.0 s lag
    lag_max = min(lag_max, n // 2 - 1)
    if lag_max <= lag_min:
        return None, 0.0

    peak_idx = int(np.argmax(ac[lag_min : lag_max + 1])) + lag_min
    confidence = float(max(0.0, ac[peak_idx] / ac0))
    if confidence < 0.05:
        return None, confidence
    bpm = 60.0 * fs / peak_idx
    return float(bpm), confidence


# --------------------------------------------------------------------------
# Synthetic test/demo signal
# --------------------------------------------------------------------------


def demo_heart_signal(
    bpm: float = 75.0,
    fs: float = 48000.0,
    seconds: float = 10.0,
    amplitude: float = 0.4,
    s1_freq: float = 45.0,
    s2_freq: float = 70.0,
) -> np.ndarray:
    """Synthetic S1/S2 train used by the test suite and the CLI demo.

    S1 = louder, lower-frequency burst (~45 Hz, like mitral/tricuspid
    closure); S2 = softer, slightly higher burst (~70 Hz, aortic/pulmonic
    closure) arriving after a realistic systolic interval (32% of the
    cycle). It is a *model*, not a real heart -- good enough to prove the
    pipeline measures period, splits and band energy correctly.
    """
    t = np.arange(int(fs * seconds)) / fs
    x = np.zeros_like(t)
    period = 60.0 / bpm
    beat = 0.0
    while beat < seconds:
        for center, freq, amp, width in (
            (beat, s1_freq, 1.0, 0.09),
            (beat + 0.32 * period, s2_freq, 0.6, 0.07),
        ):
            lo = int(max(0.0, (center - 3 * width)) * fs)
            hi = int(min(seconds, (center + 3 * width)) * fs)
            if hi <= lo:
                continue
            tt = t[lo:hi] - center
            burst = np.sin(2 * np.pi * freq * tt) * np.exp(-(tt**2) / (2 * width**2))
            x[lo:hi] += amp * burst
        beat += period
    return (amplitude * x).astype(np.float32)