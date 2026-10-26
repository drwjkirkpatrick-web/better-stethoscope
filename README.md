🔥 # better-stethoscope

**A Raspberry Pi that turns any of five microphones into a physician-ready heart-sound recorder.**

Point a chestpiece at a beating heart and you get a phonocardiogram: a 24-bit,
48 kHz master WAV, a lossless FLAC, a waveform-over-spectrogram figure, an
automatic quality verdict, and a one-zip packet your physician can open with
headphones and read. Everything between skin and specialist review runs on a
$35 computer.

![License](https://img.shields.io/badge/license-MIT-blue)
![Tests](https://img.shields.io/badge/tests-85%20passed-brightgreen)
![Modules](https://img.shields.io/badge/microphone%20modules-5-orange)
![Pi](https://img.shields.io/badge/platform-Raspberry%20Pi%20%2B%20any%20Linux-critical)
![Format](https://img.shields.io/badge/capture-48kHz%2F24--bit-9cf)

## What makes it special

* **A differential you can run.** Five microphone front-ends — electret
  capsule in tubing, piezo contact mic, I2S MEMS, generic USB, and the
  Thinklabs One line-in — each documented like a clinical differential
  (findings, strengths, weaknesses, disposition) and each shipped as a
  drop-in module behind one common interface.
  Read the [microphone differential](docs/microphone-differential.md).
* **An honest quality gate.** Every take is graded before you accept it:
  clipping → *technical*, too-quiet/noisy/no-rhythm → *reposition*, else
  *good* — with the numbers printed so a clinician can overrule the machine.
* **Research you can check.** The stethoscope recommendation
  ([Littmann Cardiology IV as donor head](docs/research-acoustic-stethoscope.md))
  and every microphone claim carry inline, verifiable citations.
* **PHI-minimal by construction.** Filenames hold a timestamp and an
  auscultation position — never a patient name. The optional patient label
  lives only in `metadata.json`. Patient audio never enters git.
* **Runs before you buy anything.** `better-stethoscope demo` synthesizes a
  72 bpm S1/S2 train and grades it, proving the whole pipeline with zero
  hardware. The full test suite (85 tests) runs on any Linux box — the
  audio backend is faked, not mocked-out-but-broken.

## Quick start (on a Raspberry Pi)

```bash
sudo apt install -y libportaudio2 alsa-utils
git clone https://github.com/drwjkirkpatrick-web/better-stethoscope.git
cd better-stethoscope
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

.venv/bin/python -m better_stethoscope demo        # no-hardware self-test
.venv/bin/python -m better_stethoscope devices     # what do you have plugged in?
.venv/bin/python -m better_stethoscope monitor     # live level meter + heart rate
.venv/bin/python -m better_stethoscope session --label chart-114
```

The guided session walks the classic five positions — aortic, pulmonic,
Erb's point, tricuspid, mitral (A-P-E-T-M) — records ~15 s per position,
prints the verdict, and ends with:

```
recordings/2026-08-26_101530_physician_packet.zip   # FLAC + figures + summary
```

Send that zip through your clinic's secure channel. Full assembly and wiring
instructions for all five front-ends live in
[the Raspberry Pi setup guide](docs/raspberry-pi-setup.md).

## The five front-ends at a glance

| Module | One-line story | Cost | Low-frequency heart sounds |
|---|---|---|---|
| `electret` | $2 capsule sealed into stethoscope tubing (peer-reviewed DIY design) | ~$10–15 + donor scope | excellent — the recommended build |
| `thinklabs` | Commercial Thinklabs One → 3.5 mm → line-in, one cable, done | ~$500 | reference-grade |
| `piezo` | Structure-borne vibration pickup — bring a ≥1 MΩ buffer or lose the bass | ~$20–40 | good only if buffered |
| `mems_i2s` | 24-bit digital MEMS straight onto the Pi's GPIO — watch the 60 Hz corner | ~$5–10 | fair (rolled off below 60 Hz) |
| `usb_mic` | Whatever USB mic you have; the fallback that always works | varies | varies |

## Commands

| Command | What it does |
|---|---|
| `devices` | list front-end modules, discovered audio devices, and load errors |
| `monitor` | live dBFS meter + rolling heart-rate estimate while you position |
| `record` | single take at a single auscultation position |
| `session` | guided five-position exam with accept/re-record prompts + packet |
| `analyze` | grade ANY WAV post-hoc (works on exports from other recorders too) |
| `export` | rebuild a physician packet from an existing session directory |
| `demo` | synthetic pipeline self-test, no hardware |

## Repository structure

```
better_stethoscope/
    config.py          # audio/session settings + the 20–2000 Hz band constants
    anatomy.py         # the five auscultation positions and their landmarks
    filters.py         # SOS band-pass/notch, envelope, autocorrelation BPM
    quality.py         # the verdict ladder: technical / reposition / good
    metadata.py        # PHI-minimal naming + JSON metadata
    session.py         # guided A-P-E-T-M flow, retry without overwrite
    report.py          # WAV/FLAC masters, figures, SUMMARY.txt, packet zip
    cli.py              # python -m better_stethoscope ...
    recorders/
        base.py         # BaseRecorder contract: discover / record / iter_blocks
        electret.py     # capsule-in-tubing front-end
        piezo.py        # contact mic + high-Z buffer front-end
        mems_i2s.py     # INMP441/SPH0645 I2S front-end
        thinklabs.py    # Thinklabs One line-in front-end
        usb_mic.py      # generic USB front-end (match-anything fallback)
tests/                  # 85 tests; fake sounddevice backend, no hardware needed
docs/
    research-acoustic-stethoscope.md   # the "best acoustic stethoscope" answer, cited
    microphone-differential.md        # the five-candidate differential, cited
    raspberry-pi-setup.md              # builds, wiring, overlays, troubleshooting
```

## Why 48 kHz / 24-bit?

Heart sounds span roughly 20–2000 Hz, with S1/S2 fundamentals at
20–150 Hz and murmurs mostly 150–600 Hz (cited in the docs). 48 kHz leaves
the anti-alias filter nowhere to interfere; 24-bit gives ~144 dB of
theoretical dynamic range so a faint S3 survives next to a loud S1 in a
single un-gain-ridden take. The raw master is always saved unfiltered —
diagnostic post-processing must never be baked into the recording.

## Disclaimer

This is a recording and review aid built by a physician for physician review.
It is **not a medical device**, carries no diagnostic interpretation, and
makes no FDA claims. Every recording requires clinician judgment. Treat the
automatic "bpm" as a period estimate from the phonocardiogram — trust your
ears and the tracing, not the number.

## Contributing

Issues and pull requests welcome — especially field reports from real
front-end builds: measured spectrograms of the same subject through two
different candidates are exactly the evidence the differential deserves.

— `drwjkirkpatrick-web`