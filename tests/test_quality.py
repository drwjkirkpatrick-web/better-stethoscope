"""Quality gate: verdicts on clean / clipped / quiet / noisy takes."""

import numpy as np
import pytest

from better_stethoscope import filters as F
from better_stethoscope import quality as Q

FS = 48000


class TestGoodTake:
    def test_clean_synthetic_take_is_good(self):
        x = F.demo_heart_signal(bpm=72, seconds=12.0, amplitude=0.3)
        r = Q.analyze(x, FS)
        assert r.verdict == Q.VERDICT_GOOD
        assert r.bpm == pytest.approx(72, abs=4)
        assert r.snr_db > Q.SNR_DB_MIN
        assert r.fraction_20_150_hz > 0.5  # synthetic train is mostly S1/S2 band
        assert r.clip_fraction == 0.0

    def test_one_line_is_informative(self):
        r = Q.analyze(F.demo_heart_signal(seconds=6.0), FS)
        line = r.one_line()
        assert "verdict=good" in line
        assert "bpm" in line


class TestTechnicalFailures:
    def test_clipping_is_technical(self):
        # A device clips at +/-1.0 -- emulate by clipping an overdriven signal.
        x = np.clip(F.demo_heart_signal(seconds=8.0, amplitude=4.0), -1.0, 1.0)
        r = Q.analyze(x, FS)
        assert r.clip_fraction > Q.CLIP_FRACTION_MAX
        assert r.verdict == Q.VERDICT_TECH
        assert any("clipping" in a for a in r.advice)


class TestRepositionFailures:
    def test_silence_is_retry(self):
        x = np.zeros(int(FS * 6), dtype=np.float32)
        r = Q.analyze(x, FS)
        assert r.verdict == Q.VERDICT_RETRY
        assert r.bpm is None

    def test_room_noise_is_retry(self):
        rng = np.random.default_rng(42)
        x = (0.02 * rng.standard_normal(int(FS * 10))).astype(np.float32)
        r = Q.analyze(x, FS)
        assert r.snr_db < Q.SNR_DB_MIN  # noise floor ~= signal level
        assert r.verdict == Q.VERDICT_RETRY

    def test_too_quiet_is_retry(self):
        x = F.demo_heart_signal(seconds=10.0, amplitude=0.001)  # ~ -60 dBFS
        r = Q.analyze(x, FS)
        assert r.rms_dbfs < Q.RMS_DBFS_MIN
        assert r.verdict == Q.VERDICT_RETRY
        assert any("quiet" in a.lower() for a in r.advice)


class TestReportShape:
    def test_to_dict_roundtrip_keys(self):
        r = Q.analyze(F.demo_heart_signal(seconds=5.0), FS)
        d = r.to_dict()
        assert d["verdict"] == r.verdict
        assert set(d) == {
            "duration_s", "peak_dbfs", "rms_dbfs", "noise_floor_dbfs",
            "snr_db", "clip_fraction", "bpm", "bpm_confidence",
            "fraction_20_150_hz", "fraction_150_600_hz", "fraction_above_600_hz",
            "verdict", "advice",
        }

    def test_dbfs_of_empty(self):
        assert Q.dbfs(np.array([], dtype=np.float32)) == -np.inf

    def test_frame_rms_shape(self):
        x = F.demo_heart_signal(seconds=2.0)
        frames = Q.frame_rms_db(x, FS)
        assert frames.ndim == 1
        assert frames.size >= 30  # ~50 ms frames over 2 s