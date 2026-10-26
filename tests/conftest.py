"""Shared test fixtures: a fake sounddevice backend.

WHY: the recorder modules import ``sounddevice`` *lazily inside methods*,
which means a test can swap ``sys.modules["sounddevice"]`` for this fake
and the module under test will happily use it -- no audio hardware, no
PortAudio, deterministic and instant.

FakeInputStream captures every constructor kwarg (so tests can assert how
the stream was opened) and, on ``start()``/``__enter__``, pushes roughly
ONE SECOND of synthetic 40 Hz sine (at half full scale) through the
PortAudio-style callback. Consequence: ``recorder.record(seconds)`` works
in tests only for ``seconds <= ~0.9``. Keep test durations short.
"""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest

FS = 48000

# A canned PortAudio device list resembling a real Pi:
#  - HDMI audio (outputs only) -- must be excluded from discovery
#  - a C-Media USB dongle (the classic electret/adapter path)
#  - the I2S MEMS card created by the googlevoicehat overlay
#  - a generic USB PnP sound device
FAKE_DEVICES = [
    {"index": 0, "name": "bcm2835 HDMI 1", "max_input_channels": 0, "max_output_channels": 4},
    {
        "index": 1,
        "name": "C-Media Electronics Inc. USB Audio Adapter",
        "max_input_channels": 1,
        "max_output_channels": 2,
    },
    {
        "index": 2,
        "name": "snd_rpi_i2s_card: - (dmic)",
        "max_input_channels": 2,
        "max_output_channels": 2,
    },
    {
        "index": 3,
        "name": "USB PnP Sound Device",
        "max_input_channels": 1,
        "max_output_channels": 2,
    },
]


class FakeInputStream:
    """Stands in for sounddevice.InputStream; records kwargs, emits audio."""

    instances: "list[dict]" = []  # every constructor call, newest last

    def __init__(self, samplerate=48000, channels=1, dtype="float32",
                 device=None, blocksize=None, callback=None, **extra):
        self.settings = {
            "samplerate": samplerate,
            "channels": channels,
            "dtype": dtype,
            "device": device,
            "blocksize": blocksize,
            "callback": callback,
            "extra": extra,
        }
        FakeInputStream.instances.append(self.settings)

    # -- context manager (how _callback_blocks opens the stream) ---------
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
        return False

    def start(self):
        """Deliver ~1 s of 40 Hz sine at 0.5 FS in blocksize-sized chunks."""
        cb = self.settings["callback"]
        sr = int(self.settings["samplerate"])
        block = int(self.settings["blocksize"] or 1024)
        channels = int(self.settings["channels"] or 1)
        produced = 0
        while produced < sr:  # one second total
            frames = min(block, sr - produced)
            t = (np.arange(frames) + produced) / sr
            mono = (0.5 * np.sin(2 * np.pi * 40.0 * t)).astype(np.float32)
            data = np.repeat(mono.reshape(frames, 1), channels, axis=1)
            cb(data, frames, None, None)
            produced += frames

    def stop(self):
        pass

    def close(self):
        pass


@pytest.fixture
def fake_sd(monkeypatch):
    """Replace sys.modules['sounddevice'] with the fake module."""
    FakeInputStream.instances.clear()
    mod = types.ModuleType("sounddevice")
    # setattr keeps static checkers happy: dynamic attributes on ModuleType.
    setattr(mod, "InputStream", FakeInputStream)
    setattr(mod, "__version__", "fake-0.0.0")
    setattr(mod, "query_devices", lambda: [dict(d) for d in FAKE_DEVICES])
    setattr(mod, "default", types.SimpleNamespace(device=[3, 0], samplerate=FS))
    monkeypatch.setitem(sys.modules, "sounddevice", mod)
    return mod