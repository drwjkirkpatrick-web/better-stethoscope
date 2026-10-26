"""Report layer: WAV/FLAC round-trips, figures, summary, packet assembly."""

import zipfile
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from better_stethoscope import filters as F
from better_stethoscope import quality as Q
from better_stethoscope import report as R
from better_stethoscope.metadata import RecordingMeta, now_iso

FS = 48000


def _take(tmp_path, name="20260826_101530_mitral", position="mitral", seconds=2.0):
    audio = F.demo_heart_signal(bpm=72, seconds=seconds, amplitude=0.3)
    wav = R.save_wav(tmp_path / f"{name}.wav", audio, FS)
    report = Q.analyze(audio, FS)
    meta = RecordingMeta(
        position=position,
        position_name="Mitral area (apex)",
        started_at=now_iso(),
        duration_s=seconds,
        filename=wav.name,
        bpm=report.bpm,
        bpm_confidence=report.bpm_confidence,
        verdict=report.verdict,
        advice=report.advice,
    )
    return SimpleNamespace(path=wav, report=report, meta=meta)


class TestSave:
    def test_wav_roundtrip_24bit(self, tmp_path):
        audio = F.demo_heart_signal(seconds=1.0)
        path = R.save_wav(tmp_path / "t.wav", audio, FS)
        back, sr = sf.read(str(path), dtype="float32")
        assert sr == FS
        assert back.size == audio.size
        info = sf.info(str(path))
        assert info.subtype == "PCM_24"

    def test_flac_lossless_matches_wav(self, tmp_path):
        audio = F.demo_heart_signal(seconds=1.0)
        R.save_wav(tmp_path / "t.wav", audio, FS)
        R.save_flac(tmp_path / "t.flac", audio, FS)
        wav_back, _ = sf.read(str(tmp_path / "t.wav"), dtype="float32")
        flac_back, _ = sf.read(str(tmp_path / "t.flac"), dtype="float32")
        # FLAC is lossless: samples agree to the 24-bit quantization floor.
        assert np.max(np.abs(wav_back - flac_back)) < 1e-6


class TestFigures:
    def test_figure_png_written(self, tmp_path):
        audio = F.demo_heart_signal(seconds=2.0)
        path = R.figure_png(audio, FS, tmp_path / "fig.png", title="mitral test")
        assert path is not None
        assert path.stat().st_size > 5_000


class TestTextArtifacts:
    def test_summary_content(self, tmp_path):
        take = _take(tmp_path)
        path = R.write_summary(
            tmp_path / "SUMMARY.txt",
            {"session_id": "s1", "started_at": "2026-08-26", "recorder": "electret",
             "recorder_display": "Electret-in-tubing", "sample_rate_hz": FS,
             "subtype": "PCM_24", "patient_label": "chart-114"},
            [take.meta.to_dict()],
        )
        text = path.read_text()
        assert "chart-114" in text            # label DOES belong in the summary...
        assert "Mitral area" in text
        assert "verdict=good" in text
        assert take.path.name in text

    def test_physician_readme_mentions_positions_and_disclaimer(self, tmp_path):
        path = R.write_physician_readme(tmp_path / "README.txt")
        text = path.read_text()
        for token in ("aortic", "mitral", "Disclaimer", "flac"):
            assert token in text


class TestPacket:
    def test_packet_contains_everything(self, tmp_path):
        session_dir = tmp_path / "2026-08-26_101530"
        session_dir.mkdir()
        take = _take(session_dir)
        meta = {"session_id": session_dir.name, "started_at": "x", "recorder": "electret"}
        from better_stethoscope.metadata import write_json

        write_json(session_dir / "metadata.json", meta)
        zip_path = R.build_physician_packet(session_dir, meta, [take])

        assert zip_path.exists()
        assert zip_path.name == "2026-08-26_101530_physician_packet.zip"
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        assert any(n.endswith(".flac") for n in names)
        assert any(n.endswith(".png") for n in names)
        assert any(n.endswith("SUMMARY.txt") for n in names)
        assert any(n.endswith("README_for_physician.txt") for n in names)
        assert any(n.endswith("metadata.json") for n in names)
        # WAV masters stay OUT of the packet (they remain in the session dir)
        assert not any(n.endswith(".wav") for n in names)