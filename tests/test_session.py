"""Session flow: record -> save -> gate -> finalize, without any hardware."""

from typing import Generator

import numpy as np
import pytest
import soundfile as sf

from better_stethoscope import filters as F
from better_stethoscope.config import SessionConfig
from better_stethoscope.recorders.base import BaseRecorder
from better_stethoscope.session import Session

FS = 48000


class FakeHeartRecorder(BaseRecorder):
    """Yields an endless synthetic 72 bpm heart-sound stream, 0.1 s blocks."""

    slug = "fake_heart"
    display_name = "Fake heart (test)"

    def __init__(self, **kw):
        super().__init__(sample_rate=FS, blocksize=4800, **kw)
        self._source = F.demo_heart_signal(bpm=72, seconds=30.0, amplitude=0.3)
        self._pos = 0

    def _iter_blocks(self) -> Generator[np.ndarray, None, None]:
        while True:
            end = self._pos + self.blocksize
            block = self._source[self._pos:end]
            self._pos = end % self._source.size
            if block.size < self.blocksize:  # wrap around the 30 s loop
                self._pos = 0
                block = self._source[: self.blocksize]
            yield block.astype(np.float32)


def _session(tmp_path, interactive=False, label=""):
    config = SessionConfig(
        seconds_per_position=3.0, countdown_seconds=0, output_root=tmp_path / "sessions"
    )
    messages: list[str] = []
    s = Session(
        recorder=FakeHeartRecorder(),
        config=config,
        label=label,
        interactive=interactive,
        echo=messages.append,
    )
    return s, messages


class TestRecordingFlow:
    def test_run_records_each_position(self, tmp_path):
        s, messages = _session(tmp_path)
        takes = s.run(["mitral", "aortic"])
        assert [t.position for t in takes] == ["mitral", "aortic"]
        assert s.meta.positions == ["mitral", "aortic"]

        wavs = sorted(p.name for p in s.dir.glob("*.wav"))
        assert len(wavs) == 2
        assert any("mitral" in w for w in wavs)
        assert any("aortic" in w for w in wavs)

        for take in takes:
            info = sf.info(str(take.path))
            assert info.samplerate == FS
            assert info.subtype == "PCM_24"
            assert take.report.verdict == "good"
            assert take.report.bpm == pytest.approx(72, abs=5)

    def test_retry_appends_not_overwrites(self, tmp_path):
        s, _ = _session(tmp_path)
        s.record_position("mitral")
        s.record_position("mitral")
        names = sorted(p.name for p in s.dir.glob("*.wav"))
        assert len(names) == 2
        assert names[0].endswith("_mitral.wav") and names[1].endswith("_mitral_r2.wav")

    def test_finalize_builds_packet(self, tmp_path):
        s, _ = _session(tmp_path)
        s.run(["mitral"])
        zip_path = s.finalize()
        assert zip_path.exists()
        assert (s.dir / "metadata.json").exists()
        assert (s.dir / "SUMMARY.txt").exists()

    def test_finalize_empty_session_raises(self, tmp_path):
        s, _ = _session(tmp_path)
        with pytest.raises(RuntimeError, match="nothing recorded"):
            s.finalize()

    def test_progress_reaches_one(self, tmp_path):
        s, _ = _session(tmp_path)
        seen = []
        s.record_position("mitral", on_progress=seen.append)
        assert seen[-1] == 1.0


class TestPhiHygiene:
    def test_label_never_touches_filenames_or_dirs(self, tmp_path):
        s, _ = _session(tmp_path, label="chart-114")
        s.run(["mitral"])
        zip_path = s.finalize()

        # label must appear nowhere in any path NAME...
        for p in s.dir.rglob("*"):
            assert "chart-114" not in p.name
        assert "chart-114" not in zip_path.name
        # ...but must be preserved inside metadata.json for the chart
        meta = (s.dir / "metadata.json").read_text()
        assert "chart-114" in meta

    def test_session_dirname_is_timestamp_only(self, tmp_path):
        s, _ = _session(tmp_path)
        assert s.dir.name.count("_") == 1  # YYYY-MM-DD_HHMMSS
        assert "-" in s.dir.name  # the date separators