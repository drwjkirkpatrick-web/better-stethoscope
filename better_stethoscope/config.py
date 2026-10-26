"""Central configuration for better-stethoscope.

Everything an operator (or a test) may want to tweak lives here as plain
dataclasses, so the rest of the codebase never hides magic numbers.

WHY 48 kHz / 24-bit / mono:
  * Heart sounds span roughly 20-2000 Hz (S1/S2 fundamentals sit at
    20-150 Hz; murmurs extend to ~600 Hz and beyond). 48 kHz sampling gives
    a 24 kHz Nyquist ceiling -- far above the band of interest -- so the
    anti-alias filter of any USB/ALSA device is never stressed.
  * 24-bit depth gives ~144 dB of theoretical dynamic range, enough to
    capture a faint S3/S4 alongside a loud S1 in one take without gain
    riding.
  * Mono: auscultation is a single point source; the second channel would
    only double file size.
The default band for analysis (20-2000 Hz) mirrors the published frequency
response of the Eko CORE 500 digital stethoscope -- see
docs/microphone-differential.md for the citations.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


# Heart-sound band constants (Hz). These are shared by filters.py, quality.py
# and the spectrogram code so the whole pipeline agrees on one target band.
HEART_BAND_LOW_HZ = 20.0
HEART_BAND_HIGH_HZ = 2000.0
S1S2_BAND_HIGH_HZ = 150.0     # S1/S2 fundamentals live below ~150 Hz
MURMUR_BAND_LOW_HZ = 150.0    # murmur energy above this is notable
MURMUR_BAND_HIGH_HZ = 600.0   # most murmurs concentrate 150-600 Hz


@dataclass
class AudioConfig:
    """How we open the microphone and what we write to disk."""

    sample_rate: int = 48000          # Hz; 48k is universally supported
    channels: int = 1                 # mono capture
    dtype: str = "float32"            # stream dtype; converted on save
    wav_subtype: str = "PCM_24"        # 24-bit WAV via libsndfile
    flac_subtype: str = "PCM_24"      # lossless FLAC, also 24-bit
    blocksize: int = 1024             # ~21 ms at 48 kHz; small = low latency


@dataclass
class SessionConfig:
    """How a guided auscultation session behaves."""

    # Order follows the classic "A-P-E-T-M" sweep down the precordium;
    # see anatomy.py for the landmarks themselves.
    positions: list[str] = field(
        default_factory=lambda: ["aortic", "pulmonic", "erbs", "tricuspid", "mitral"]
    )
    seconds_per_position: int = 15    # >= 10 s: enough beats for BPM confidence
    countdown_seconds: int = 3       # "quiet... place... hold" settle time
    interactive: bool = True          # prompt accept/re-record after each take
    patient_label: str = ""           # OPTIONAL free-text label (see PHI note)

    # Recordings root. Overridable so tests can point at a tmp_path and the
    # Pi can redirect to a USB stick with one env var.
    output_root: Path = field(
        default_factory=lambda: Path(
            os.environ.get("BETTER_STETHOSCOPE_OUT", "recordings")
        )
    )


PHI_NOTE = (
    "Privacy: filenames contain only a timestamp and the auscultation "
    "position -- never a patient name. The optional patient label is stored "
    "in metadata.json (for the chart) and should be a coded identifier, not "
    "PHI. Transfer the session zip through your clinic's secure channel "
    "(patient portal, encrypted drive), not plain email."
)