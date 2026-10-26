"""Session/recording metadata and filename conventions (PHI-minimal).

WHY this module exists: the whole point of the project is sending audio to
a physician, so two things must be true for every file we ship:

1. The filename is *context-free* -- timestamp + auscultation position,
   never a patient name. A file called ``20260826_1015_mitral.wav`` that
   leaks out of a channel carries no PHI by itself.
2. The clinical context (patient label, device used, quality verdict,
   estimated rate) rides along in ``metadata.json`` inside the session,
   which travels only through the secure channel with the audio.

The optional patient label is intentionally NOT embedded in any filename
or directory name.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def sanitize(s: str) -> str:
    """Filename-safe slug: lowercase, alphanumerics/underscore/dash only."""
    return re.sub(r"[^a-z0-9_-]+", "_", s.lower()).strip("_")


def session_dirname(when: datetime) -> str:
    """Session directory name: ``YYYY-MM-DD_HHMMSS`` -- no patient data."""
    return when.strftime("%Y-%m-%d_%H%M%S")


def recording_filename(position: str, when: datetime, attempt: int = 1, ext: str = "wav") -> str:
    """Recording filename: ``YYYYMMDD_HHMMSS_<position>[_rN].wav``.

    ``attempt`` > 1 appends ``_rN`` so a re-record never overwrites the
    earlier take -- sometimes the "failed" take is the interesting one.
    """
    pos = sanitize(position)
    base = f"{when.strftime('%Y%m%d_%H%M%S')}_{pos}"
    if attempt > 1:
        base += f"_r{attempt}"
    return f"{base}.{ext.lstrip('.')}"


@dataclass
class SessionMeta:
    """Everything a reviewing physician needs to know about the session."""

    started_at: str                 # ISO 8601 with timezone
    session_id: str                 # session_dirname (also the zip stem)
    recorder: str                   # module slug, e.g. "electret"
    recorder_display: str = ""     # human-readable front-end name
    device_name: str = ""          # ALSA/USB device string
    sample_rate_hz: int = 48000
    subtype: str = "PCM_24"
    software_version: str = ""
    patient_label: str = ""         # OPTIONAL coded ID; never PHI
    operator_notes: str = ""
    positions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RecordingMeta:
    """Per-take metadata for one position recording."""

    position: str
    position_name: str
    started_at: str
    duration_s: float
    filename: str
    bpm: Optional[float] = None
    bpm_confidence: float = 0.0
    verdict: str = ""
    advice: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def now_iso() -> str:
    """Current UTC time as ISO 8601 (timezone-aware, no ambiguity)."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_json(path: Path, obj: Any) -> Path:
    """Write metadata as pretty JSON; ``default=str`` keeps datetimes safe."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False, default=str)
        fh.write("\n")
    return path


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)