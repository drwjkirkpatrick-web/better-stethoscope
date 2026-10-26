"""On-disk artifacts: WAV + FLAC, spectrogram figures, physician packet.

Everything the reviewing physician receives is assembled here:

* 24-bit WAV (the archival master, kept in the session directory)
* FLAC (bit-identical lossless copy, half the size, what goes in the zip)
* one PNG per take: waveform over a spectrogram up to 2 kHz
* SUMMARY.txt (plain-text clinical summary, human-readable anywhere)
* README_for_physician.txt (how to open, what the labels mean, disclaimer)
* metadata.json (machine-readable, mirrors the summary)

WHY FLAC in the packet and WAV on disk: patient portals and email
attachment limits punish 15 s 24-bit WAVs (~3.5 MB) far less than they
punish carelessness, but FLAC gives the same bits at ~50-60% size and
plays in any modern browser/player -- and the WAV master never leaves
the clinic machine unless asked for.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf


def save_wav(path: Path, audio: np.ndarray, fs: int, subtype: str = "PCM_24") -> Path:
    """Write the 24-bit WAV master. Float input in [-1, 1] is the contract."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.asarray(audio, dtype=np.float32), fs, subtype=subtype)
    return path


def save_flac(path: Path, audio: np.ndarray, fs: int, subtype: str = "PCM_24") -> Path:
    """Lossless FLAC copy for transfer (same samples, smaller file)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.asarray(audio, dtype=np.float32), fs, format="FLAC", subtype=subtype)
    return path


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------


def figure_png(
    x: np.ndarray,
    fs: int,
    path: Path,
    title: str = "",
    fmax: float = 2000.0,
) -> Optional[Path]:
    """One image per take: waveform on top, spectrogram (to ``fmax``) below.

    Returns None (with a console note) when matplotlib is missing -- a Pi
    trimmed to the bare minimum can still record; it just ships no picture.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")  # headless: never try to open a display
        from matplotlib import pyplot as plt
    except ImportError:
        print("note: matplotlib not installed -- skipping figures (pip install matplotlib)")
        return None

    x = np.asarray(x, dtype=np.float32).ravel()
    t = np.arange(x.size) / fs

    fig, (ax_wave, ax_spec) = plt.subplots(
        2, 1, figsize=(11, 6.5), sharex=True, gridspec_kw={"height_ratios": [1, 2]}
    )

    # -- waveform: decimate only for DISPLAY (keep every 1 ms of ink) -----
    step = max(1, int(fs / 1000))
    ax_wave.plot(t[::step], x[::step], lw=0.6, color="#b3202c")
    ax_wave.set_ylabel("amplitude")
    ax_wave.set_ylim(-1.05, 1.05)
    ax_wave.grid(alpha=0.25)

    # -- spectrogram: 4th-order detail, dB scale, clipped to the heart band --
    from scipy import signal as sp_signal

    freqs, times, power = sp_signal.spectrogram(
        x.astype(np.float64), fs=fs, nperseg=2048, noverlap=1536, window="hann"
    )
    keep = freqs <= fmax
    db = 10.0 * np.log10(np.maximum(power[keep], 1e-14))
    mesh = ax_spec.pcolormesh(times, freqs[keep], db, shading="auto", cmap="magma")
    ax_spec.set_ylabel("frequency (Hz)")
    ax_spec.set_xlabel("time (s)")
    fig.colorbar(mesh, ax=ax_spec, label="dB", pad=0.01)

    if title:
        fig.suptitle(title)
    fig.tight_layout()
    path = Path(path)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


# --------------------------------------------------------------------------
# Text artifacts
# --------------------------------------------------------------------------

_PHYSICIAN_README = """\
Better-stethoscope physician packet
===================================

Contents
--------
  *.flac                 Lossless 24-bit audio of each auscultation position.
                         Plays in any browser or audio player; headphones
                         recommended for low-frequency content.
  *_position.png         Waveform (top) and spectrogram to 2 kHz (bottom)
                         for each take.
  SUMMARY.txt            Plain-text summary: positions, durations, the
                         software's rate estimate and quality verdict.
  metadata.json          Machine-readable mirror of the summary.

Position labels
---------------
  aortic     2nd right intercostal space, sternal border
  pulmonic   2nd left intercostal space, sternal border
  erbs       3rd left intercostal space (Erb's point)
  tricuspid  4th-5th left intercostal space, lower sternal border
  mitral     5th left intercostal space, midclavicular line (apex)

Reading notes
------------
  * S1/S2 fundamentals sit at 20-150 Hz; murmurs typically 150-600 Hz.
  * The auto-detected "bpm" is a period estimate from the phonocardiogram,
    not an ECG-derived heart rate -- trust your ears and the tracing.
  * Files whose quality verdict in SUMMARY.txt is "reposition" or
    "technical" are flagged as unreliable at capture time.

Disclaimer
----------
This packet is a telehealth aid produced by an uncritical recording
device; it is not a medical device output and carries no diagnostic
interpretation. All findings require physician review.
"""


def write_summary(path: Path, session_meta: dict, takes: list[dict]) -> Path:
    """Human-readable clinical summary of a session."""
    lines: list[str] = []
    lines.append("BETTER-STETHOSCOPE SESSION SUMMARY")
    lines.append("=" * 60)
    lines.append(f"Session:      {session_meta.get('session_id', '')}")
    lines.append(f"Started:      {session_meta.get('started_at', '')}")
    lines.append(f"Front-end:    {session_meta.get('recorder_display', '') or session_meta.get('recorder', '')}")
    lines.append(f"Device:       {session_meta.get('device_name', '')}")
    lines.append(f"Format:       {session_meta.get('sample_rate_hz', '')} Hz, {session_meta.get('subtype', '')}")
    if session_meta.get("patient_label"):
        lines.append(f"Patient code: {session_meta['patient_label']}")
    if session_meta.get("operator_notes"):
        lines.append(f"Notes:        {session_meta['operator_notes']}")
    lines.append("")
    lines.append("Takes")
    lines.append("-" * 60)
    for take in takes:
        bpm = take.get("bpm")
        bpm_txt = f"{bpm:.0f} bpm (conf {take.get('bpm_confidence', 0):.2f})" if bpm else "no rhythm found"
        lines.append(
            f"{take.get('position_name', take.get('position', '?')):<22} "
            f"{take.get('duration_s', 0):5.1f}s  {bpm_txt:<24} verdict={take.get('verdict', '?')}"
        )
        lines.append(f"    file: {take.get('filename', '')}")
        for advice in take.get("advice", []):
            lines.append(f"    note: {advice}")
    lines.append("")
    lines.append("Position key: aortic/pulmonic/erbs/tricuspid/mitral = 2nd R ICS /")
    lines.append("2nd L ICS / 3rd L ICS (Erb's) / 4th-5th L ICS / apex 5th L ICS MCL.")
    lines.append("")
    lines.append("Transfer: send this zip through your clinic's secure channel.")

    path = Path(path)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_physician_readme(path: Path) -> Path:
    path = Path(path)
    path.write_text(_PHYSICIAN_README, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Packet assembly
# --------------------------------------------------------------------------


def build_physician_packet(
    session_dir: Path,
    session_meta: dict,
    takes: list,
) -> Path:
    """Package a finished session into one zip for the physician.

    ``takes`` is a sequence of objects with ``.path`` (WAV), ``.report``
    (QualityReport) and ``.meta`` (RecordingMeta) -- i.e. the TakeResult
    objects the Session collects. The zip lands next to the session
    directory and contains FLAC + figures + text; the WAV masters stay in
    the session directory.
    """
    session_dir = Path(session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)

    flac_paths: list[Path] = []
    png_paths: list[Path] = []
    take_dicts: list[dict] = []

    for take in takes:
        audio, fs = sf.read(str(take.path), dtype="float32")
        flac = save_flac(take.path.with_suffix(".flac"), audio, fs)
        flac_paths.append(flac)
        fig = figure_png(
            audio,
            int(fs),
            take.path.with_suffix(".png"),
            title=f"{take.meta.position_name} -- {take.meta.filename}",
        )
        if fig is not None:
            png_paths.append(fig)
        take_dicts.append(take.meta.to_dict())

    summary = write_summary(session_dir / "SUMMARY.txt", session_meta, take_dicts)
    readme = write_physician_readme(session_dir / "README_for_physician.txt")
    meta_json = session_dir / "metadata.json"
    # metadata.json itself is written by the Session; if present it ships too.

    zip_path = session_dir.parent / f"{session_dir.name}_physician_packet.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in flac_paths + png_paths + [summary, readme] + (
            [meta_json] if meta_json.exists() else []
        ):
            zf.write(path, arcname=f"{session_dir.name}/{path.name}")
    return zip_path


def copy_session(source_dir: Path, dest_dir: Path) -> Path:
    """Copy a session directory (e.g., onto a USB stick for hand-off)."""
    return Path(shutil.copytree(Path(source_dir), Path(dest_dir) / Path(source_dir).name, dirs_exist_ok=True))