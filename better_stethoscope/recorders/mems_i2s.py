"""I2S MEMS microphone front-end -- a bare chip on the Pi's own audio bus.

An INMP441 / SPH0645 / ICS-43434 MEMS microphone breakout wired straight
to the Raspberry Pi's I2S/PCM peripheral: no USB dongle, no sound card,
no adapter in between -- the Pi itself becomes the audio interface. That
makes this the most integrated front-end in the set and the cheapest to
leave permanently wired inside a case, but it is also the weakest for
low-frequency heart work; read LIMITATIONS before trusting a faint S3/S4
from this path.

WIRING (Pi 40-pin header):
    mic VDD (3V)  -> Pi 3.3V
    mic GND       -> Pi GND
    mic BCLK/SCK  -> GPIO18      (physical pin 12)
    mic LRCL/WS   -> GPIO19      (physical pin 35)
    mic DOUT/SD   -> GPIO20      (physical pin 38)
    mic L/R       -> Pi GND      (selects the LEFT channel)
    WHY the L/R pin must be grounded: left floating, the mic drives
    garbage into BOTH time slots and the simple overlay below has no way
    to sort it out. Tie L/R to GND, capture the left channel, done.

COUPLING (making it hear the heart):
    The mic is a bare chip with a tiny port -- no chestpiece of its own.
    The best coupling is the same trick as the electret build: press the
    mic port into a short piece of sealed tubing fitted over the
    chestpiece stem, so the diaphragm's air column drives the port
    directly with no leaks.

ENABLE (device-tree overlay steps):
    1. Open /boot/firmware/config.txt on Bookworm (older OS releases
       keep it at /boot/config.txt).
    2. Add two lines:
           dtparam=i2s=on
           dtoverlay=googlevoicehat-soundcard
    3. Reboot. The card appears as snd_rpi_i2s_card -- a 24-bit capture
       that ALSA presents as S32_LE, because the driver pads each
       24-bit sample into a 32-bit word.

GAIN (fixed hardware plus the softvol fallback):
    There is NO hardware gain control on this front-end: the capsule's
    sensitivity is fixed and the overlay exposes no analog volume stage,
    so capture level is whatever the mic gives you. If takes come out
    too quiet, the sanctioned fallback is ALSA softvol: a 'Boost'
    capture control, adjustable up to about +30 dB, applied digitally
    behind the driver. Raise it only as far as the quality gate needs --
    softvol rescales samples, it cannot recover information that never
    reached the ADC, so fix acoustic coupling first. Check the level
    outside this app with:
        arecord -D plughw:1,0 -c1 -r 48000 -f S32_LE -t wav test.wav
    (the card number can differ; `arecord -l` lists it).

LIMITATIONS (60 Hz roll-off -- read this first):
    MEMS microphones roll off below their flat band, and the INMP441's
    published -3 dB low corner sits at 60 Hz. That means much of the
    S1/S2 fundamental energy (20-60 Hz) is attenuated before it ever
    reaches the ADC. Of the five front-ends this one is the WEAKEST for
    low-frequency heart-sound fidelity: fine for heart rate, murmurs and
    lung sounds, worst for S3/S4 gallops. Treat a faint low-frequency
    finding from this module as unconfirmed until a chest-coupled
    front-end agrees.

NOTE:
    See docs/microphone-differential.md for how this front-end compares
    with the other microphones in the set.

TESTS: tests/test_mems_i2s.py exercises discovery and stream construction
with a fake backend (see tests/conftest.py); no hardware needed.
"""

from __future__ import annotations

from typing import Generator

import numpy as np

from .base import BaseRecorder


class MemsI2sRecorder(BaseRecorder):
    """INMP441 / SPH0645 / ICS-43434 MEMS mic on the Pi's I2S/PCM bus."""

    slug = "mems_i2s"
    display_name = "I2S MEMS microphone (INMP441 / SPH0645 on the Pi header)"
    description = (
        "A bare INMP441 / SPH0645 / ICS-43434 MEMS microphone wired "
        "directly to the Pi's I2S/PCM peripheral -- no USB adapter at "
        "all. The most integrated front-end of the set, but its 60 Hz "
        "low-frequency roll-off makes it the weakest for S1/S2 "
        "fundamentals: use it for rate, murmurs and lung sounds, and "
        "reach for a chest-coupled front-end before calling an S3/S4."
    )
    hardware_notes = (
        "1) Wire the breakout to the 40-pin header: VDD(3V) -> 3.3V,\n"
        "GND -> GND, BCLK/SCK -> GPIO18 (pin 12), LRCL/WS -> GPIO19\n"
        "(pin 35), DOUT/SD -> GPIO20 (pin 38), and L/R -> GND to select\n"
        "the LEFT channel -- a floating L/R pin outputs garbage on both\n"
        "slots.\n"
        "2) Enable the bus in /boot/firmware/config.txt (older OS:\n"
        "/boot/config.txt): add 'dtparam=i2s=on' and\n"
        "'dtoverlay=googlevoicehat-soundcard', then reboot; the card\n"
        "shows up as snd_rpi_i2s_card.\n"
        "3) The mic is bare -- no chestpiece. Press the mic port into\n"
        "short sealed tubing fitted to the chestpiece stem (as with the\n"
        "electret build) so the diaphragm column drives the port.\n"
        "4) Remember the 60 Hz roll-off: attenuated S1/S2 fundamentals,\n"
        "worst front-end of the five for S3/S4 gallops.\n"
        "5) Verify with: better-stethoscope monitor --module mems_i2s"
    )
    gain_advice = (
        "No hardware gain exists here -- capture level is fixed by the "
        "capsule. If takes are too quiet, add ALSA softvol (a 'Boost' "
        "capture control, up to about +30 dB) as the sanctioned "
        "fallback, and test with: arecord -D plughw:1,0 -c1 -r 48000 "
        "-f S32_LE -t wav test.wav (card number per `arecord -l`). The "
        "quality gate flags clipping/too-quiet automatically."
    )
    # NOTE: the googlevoicehat overlay names its card snd_rpi_i2s_card,
    # which PortAudio usually shows as 'snd_rpi_i2s_card: - (dmic)'. The
    # tokens below cover the variants seen in the wild (plain 'i2s'
    # boards, dmic-style overlays, other snd_rpi_* soundcard overlays).
    device_match = ("i2s", "dmic", "snd_rpi", "googlevoicehat")

    def _iter_blocks(self) -> Generator[np.ndarray, None, None]:
        # WHY no extra stream kwargs: the overlay exposes a plain ALSA
        # capture device (24-bit samples padded to S32_LE, which
        # sounddevice hands over as float32 after rescaling), so the
        # canonical callback loop in base.py opens it unmodified --
        # mono, 48 kHz, float32.
        return self._callback_blocks()