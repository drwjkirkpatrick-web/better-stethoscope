"""Command-line interface: ``python -m better_stethoscope <command>``.

Commands:
  devices    list microphone front-end modules, discovered devices, errors
  monitor    live level meter + rolling heart-rate estimate (set placement)
  record     one position, one take, printed quality verdict
  session    guided five-position exam (A-P-E-T-M) + physician packet
  analyze    post-hoc quality report on any WAV (works on ANY recorder's
             file -- including one exported from a commercial device)
  export     rebuild a physician packet from an existing session directory
  demo       synthesize a heart-sound train and analyze it (no hardware)

Exit codes: 0 success; 1 flagged/failed (analyze returns 1 when the take
verdict is not "good" -- handy for scripted batch review).
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import deque
from pathlib import Path
from typing import Optional

import numpy as np

from . import __version__, quality
from . import recorders as registry
from .anatomy import DEFAULT_ORDER, get_position
from .config import PHI_NOTE
from .metadata import RecordingMeta, load_json
from .recorders.base import BaseRecorder
from .session import Session


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _pick_module(slug: Optional[str]):
    """Resolve the requested module (or auto-pick one with a live device)."""
    classes = registry.available()
    if not classes:
        details = "\n".join(f"  {k}: {v}" for k, v in registry.errors().items())
        raise SystemExit(f"No recorder modules available:\n{details}")
    if slug:
        return registry.get(slug)
    # Auto: prefer the first module (in registry order) that sees a device.
    for name in registry.MODULE_NAMES:
        cls = classes.get(name)
        if cls is not None and cls.discover():
            return cls
    return next(iter(classes.values()))


def _make_recorder(args) -> BaseRecorder:
    cls = _pick_module(getattr(args, "module", None))
    return cls(
        device_index=getattr(args, "device", None),
        sample_rate=getattr(args, "sample_rate", 48000),
    )


def _db(rms: float) -> float:
    return 20.0 * math.log10(rms) if rms > 0 else -120.0


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_devices(args) -> int:
    ok, msg = BaseRecorder.backend_status()
    print(f"backend: {msg}" if ok else f"backend problem: {msg}")
    print()
    classes = registry.available()
    for slug in registry.MODULE_NAMES:
        cls = classes.get(slug)
        if cls is None:
            continue
        print(f"[{slug}] {cls.display_name}")
        print(f"      {cls.description}")
        if cls.gain_advice:
            print(f"      gain: {cls.gain_advice}")
        for dev in cls.discover():
            print(f"      device {dev['index']}: {dev['name']}")
        print()
    problems = registry.errors()
    if problems:
        print("unavailable modules:")
        for name, why in problems.items():
            print(f"  {name}: {why}")
    return 0


def cmd_monitor(args) -> int:
    rec = _make_recorder(args)
    print(f"front-end: {type(rec).display_name}")
    print("listening... Ctrl-C stops. Match the bar to a healthy take:")
    print("  aim for the bar around -25 to -12 dBFS with a visible beat rhythm.\n")

    hold_s = 12.0
    buffer = deque(maxlen=max(2, int(hold_s * rec.sample_rate / rec.blocksize)))
    printed_bpm_at = -hold_s  # force an early first estimate
    blocks_seen = 0
    try:
        for block in rec.iter_blocks():
            blocks_seen += 1
            buffer.append(block)
            rms = float(np.sqrt(np.mean(block.astype(np.float64) ** 2)))
            db = _db(rms)
            filled = max(0, min(40, int((db + 60) / 60 * 40)))
            print(f"\r  {'|' * filled}{'.' * (40 - filled)} {db:7.1f} dBFS", end="")
            if blocks_seen % max(1, int(2 * rec.sample_rate / rec.blocksize)) == 0:
                window = np.concatenate(list(buffer))
                bpm, conf = _rolling_bpm(window, rec.sample_rate)
                if bpm is not None:
                    print(f"   ~{bpm:3.0f} bpm (conf {conf:.2f})", end="")
            print("", end="", flush=True)
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


def _rolling_bpm(x: np.ndarray, fs: int):
    from .filters import estimate_bpm

    return estimate_bpm(x, fs)


def cmd_record(args) -> int:
    session = Session(
        recorder=_make_recorder(args),
        label=args.label,
        out_root=Path(args.out) if args.out else None,
        interactive=False,
    )
    take = session.record_position(args.position, seconds=args.seconds)
    print(f"\nsaved: {take.path}")
    print(f"session directory: {session.dir}")
    print(PHI_NOTE)
    return 0 if take.report.verdict == quality.VERDICT_GOOD else 1


def cmd_session(args) -> int:
    session = Session(
        recorder=_make_recorder(args),
        label=args.label,
        out_root=Path(args.out) if args.out else None,
        interactive=True,
    )
    print(f"front-end: {type(session.recorder).display_name}")
    print(f"positions: {' -> '.join(session.config.positions)}")
    session.run()
    zip_path = session.finalize()
    print(f"\nphysician packet: {zip_path}")
    print(PHI_NOTE)
    return 0


def cmd_analyze(args) -> int:
    import soundfile as sf

    path = Path(args.wav)
    x, fs = sf.read(str(path), dtype="float32", always_2d=True)
    x = x.mean(axis=1)  # fold stereo to mono for analysis
    report = quality.analyze(x, int(fs))
    print(f"{path.name}: {report.one_line()}")
    for advice in report.advice:
        print(f"  ! {advice}")
    print(
        f"  band energy: 20-150 Hz {report.fraction_20_150_hz:.0%} | "
        f"150-600 Hz {report.fraction_150_600_hz:.0%} | >600 Hz {report.fraction_above_600_hz:.0%}"
    )
    if args.figures:
        from .report import figure_png

        fig = figure_png(x, int(fs), path.with_suffix(".png"), title=path.name)
        if fig:
            print(f"  figure: {fig}")
    return 0 if report.verdict == quality.VERDICT_GOOD else 1


def cmd_export(args) -> int:
    """Rebuild a physician packet from a session directory (any WAVs inside)."""
    import soundfile as sf

    from .report import build_physician_packet

    session_dir = Path(args.session_dir)
    meta: dict = {}
    meta_path = session_dir / "metadata.json"
    if meta_path.exists():
        meta = load_json(meta_path)
    else:
        meta = {"session_id": session_dir.name, "started_at": "", "recorder": "unknown"}

    takes = []
    for wav in sorted(session_dir.glob("*.wav")):
        audio, fs = sf.read(str(wav), dtype="float32", always_2d=True)
        audio = audio.mean(axis=1)
        # position is the last filename token ("_r2" suffixes are re-records)
        stem = wav.stem.split("_")
        position = stem[-2] if stem[-1].startswith("r") and stem[-1][1:].isdigit() else stem[-1]
        report = quality.analyze(audio, int(fs))
        rmeta = RecordingMeta(
            position=position,
            position_name=get_position(position).name,
            started_at=meta.get("started_at", ""),
            duration_s=len(audio) / fs,
            filename=wav.name,
            bpm=report.bpm,
            bpm_confidence=report.bpm_confidence,
            verdict=report.verdict,
            advice=report.advice,
        )
        takes.append(
            type("ExportTake", (), {"path": wav, "report": report, "meta": rmeta})()
        )

    if not takes:
        raise SystemExit(f"no WAV files found in {session_dir}")
    zip_path = build_physician_packet(session_dir, meta, takes)
    print(f"physician packet: {zip_path}")
    return 0


def cmd_demo(args) -> int:
    from .filters import demo_heart_signal

    x = demo_heart_signal(bpm=72, seconds=8.0, amplitude=0.3)
    report = quality.analyze(x, 48000)
    print("synthetic 72 bpm S1/S2 train, 8 s, 48 kHz -- pipeline self-test")
    print(f"  {report.one_line()}")
    if args.out:
        from .report import save_wav

        path = save_wav(Path(args.out), x, 48000)
        print(f"  saved: {path}")
    print("install OK: DSP + quality gate verified (no microphone involved).")
    return 0 if report.verdict == quality.VERDICT_GOOD else 1


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--module", help="recorder module slug (see `devices`)")
    p.add_argument("--device", type=int, default=None, help="PortAudio device index")
    p.add_argument("--sample-rate", type=int, default=48000)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="better-stethoscope",
        description="High-quality heart-sound recording on a Raspberry Pi.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("devices", help="list front-end modules and devices")
    p.set_defaults(func=cmd_devices)

    p = sub.add_parser("monitor", help="live level meter + heart-rate estimate")
    _add_common(p)
    p.set_defaults(func=cmd_monitor)

    p = sub.add_parser("record", help="record one position")
    _add_common(p)
    p.add_argument("--position", default="mitral", help=f"one of: {', '.join(DEFAULT_ORDER)} (or any label)")
    p.add_argument("--seconds", type=float, default=15.0)
    p.add_argument("--label", default="", help="coded patient label (metadata only, never filenames)")
    p.add_argument("--out", default=None, help="recordings root (default ./recordings)")
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("session", help="guided five-position exam + physician packet")
    _add_common(p)
    p.add_argument("--seconds", type=float, default=None, help="seconds per position (default 15)")
    p.add_argument("--label", default="", help="coded patient label (metadata only)")
    p.add_argument("--out", default=None, help="recordings root (default ./recordings)")
    p.set_defaults(func=cmd_session)

    p = sub.add_parser("analyze", help="quality report for any WAV")
    p.add_argument("wav", help="path to a WAV file")
    p.add_argument("--figures", action="store_true", help="also write a PNG figure")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("export", help="build a physician packet from a session directory")
    p.add_argument("session_dir", help="session directory containing WAVs")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("demo", help="synthetic pipeline self-test (no hardware)")
    p.add_argument("--out", default=None, help="optionally save the demo WAV here")
    p.set_defaults(func=cmd_demo)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        print("\ninterrupted.")
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())