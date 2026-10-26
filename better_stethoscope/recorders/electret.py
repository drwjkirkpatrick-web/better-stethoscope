"""Electret capsule sealed into stethoscope tubing -- the low-cost DIY build.

This is the classic five-dollar digital stethoscope: a bare electret
condenser capsule pressed into the stethoscope's own tubing and fed by a
cheap USB dongle. It is the front-end to reach for when you want heart
sounds on a Pi for the price of a coffee.

COUPLING (the build):
    1) Cut the stethoscope tube about 5 cm from the chestpiece stem --
       published builds keep roughly 5 cm of 6 mm inner-diameter tubing
       between the stem and the capsule.
    2) Insert a bare electret capsule into the tubing end. Any 6 mm
       lavalier capsule works; a CMC-9745-44P or similar costs 1-2 USD.
    3) Seal the joint (heat-shrink, silicone, or foam) so the only
       acoustic path is chestpiece -> air column -> capsule. A leaky
       joint lets chest energy escape and room noise in.
    4) Connect the capsule's two leads to the mic input of a C-Media
       CM108(B) USB sound-card dongle. The dongle's plug-in-power mic
       bias supplies the capsule's operating current, and its USB side
       is what the Pi enumerates as the capture device.

    Because the sealed air column couples the capsule directly to the
    chestpiece, this front-end captures the S1/S2 fundamentals
    (20-150 Hz) remarkably well for the money.

GAIN:
    The capsule output is faint -- start at maximum input gain in
    alsamixer (F4) and back off only if the quality gate reports
    clipping.

NOTE: the full engineering write-up with prose citations lives in
docs/microphone-differential.md.
"""

from __future__ import annotations

from typing import Iterator

import numpy as np

from .base import BaseRecorder


class ElectretRecorder(BaseRecorder):
    """Bare electret capsule sealed into the stethoscope tube (DIY build).

    A 6 mm electret capsule (any lavalier type; a CMC-9745-44P is the
    usual 1-2 USD choice) sits about 5 cm from the chestpiece stem in
    6 mm inner-diameter tubing, sealed so the only acoustic path is the
    sealed air column from chestpiece to capsule. A C-Media CM108(B)
    USB dongle powers the capsule through its plug-in-power mic bias and
    gives the Pi a USB capture device. The direct air coupling is why
    the S1/S2 fundamentals (20-150 Hz) survive; the trade-off is a very
    low signal level, so plan on near-maximum OS input gain.
    """

    slug = "electret"
    display_name = "DIY electret capsule in stethoscope tubing"
    description = (
        "The classic low-cost DIY digital stethoscope: a bare electret "
        "capsule (e.g. a 1-2 USD CMC-9745-44P or any 6 mm lavalier "
        "capsule) sealed into the stethoscope tube about 5 cm from the "
        "chestpiece stem, powered and captured through a C-Media CM108(B) "
        "USB dongle's plug-in-power mic input. The sealed air column "
        "couples straight to the chestpiece, so S1/S2 fundamentals "
        "(20-150 Hz) come through well; expect to run near-maximum gain."
    )
    hardware_notes = (
        "1) Cut the stethoscope tube ~5 cm from the chestpiece stem "
        "(published builds use ~5 cm of 6 mm ID tubing).\n"
        "2) Insert a bare 6 mm electret capsule (e.g. CMC-9745-44P, "
        "1-2 USD) into the tubing end.\n"
        "3) Seal with heat, silicone, or foam so the only acoustic path "
        "is tube-to-capsule -- no leaks.\n"
        "4) Wire the capsule to a C-Media CM108(B) dongle's mic input; "
        "its plug-in-power bias runs the capsule, and the dongle shows "
        "up as the Pi's USB capture device.\n"
        "5) Verify with: better-stethoscope monitor --module electret"
    )
    gain_advice = (
        "Start at maximum input gain in alsamixer (F4), then back off "
        "if the quality gate reports clipping -- the sealed capsule's "
        "output is faint by nature."
    )
    # WHY these tokens: the CM108-family dongles enumerate under several
    # names ("C-Media Electronics Inc. ...", "USB PnP Sound Device", plain
    # "USB Audio Adapter"), so match them all -- but NOT the Pi's I2S cards
    # or HDMI, which never carry this front-end.
    device_match = ("c-media", "cm108", "usb pnp", "audio adapter", "usb audio")

    def _iter_blocks(self) -> Iterator[np.ndarray]:
        # Same canonical capture loop as every sounddevice module: the
        # callback-queue pattern in base._callback_blocks decouples the
        # PortAudio callback from our consumer so nothing drops frames.
        return self._callback_blocks()