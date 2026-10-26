"""Thinklabs One digital stethoscope used as the front-end via line input.

The One is a complete electrostatic-diaphragm digital stethoscope: its
chestpiece senses body sound with an electromagnetic diaphragm, applies
more than 100x of clean internal amplification, and offers five tunable
bandpass filters. It then plays the result out of a plain 3.5mm
headphone jack -- there is no SDK, no USB protocol, no API to talk to.
From the Pi's point of view the One is just an external microphone that
happens to be the best heart-sound sensor on the bench. This is the
premium-quality path: the reference-grade front-end that the DIY
modules in this package are trying to approximate.

SIGNAL CHAIN (One -> 3.5mm -> LINE IN -> Pi):
    One chestpiece (electromagnetic diaphragm pressed directly on skin)
      -> internal >100x amplifier and filter stage
      -> 3.5mm analog output (4-conductor jack, headphone-level, about
         3 V peak-to-peak into a low-impedance driver)
      -> patch cable into a USB audio adapter's LINE IN jack
      -> USB ADC (line level, unity gain) -> PortAudio stream at
         48 kHz, mono, float32 -- digitized by the Pi, nothing else.

GAIN:
    The One's own volume knob IS the gain control for this chain -- the
    adapter's line input adds nothing. Start with the One's volume at
    2-4 on its 1-10 scale and watch the Pi-side quality gate: a peak
    near 0 dBFS means the converter is being overdriven, so back the
    knob off.

WHY LINE NOT MIC:
    The signal leaving the One has already been amplified about 100x;
    it is headphone-level output, strong enough to drive a
    low-impedance driver. A USB adapter's MIC jack expects a few
    millivolts from a passive capsule and applies its own preamp gain on
    top. Feeding it the One's ~3 V peak-to-peak output would
    double-amplify and overdrive the input, slamming it into clipping
    before the ADC ever sees the signal. Use LINE IN, which is unity.

NOTE: leave the One's internal bandpass filters on the default setting
so post-filtering stays in our pipeline (filters.py owns the 20-2000 Hz
heart band); the recorder should receive the full-band signal. See
docs/microphone-differential.md for how this front-end compares with
the DIY microphones.

TESTS: tests/test_thinklabs.py exercises discovery, stream
construction, capture and registry wiring against the fake backend in
tests/conftest.py -- no hardware needed.
"""

from __future__ import annotations

from typing import Generator

import numpy as np

from .base import BaseRecorder


class ThinklabsLineInRecorder(BaseRecorder):
    """Thinklabs One's analog output captured through a USB line input."""

    slug = "thinklabs"
    display_name = "Thinklabs One -> USB line input"
    description = (
        "The reference-grade front-end: a commercial electrostatic-diaphragm "
        "digital stethoscope whose 3.5mm headphone-level output feeds a USB "
        "adapter's LINE IN. Over 100x of amplification and five bandpass "
        "filters live inside the One itself; the Pi just digitizes the "
        "already-clean line-level signal."
    )
    hardware_notes = (
        "1) Place the One's electromagnetic-diaphragm chestpiece directly on "
        "skin at the auscultation landmark -- no shirt in between.\n"
        "2) Run a patch cable from the One's 3.5mm output (4-conductor jack, "
        "headphone-level, ~3 V peak-to-peak into a low-impedance driver) to "
        "the USB audio adapter's LINE IN jack -- never the MIC jack.\n"
        "3) Leave the One's internal filters on default; our pipeline does "
        "its own post-filtering.\n"
        "4) Verify with: better-stethoscope monitor --module thinklabs"
    )
    gain_advice = (
        "The One's volume knob is the only gain control in this chain (line "
        "input is unity). Start at 2-4 on its 1-10 scale; if the quality "
        "gate reports a peak near 0 dBFS, back the knob off."
    )
    # NOTE: match USB ADC adapters and anything advertising a line input;
    # the on-board I2S MEMS card and HDMI audio belong to other modules.
    # Substrings are compared case-insensitively by BaseRecorder._matches.
    device_match = ("usb audio", "audio adapter", "c-media", "cm108", "usb pnp", "line")

    def _iter_blocks(self) -> Generator[np.ndarray, None, None]:
        # WHY _callback_blocks: once the One's signal reaches the adapter's
        # line input it behaves exactly like any other USB input, so the
        # canonical PortAudio callback-queue loop from base.py is all we
        # need -- the One did the sensor work, we just digitize it.
        return self._callback_blocks()