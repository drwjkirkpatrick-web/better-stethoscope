"""PiezoContactRecorder: discovery, stream construction, capture, registry."""

import numpy as np

from better_stethoscope import recorders as registry
from better_stethoscope.recorders.piezo import PiezoContactRecorder

from .conftest import FS, FakeInputStream


class TestDiscovery:
    def test_discover_returns_exactly_the_usb_audio_adapter(self, fake_sd):
        found = PiezoContactRecorder.discover()
        # WHY [1] only: the C-Media dongle's name carries 'usb audio' AND
        # 'audio adapter', while the I2S card and the generic
        # 'USB PnP Sound Device' match none of the substrings.
        assert [d["index"] for d in found] == [1]
        assert all(d["module"] == "piezo" for d in found)


class TestStreamConstruction:
    def test_stream_opened_with_expected_kwargs(self, fake_sd):
        # NOTE: no explicit device_index, so the recorder resolves the
        # device via discovery -- the first match, index 1.
        FakeInputStream.instances.clear()
        rec = PiezoContactRecorder()
        rec.record(0.25)  # stream opens lazily on first pull
        settings = FakeInputStream.instances[-1]
        assert settings["samplerate"] == FS
        assert settings["channels"] == 1
        assert settings["dtype"] == "float32"
        assert settings["device"] == 1


class TestCapture:
    def test_record_returns_expected_samples(self, fake_sd):
        rec = PiezoContactRecorder()
        x = rec.record(0.25)
        assert x.size == int(0.25 * FS)
        assert x.dtype == np.float32
        # WHY 0.4..0.6: the fake backend emits a 0.5 FS sine, so a healthy
        # capture must pass it through at (nearly) full level.
        peak = float(np.max(np.abs(x)))
        assert 0.4 < peak < 0.6


class TestRegistry:
    def test_registry_maps_slug_to_this_class(self):
        assert registry.available()["piezo"] is PiezoContactRecorder