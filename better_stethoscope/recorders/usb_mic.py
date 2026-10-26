"""Generic USB microphone front-end -- the "whatever you already have" module.

This is the fallback path: any USB microphone, lavalier, headset mic, or
USB audio adapter the Pi enumerates through PortAudio. It is the reference
implementation of the BaseRecorder contract (the other modules follow this
file's shape), and it is deliberately the most permissive matcher.

COUPLING (making it actually hear the heart):
    A bare USB mic pointed at the chest hears almost nothing -- body sounds
    are too quiet and too low. Couple it acoustically like the classic Nuts
    & Volts / physiology-journal builds: press the mic capsule into a short
    piece of stethoscope tubing (or heat the tube and insert the mic), with
    the chestpiece on the other end. See docs/microphone-differential.md
    for the build that published this coupling method.

GAIN:
    Set OS input capture gain to ~2/3 in alsamixer (F4) as a start; the
    quality gate will tell you if you clipped or if you are too quiet.

TESTS: tests/test_recorders.py exercises discovery and stream construction
with a fake backend (see tests/conftest.py); no hardware needed.
"""

from __future__ import annotations

from typing import Iterator

import numpy as np

from .base import BaseRecorder


class UsbMicRecorder(BaseRecorder):
    """Any USB microphone or USB audio adapter (match-anything fallback)."""

    slug = "usb_mic"
    display_name = "Generic USB microphone / USB audio adapter"
    description = (
        "Any USB mic or USB sound card the Pi enumerates. Best used with "
        "the mic capsule coupled into stethoscope tubing; otherwise expect "
        "only room audio. This is the module of last resort when no more "
        "specific front-end is connected."
    )
    hardware_notes = (
        "1) Plug the USB mic/adapter into the Pi.\n"
        "2) For heart sounds, couple the capsule into ~5 cm of stethoscope "
        "tubing sealed against the chestpiece stem.\n"
        "3) Verify with: better-stethoscope monitor --module usb_mic"
    )
    gain_advice = (
        "Start at ~2/3 input gain (alsamixer F4, or your adapter's knob). "
        "The quality gate flags clipping/too-quiet automatically."
    )
    # Empty match list = accept any input device (the "match anything" rule
    # documented in base.py).
    device_match = ()

    def _iter_blocks(self) -> Iterator[np.ndarray]:
        return self._callback_blocks()