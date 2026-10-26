"""BaseRecorder + registry + usb_mic exemplar (all with the fake backend)."""

import numpy as np
import pytest

from better_stethoscope import recorders as registry
from better_stethoscope.recorders.base import BaseRecorder

from .conftest import FakeInputStream, FS


class DummyRecorder(BaseRecorder):
    """Infinite 40 Hz sine generator -- no backend, deterministic."""

    slug = "dummy"
    display_name = "Dummy"

    def _iter_blocks(self):
        t0 = 0.0
        while True:
            t = (t0 + np.arange(self.blocksize)) / self.sample_rate
            yield (0.2 * np.sin(2 * np.pi * 40.0 * t)).astype(np.float32)
            t0 += self.blocksize


class TestRecord:
    def test_exact_length_and_dtype(self):
        rec = DummyRecorder(sample_rate=FS, blocksize=4096)
        x = rec.record(1.0)
        assert x.size == FS
        assert x.dtype == np.float32
        assert abs(float(np.max(np.abs(x))) - 0.2) < 0.02

    def test_progress_reaches_one(self):
        seen = []
        DummyRecorder().record(0.5, on_progress=seen.append)
        assert seen[-1] == 1.0
        assert seen == sorted(seen)

    def test_dead_stream_raises(self):
        class DeadRecorder(DummyRecorder):
            def _iter_blocks(self):
                return
                yield  # pragma: no cover -- makes this a generator

        with pytest.raises(RuntimeError, match="no audio"):
            DeadRecorder().record(0.1)

    def test_iter_blocks_respects_max_seconds(self):
        rec = DummyRecorder(blocksize=1024)
        total = sum(b.size for b in rec.iter_blocks(max_seconds=0.5))
        assert total >= int(0.5 * FS)
        assert total < int(0.5 * FS) + 1024  # stops at the boundary block


class TestDiscovery:
    def test_discover_filters_and_matches(self, fake_sd):
        from better_stethoscope.recorders import usb_mic

        devices = usb_mic.UsbMicRecorder.discover()
        indices = [d["index"] for d in devices]
        # generic module matches every input device...
        assert set(indices) == {1, 2, 3}
        # ...but never the HDMI output-only device
        assert all(d["name"] != "bcm2835 HDMI 1" for d in devices)
        assert all(d["module"] == "usb_mic" for d in devices)

    def test_device_match_substrings(self, fake_sd):
        from better_stethoscope.recorders import usb_mic

        class Picky(usb_mic.UsbMicRecorder):
            device_match = ("i2s", "dmic")

        found = Picky.discover()
        assert [d["index"] for d in found] == [2]  # only the I2S card

    def test_explicit_device_index_wins(self, fake_sd):
        from better_stethoscope.recorders import usb_mic

        rec = usb_mic.UsbMicRecorder(device_index=3)
        assert rec.resolve_device() == 3
        # without an explicit index, the first discovery match is chosen
        rec2 = usb_mic.UsbMicRecorder()
        assert rec2.resolve_device() == 1

    def test_backend_status_shape(self):
        ok, msg = BaseRecorder.backend_status()
        assert isinstance(ok, bool)
        assert isinstance(msg, str)


class TestStreamConstruction:
    def test_stream_opened_with_expected_kwargs(self, fake_sd):
        from better_stethoscope.recorders import usb_mic

        FakeInputStream.instances.clear()
        rec = usb_mic.UsbMicRecorder(device_index=3, blocksize=1024)
        x = rec.record(0.2)  # fake backend delivers ~1 s, so this completes
        settings = FakeInputStream.instances[-1]
        assert settings["samplerate"] == FS
        assert settings["channels"] == 1
        assert settings["dtype"] == "float32"
        assert settings["device"] == 3
        assert settings["blocksize"] == 1024
        assert x.size == int(0.2 * FS)
        assert 0.4 < float(np.max(np.abs(x))) < 0.6  # 0.5 FS sine came through


class TestRegistry:
    def test_available_contains_generic_module(self):
        classes = registry.available()
        assert "usb_mic" in classes
        assert classes["usb_mic"].slug == "usb_mic"

    def test_get_unknown_slug_raises_with_hint(self):
        with pytest.raises(KeyError, match="Available"):
            registry.get("definitely_not_a_module")

    def test_errors_are_strings_never_crashes(self):
        for reason in registry.errors().values():
            assert isinstance(reason, str) and reason

    def test_all_devices_merges(self, fake_sd):
        devices = registry.all_devices()
        assert any(d["module"] == "usb_mic" for d in devices)
        # HDMI never shows up as an input
        assert all("HDMI" not in d["name"] for d in devices)