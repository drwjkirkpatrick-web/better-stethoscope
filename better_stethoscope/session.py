"""Guided auscultation sessions: prompt -> countdown -> record -> gate -> save.

A Session walks the operator through the classic five positions (A-P-E-T-M),
records a fixed-length take at each, runs the quality gate, prints the
verdict, and (when interactive) offers accept / re-record. Every take is
saved as a 24-bit WAV named timestamp_position; re-records never overwrite
(they append ``_r2``, ``_r3``... -- sometimes the "failed" take is the
interesting one).

The session directory name and every filename are PHI-free by construction
(see metadata.py); the optional patient label lives only in metadata.json.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from . import quality as quality_mod
from .anatomy import Position, get_position
from .config import AudioConfig, PHI_NOTE, SessionConfig
from .metadata import (
    RecordingMeta,
    SessionMeta,
    now_iso,
    recording_filename,
    session_dirname,
    write_json,
)
from .recorders.base import BaseRecorder
from .report import save_wav
from . import __version__


@dataclass
class TakeResult:
    """One completed take: where it lives and what the gate thought of it."""

    position: str
    path: Path
    report: quality_mod.QualityReport
    meta: RecordingMeta


class Session:
    """One patient encounter: five positions, quality-gated takes."""

    def __init__(
        self,
        recorder: BaseRecorder,
        config: Optional[SessionConfig] = None,
        audio: Optional[AudioConfig] = None,
        label: str = "",
        out_root: Optional[Path] = None,
        interactive: Optional[bool] = None,
        echo: Callable[[str], None] = print,
    ) -> None:
        self.recorder = recorder
        self.config = config or SessionConfig()
        self.audio = audio or AudioConfig()
        self.interactive = self.config.interactive if interactive is None else interactive
        self.echo = echo

        self.started = datetime.now().astimezone()
        root = Path(out_root) if out_root is not None else Path(self.config.output_root)
        self.dir = root / session_dirname(self.started)
        self.dir.mkdir(parents=True, exist_ok=True)

        # Resolve what the OS says about the device for the chart record.
        device_name = ""
        try:
            for dev in type(recorder).discover():
                if dev["index"] == recorder.device_index or recorder.device_index is None:
                    device_name = dev["name"]
                    break
        except Exception:  # noqa: BLE001 - metadata is best-effort only
            device_name = ""

        self.meta = SessionMeta(
            started_at=now_iso(),
            session_id=self.dir.name,
            recorder=recorder.slug,
            recorder_display=type(recorder).display_name,
            device_name=device_name,
            sample_rate_hz=self.audio.sample_rate,
            subtype=self.audio.wav_subtype,
            software_version=__version__,
            patient_label=label,
        )
        self.takes: list[TakeResult] = []

    # ------------------------------------------------------------------
    def record_position(
        self,
        position_slug: str,
        seconds: Optional[float] = None,
        countdown: Optional[int] = None,
        on_progress: Optional[Callable[[float], None]] = None,
    ) -> TakeResult:
        """Record one position (no prompts, no retry logic -- programmatic)."""
        position = get_position(position_slug)
        seconds = float(seconds if seconds is not None else self.config.seconds_per_position)
        countdown = self.config.countdown_seconds if countdown is None else int(countdown)

        for i in range(countdown, 0, -1):
            self.echo(f"  ... {i}")
            time.sleep(1)

        when = datetime.now().astimezone()
        attempt = 1 + sum(1 for t in self.takes if t.position == position.slug)
        self.echo(f"  recording {position.name} ({seconds:g} s)...")
        audio = self.recorder.record(
            seconds, on_progress=on_progress or (lambda f: self._progress(f, seconds))
        )

        path = save_wav(
            self.dir / recording_filename(position.slug, when, attempt=attempt),
            audio,
            self.audio.sample_rate,
            subtype=self.audio.wav_subtype,
        )

        report = quality_mod.analyze(audio, self.audio.sample_rate)
        rmeta = RecordingMeta(
            position=position.slug,
            position_name=position.name,
            started_at=now_iso(),
            duration_s=seconds,
            filename=path.name,
            bpm=report.bpm,
            bpm_confidence=report.bpm_confidence,
            verdict=report.verdict,
            advice=report.advice,
        )
        take = TakeResult(position=position.slug, path=path, report=report, meta=rmeta)
        self.takes.append(take)
        self.meta.positions.append(position.slug)

        self.echo(f"  -> {report.one_line()}")
        for advice in report.advice:
            self.echo(f"     ! {advice}")
        return take

    def _progress(self, fraction: float, seconds: float) -> None:
        bar_len = 24
        filled = int(bar_len * min(1.0, fraction))
        self.echo(
            f"\r  [{'#' * filled}{'.' * (bar_len - filled)}] "
            f"{fraction * seconds:5.1f}/{seconds:g} s "
        )
        if fraction >= 1.0:
            self.echo("")

    # ------------------------------------------------------------------
    def _prompt(self, text: str) -> str:
        try:
            return input(text).strip().lower()
        except EOFError:
            return ""  # non-interactive pipe: treat as "continue"

    def guided_position(self, position_slug: str) -> Optional[TakeResult]:
        """Prompt the operator, record, and offer accept/re-record.

        Returns the accepted TakeResult, or None when the operator skips.
        """
        position = get_position(position_slug)
        while True:
            self.echo("")
            self.echo(f"=== {position.name} ===")
            self.echo(f"    place: {position.landmark}")
            self.echo(f" listen for: {position.listen_for}")
            if self.interactive:
                self.echo(
                    "    press Enter when the room is quiet and the patient holds "
                    "still (or type 's' to skip)"
                )
                answer = self._prompt("> ")
                if answer == "s":
                    self.echo("    skipped.")
                    return None

            take = self.record_position(position_slug)
            if not self.interactive:
                return take

            if take.report.verdict == quality_mod.VERDICT_GOOD:
                answer = self._prompt("  accept? [Enter=accept, r=re-record] ")
            else:
                answer = self._prompt("  take flagged; [r=re-record, Enter=accept anyway] ")
            if answer == "r":
                continue  # re-record: loops back to the placement prompt
            return take

    def run(self, positions: Optional[list[str]] = None) -> list[TakeResult]:
        """Walk the standard positions (default A-P-E-T-M)."""
        order = positions or list(self.config.positions)
        for slug in order:
            self.guided_position(slug)
        self.echo("")
        self.echo(f"Session directory: {self.dir}")
        self.echo(PHI_NOTE)
        return [t for t in self.takes]

    # ------------------------------------------------------------------
    def finalize(self) -> Path:
        """Write metadata.json and build the physician packet zip."""
        from .report import build_physician_packet  # late import: no cycle

        write_json(self.dir / "metadata.json", self.meta.to_dict())
        if not self.takes:
            raise RuntimeError("nothing recorded -- no packet to build")
        return build_physician_packet(self.dir, self.meta.to_dict(), self.takes)