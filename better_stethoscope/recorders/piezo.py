"""Piezo contact microphone front-end -- a chest-coupled vibration pickup.

A piezo disc taped flat against the chest is the simplest heart-sound
transducer in the set: it transmits chest-wall vibration directly, with
no stethoscope head, tubing, or trapped air column in the path. What it
gives in mechanical simplicity it takes back in electrical fragility,
so two physics facts dominate every build.

COUPLING (mounting plus the impedance-buffer warning):
    Tape the bare disc flat against the chest wall with medical tape or
    an elastic band; the disc itself is the chestpiece, so nothing else
    needs to touch the skin. CRITICAL: always buffer the disc with a
    JFET or charge-amp impedance converter (a DI box or a 10 MOhm-class
    piezo preamp) before the interface line-in. A piezo element is
    capacitive, so its impedance rises as frequency falls; wired
    straight into a typical 50 kOhm line input, the pair forms an
    accidental roughly 200 Hz high-pass that guts S1/S2 (20-150 Hz), and
    a 1.5 kOhm mic input is worse -- a roughly 1 kHz high-pass that
    eliminates the heart band almost entirely.

SIGNAL CHARACTER (resonance coloration):
    A bare disc is a little spring-mass system and rings at its own
    mechanical resonance, typically somewhere in the 2-6 kHz region --
    the familiar metallic, tinny coloration. Added mass on the disc
    (a blob of epoxy or damping putty over its center) lowers and tames
    the ring. Expect murmurs to sound harsh through piezo; listen (and
    look at the spectrogram) for timing first, timbre second.

GAIN:
    Set gain on the interface itself (its line-in trim or input knob),
    starting around 60 percent; the quality gate flags clipping and
    too-quiet takes automatically.

NOTE:
    See docs/microphone-differential.md for how this front-end compares
    with the other microphones in the set.

TESTS: tests/test_piezo.py exercises discovery and stream construction
with a fake backend (see tests/conftest.py); no hardware needed.
"""

from __future__ import annotations

from typing import Generator

import numpy as np

from .base import BaseRecorder


class PiezoContactRecorder(BaseRecorder):
    """Piezo contact disc through a high-impedance buffer into a USB interface."""

    slug = "piezo"
    display_name = "Piezo contact microphone (chest-coupled disc)"
    description = (
        "A piezo disc taped flat against the chest picks up chest-wall "
        "vibration directly -- no stethoscope head required. It must ride "
        "a high-impedance buffer (JFET or charge-amp, e.g. a DI box or a "
        "10 MOhm-class piezo preamp) into the interface line-in; a bare "
        "disc is a capacitor, and unbuffered inputs accidentally high-pass "
        "the heart band away."
    )
    hardware_notes = (
        "1) Tape the piezo disc flat against the chest wall (medical tape\n"
        "or an elastic band); the disc transmits chest-wall vibration\n"
        "directly, so no stethoscope head is needed.\n"
        "2) CRITICAL: always buffer the disc with a JFET or charge-amp\n"
        "impedance converter (a DI box or a 10 MOhm-class piezo preamp)\n"
        "before the interface line-in. A piezo element is capacitive, so\n"
        "its impedance rises as frequency falls: a 50 kOhm line input\n"
        "forms an accidental ~200 Hz high-pass that guts S1/S2 (20-150\n"
        "Hz), and a 1.5 kOhm mic input forms a ~1 kHz high-pass that\n"
        "eliminates the heart band almost entirely.\n"
        "3) Bare discs ring at 2-6 kHz (metallic coloration); added mass\n"
        "damps it. Expect murmurs to sound harsh through piezo.\n"
        "4) Verify with: better-stethoscope monitor --module piezo"
    )
    gain_advice = (
        "Set gain on the interface (its line-in trim / input knob), "
        "starting around 60 percent; the quality gate flags clipping or "
        "too-quiet takes automatically."
    )
    # NOTE: this front-end ends at a USB audio *interface*: consumer
    # dongles announce themselves as 'USB Audio Adapter', while branded
    # small-format interfaces carry their own names (Behringer U-PHORIA,
    # Focusrite Scarlett, ...). The disc sits in front of a buffer, and
    # the buffer feeds the interface's line-in.
    device_match = (
        "usb audio",
        "audio adapter",
        "behringer",
        "focusrite",
        "scarlett",
        "u-phoria",
        "interface",
    )

    def _iter_blocks(self) -> Generator[np.ndarray, None, None]:
        # WHY no extra stream kwargs: the external buffer (not this code)
        # handles impedance matching, so a plain mono float32 capture is
        # all this front-end needs -- the same canonical loop every
        # sounddevice module uses.
        return self._callback_blocks()