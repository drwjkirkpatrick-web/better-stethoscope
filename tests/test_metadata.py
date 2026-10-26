"""Metadata conventions: PHI-minimal filenames, JSON round-trip."""

import json
from datetime import datetime

from better_stethoscope import metadata as M


class TestNaming:
    def test_sanitize(self):
        assert M.sanitize("Mitral Area (Apex!)") == "mitral_area_apex"
        assert M.sanitize("Erb's point") == "erb_s_point"

    def test_session_dirname_has_no_patient_data(self):
        when = datetime(2026, 8, 26, 10, 15, 30)
        assert M.session_dirname(when) == "2026-08-26_101530"

    def test_recording_filename(self):
        when = datetime(2026, 8, 26, 10, 15, 30)
        assert M.recording_filename("mitral", when) == "20260826_101530_mitral.wav"
        assert M.recording_filename("mitral", when, attempt=2) == "20260826_101530_mitral_r2.wav"
        assert M.recording_filename("Erb's point", when, ext="flac").endswith("erb_s_point.flac")

    def test_no_position_label_in_filename_leaks(self):
        """Structural PHI guarantee: filenames can only hold position + time."""
        when = datetime(2026, 1, 1)
        name = M.recording_filename("mitral", when)
        assert "patient" not in name.lower()
        assert name.count("_") == 2


class TestMetaObjects:
    def test_session_meta_to_dict(self):
        meta = M.SessionMeta(
            started_at="2026-08-26T10:15:30-07:00",
            session_id="2026-08-26_101530",
            recorder="electret",
            recorder_display="Electret-in-tubing",
            device_name="C-Media USB Audio Adapter",
            patient_label="chart-114",
            positions=["mitral", "aortic"],
        )
        d = meta.to_dict()
        assert d["recorder"] == "electret"
        assert d["positions"] == ["mitral", "aortic"]

    def test_recording_meta_defaults(self):
        meta = M.RecordingMeta(
            position="mitral", position_name="Mitral area (apex)",
            started_at="now", duration_s=15.0, filename="x.wav",
        )
        assert meta.bpm is None
        assert meta.advice == []

    def test_json_roundtrip(self, tmp_path):
        path = tmp_path / "meta.json"
        payload = {"session_id": "s", "label": "chart-114", "nested": {"a": 1}}
        M.write_json(path, payload)
        assert M.load_json(path) == payload
        # pretty-printed, trailing newline
        text = path.read_text()
        assert text.endswith("\n") and json.loads(text)["nested"]["a"] == 1

    def test_now_iso_is_parseable(self):
        parsed = datetime.fromisoformat(M.now_iso())
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() is not None