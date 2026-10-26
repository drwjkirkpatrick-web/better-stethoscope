"""ElectretRecorder: discovery, stream construction, record, registry.

All against the fake sounddevice backend (see tests/conftest.py), so
these tests run on any machine without audio hardware. Record durations
stay <= 0.2 s because the fake backend delivers only ~1 s of audio.
"""

import numpy as np

from better_stethoscope import recorders as registry
from better_stethoscope.recorders import electret

from .conftest import FakeInputStream, FS


class TestDiscovery:
    def test_discover_returns_cm108_and_pnp_only(self, fake_sd):
        devices = electret.ElectretRecorder.discover()
        # C-Media dongle (1) and generic USB PnP card (3); the I2S card
        # (2) is not this front-end, HDMI (0) is not even an input.
        assert [d["index"] for d in devices] == [1, 3]
        assert all(d["module"] == "electret" for d in devices)

    def test_discover_never_returns_hdmi(self, fake_sd):
        devices = electret.ElectretRecorder.discover()
        assert devices  # sanity: something was found before we exclude
        assert all("HDMI" not in d["name"] for d in devices)


class TestStreamConstruction:
    def test_stream_opened_with_expected_kwargs(self, fake_sd):
        FakeInputStream.instances.clear()
        rec = electret.ElectretRecorder(device_index=3, blocksize=1024)
        x = rec.record(0.2)  # fake backend delivers ~1 s, so this completes
        settings = FakeInputStream.instances[-1]
        assert settings["samplerate"] == FS
        assert settings["channels"] == 1
        assert settings["dtype"] == "float32"
        assert settings["device"] == 3
        assert x.size == int(0.2 * FS)


class TestRecord:
    def test_exact_length_dtype_and_peak(self, fake_sd):
        rec = electret.ElectretRecorder(device_index=3, blocksize=1024)
        x = rec.record(0.2)
        # exactly the requested number of samples, float32, 0.5 FS sine
        assert x.size == int(0.2 * 48000)
        assert x.dtype == np.float32
        assert 0.4 < float(np.max(np.abs(x))) < 0.6


class TestRegistry:
    def test_registry_exposes_electret_class(self):
        # The registry imports modules lazily, so 'electret' only shows
        # up once better_stethoscope/recorders/electret.py exists.
        classes = registry.available()
        assert classes["electret"] is electret.ElectretRecorder
        assert classes["electret"].slug == "electret"