"""Automatic quality gate: "is this take worth sending to a physician?"

A take can fail three ways, and each has a distinct fix:

* ``technical``  -- the recording chain is mis-set (clipping, dead channel).
  Fix the gain/cable, then re-record.
* ``reposition`` -- the chain works but the acoustic coupling is bad (too
  quiet, noisy room, or the chestpiece is off the apex). Re-couple and
  re-record; no amount of post-processing rescues a bad take.
* ``good``       -- send it.

The numbers the gate computes are deliberately conservative and are printed
with the verdict so a human can overrule them -- the operator is a
clinician, and the software is a gate, not a judge.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

import numpy as np

from . import filters
from .config import (
    HEART_BAND_HIGH_HZ,
    HEART_BAND_LOW_HZ,
    MURMUR_BAND_HIGH_HZ,
    MURMUR_BAND_LOW_HZ,
    S1S2_BAND_HIGH_HZ,
)


def _sp():
    """Lazy scipy.signal import (same rationale as filters._sp)."""
    try:
        from scipy import signal

        return signal
    except ImportError as exc:  # pragma: no cover - dev machines only
        raise RuntimeError(
            "scipy is required for better_stethoscope.quality. "
            "Install it with: pip install scipy"
        ) from exc


VERDICT_GOOD = "good"
VERDICT_RETRY = "reposition"
VERDICT_TECH = "technical"

# Decision thresholds -- module-level so tests and CLI help can read them.
CLIP_FRACTION_MAX = 0.005    # >0.5% clipped samples = a technical failure
RMS_DBFS_MIN = -45.0         # quieter than this and S1/S2 will be unusable
SNR_DB_MIN = 10.0            # signal must beat the room by ~10 dB
BPM_CONFIDENCE_MIN = 0.20    # below this, print a low-confidence warning
PEAK_NEAR_FULL_DBFS = -0.3   # within 0.3 dB of full scale = about to clip


@dataclass
class QualityReport:
    """Every number the gate looks at, so verdicts are never opaque."""

    duration_s: float
    peak_dbfs: float
    rms_dbfs: float
    noise_floor_dbfs: float
    snr_db: float
    clip_fraction: float
    bpm: Optional[float]
    bpm_confidence: float
    fraction_20_150_hz: float
    fraction_150_600_hz: float
    fraction_above_600_hz: float
    verdict: str = ""
    advice: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def one_line(self) -> str:
        bpm_txt = f"{self.bpm:.0f} bpm" if self.bpm is not None else "no rhythm found"
        return (
            f"verdict={self.verdict} | peak {self.peak_dbfs:.1f} dBFS | "
            f"rms {self.rms_dbfs:.1f} dBFS | SNR {self.snr_db:.1f} dB | "
            f"clip {100 * self.clip_fraction:.2f}% | {bpm_txt} "
            f"(conf {self.bpm_confidence:.2f})"
        )


def dbfs(x: np.ndarray) -> float:
    """RMS level in dB relative to digital full scale (1.0)."""
    x = np.asarray(x)
    if x.size == 0:
        return -np.inf
    rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
    if rms <= 0.0:
        return -np.inf
    return 20.0 * np.log10(rms)


def frame_rms_db(x: np.ndarray, fs: float, frame_ms: float = 50.0) -> np.ndarray:
    """RMS in dBFS of consecutive frames (default 50 ms windows).

    Used for the noise-floor estimate: quiet frames between beats reveal
    how loud the room/coupling noise actually is.
    """
    x = np.asarray(x)
    n = int(round(fs * frame_ms / 1000.0))
    if n < 1 or x.size < n:
        return np.array([dbfs(x)])
    trimmed = x[: (x.size // n) * n]
    frames = trimmed.reshape(-1, n)
    rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
    with np.errstate(divide="ignore"):
        return 20.0 * np.log10(np.maximum(rms, 1e-12))


def _band_fractions(x: np.ndarray, fs: float) -> tuple[float, float, float]:
    """Fraction of in-band energy in the S1/S2 band, murmur band, above."""
    if x.size < 512:
        return 0.0, 0.0, 0.0
    sp = _sp()
    freqs, power = sp.welch(x.astype(np.float64), fs=fs, nperseg=2048)
    in_band = (freqs >= HEART_BAND_LOW_HZ) & (freqs <= HEART_BAND_HIGH_HZ)
    total = float(np.sum(power[in_band]))
    if total <= 0.0:
        return 0.0, 0.0, 0.0
    s1s2 = float(np.sum(power[(freqs >= HEART_BAND_LOW_HZ) & (freqs <= S1S2_BAND_HIGH_HZ)]))
    murmur = float(
        np.sum(power[(freqs >= MURMUR_BAND_LOW_HZ) & (freqs <= MURMUR_BAND_HIGH_HZ)])
    )
    above = float(np.sum(power[freqs > MURMUR_BAND_HIGH_HZ]))
    return s1s2 / total, murmur / total, above / total


def analyze(x: np.ndarray, fs: float) -> QualityReport:
    """Compute every metric and return a full QualityReport with verdict."""
    x = np.asarray(x, dtype=np.float32).ravel()
    duration_s = x.size / float(fs)

    peak = float(np.max(np.abs(x))) if x.size else 0.0
    peak_dbfs = 20.0 * np.log10(peak) if peak > 0 else -np.inf
    rms_dbfs = dbfs(x)
    clip_fraction = float(np.mean(np.abs(x) >= 0.999)) if x.size else 1.0

    frames_db = frame_rms_db(x, fs)
    noise_floor_dbfs = float(np.percentile(frames_db, 10))
    snr_db = rms_dbfs - noise_floor_dbfs

    bpm, bpm_confidence = filters.estimate_bpm(x, fs)
    f_s1s2, f_murmur, f_above = _band_fractions(x, fs)

    report = QualityReport(
        duration_s=duration_s,
        peak_dbfs=peak_dbfs,
        rms_dbfs=rms_dbfs,
        noise_floor_dbfs=noise_floor_dbfs,
        snr_db=snr_db,
        clip_fraction=clip_fraction,
        bpm=bpm,
        bpm_confidence=bpm_confidence,
        fraction_20_150_hz=f_s1s2,
        fraction_150_600_hz=f_murmur,
        fraction_above_600_hz=f_above,
    )

    # ---- verdict ladder: hard failures first, soft warnings after ----
    advice: list[str] = []
    if report.clip_fraction > CLIP_FRACTION_MAX:
        report.verdict = VERDICT_TECH
        advice.append(
            "Input is clipping: reduce OS input gain (alsamixer F4) or the "
            "front-end volume, then re-record."
        )
    elif peak_dbfs > PEAK_NEAR_FULL_DBFS:
        advice.append(
            "Peak is at full scale: one firmer contact will clip it. "
            "Consider easing input gain slightly."
        )

    if report.verdict != VERDICT_TECH:
        report.verdict = VERDICT_GOOD
        if rms_dbfs < RMS_DBFS_MIN:
            report.verdict = VERDICT_RETRY
            advice.append(
                "Signal is very quiet: press the chestpiece firmly for a "
                "sealed diaphragm, move toward the apex, and raise input gain."
            )
        elif snr_db < SNR_DB_MIN:
            report.verdict = VERDICT_RETRY
            advice.append(
                "Background noise is close to the signal: quiet the room, "
                "stop moving/cable rustle, prefer battery power."
            )
        if bpm is None and report.verdict == VERDICT_GOOD:
            report.verdict = VERDICT_RETRY
            advice.append(
                "No periodic heart sounds detected: reposition over the "
                "apex (5th ICS, midclavicular line) and re-record."
            )
        elif bpm is not None and bpm_confidence < BPM_CONFIDENCE_MIN:
            advice.append(
                "Rhythm estimate is low-confidence; if the take sounds "
                "arrhythmic consider a longer recording (>= 20 s)."
            )

    report.advice = advice
    return report