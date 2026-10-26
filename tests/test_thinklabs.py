"""ThinklabsLineInRecorder tests: discovery, wiring, capture, registry.

All backend-dependent tests use the auto-injected ``fake_sd`` fixture
from tests/conftest.py -- no Thinklabs One and no USB adapter needed.
Durations stay at or below 0.5 s because the fake backend delivers only
~1 s of synthetic audio per stream.
"""

import numpy as np

from better_stethoscope import recorders as registry
from better_stethoscope.recorders.thinklabs import ThinklabsLineInRecorder

from .conftest import FakeInputStream, FS


class TestDiscovery:
    def test_discover_returns_line_in_devices_exactly(self, fake_sd):
        devices = ThinklabsLineInRecorder.discover()
        # C-Media USB adapter and the USB PnP device advertise line-capable
        # USB ADCs; HDMI (output-only) and the I2S MEMS card never match.
        assert [d["index"] for d in devices] == [1, 3]
        assert all(d["module"] == "thinklabs" for d in devices)

    def test_device_resolution_order(self, fake_sd):
        # explicit constructor arg wins...
        assert ThinklabsLineInRecorder(device_index=3).resolve_device() == 3
        # ...otherwise the first discovery match (the C-Media adapter) is used
        assert ThinklabsLineInRecorder().resolve_device() == 1


class TestStreamConstruction:
    def test_stream_opened_with_line_in_settings(self, fake_sd):
        FakeInputStream.instances.clear()
        rec = ThinklabsLineInRecorder(device_index=1)
        rec.record(0.2)  # fake backend delivers ~1 s, so this completes
        settings = FakeInputStream.instances[-1]
        assert settings["samplerate"] == FS
        assert settings["channels"] == 1
        assert settings["dtype"] == "float32"
        assert settings["device"] == 1  # explicit index, not a default lookup


class TestRecord:
    def test_record_returns_expected_audio(self, fake_sd):
        rec = ThinklabsLineInRecorder(device_index=1)
        x = rec.record(0.2)
        assert x.dtype == np.float32
        assert x.size == int(0.2 * FS)
        # the fake backend's 0.5 FS sine must come through the line-in
        # chain essentially untouched (LINE IN adds no gain of its own)
        assert 0.4 < float(np.max(np.abs(x))) < 0.6


class TestRegistry:
    def test_registry_maps_slug_to_class(self):
        classes = registry.available()
        assert classes["thinklabs"] is ThinklabsLineInRecorder