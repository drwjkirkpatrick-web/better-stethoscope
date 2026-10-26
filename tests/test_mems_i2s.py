"""MemsI2sRecorder: discovery, stream construction, capture, registry."""

import numpy as np

from better_stethoscope import recorders as registry
from better_stethoscope.recorders.mems_i2s import MemsI2sRecorder

from .conftest import FS, FakeInputStream


class TestDiscovery:
    def test_discover_returns_exactly_the_i2s_card(self, fake_sd):
        found = MemsI2sRecorder.discover()
        # WHY [2] only: the I2S card's name 'snd_rpi_i2s_card: - (dmic)'
        # carries 'i2s', 'dmic' and 'snd_rpi', while the C-Media dongle
        # and the 'USB PnP Sound Device' match none of the substrings.
        assert [d["index"] for d in found] == [2]
        assert all(d["module"] == "mems_i2s" for d in found)


class TestStreamConstruction:
    def test_stream_opened_with_expected_kwargs(self, fake_sd):
        # NOTE: device_index=2 pins the I2S card explicitly, exactly how
        # the CLI opens it after discovery.
        FakeInputStream.instances.clear()
        rec = MemsI2sRecorder(device_index=2)
        rec.record(0.25)  # stream opens lazily on first pull
        settings = FakeInputStream.instances[-1]
        assert settings["samplerate"] == FS
        assert settings["channels"] == 1
        assert settings["dtype"] == "float32"
        assert settings["device"] == 2


class TestCapture:
    def test_record_returns_expected_samples(self, fake_sd):
        rec = MemsI2sRecorder(device_index=2)
        x = rec.record(0.25)
        assert x.size == int(0.25 * FS)
        assert x.dtype == np.float32
        # WHY 0.4..0.6: the fake backend emits a 0.5 FS sine, so a
        # healthy capture must pass it through at (nearly) full level.
        peak = float(np.max(np.abs(x)))
        assert 0.4 < peak < 0.6


class TestRegistry:
    def test_registry_maps_slug_to_this_class(self):
        assert registry.available()["mems_i2s"] is MemsI2sRecorder