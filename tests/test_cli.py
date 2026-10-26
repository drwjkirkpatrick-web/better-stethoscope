"""CLI: parser wiring and the hardware-free commands end to end."""

import pytest

from better_stethoscope import cli
from better_stethoscope import filters as F
from better_stethoscope.report import save_wav


class TestDemo:
    def test_demo_passes_and_prints(self, capsys):
        assert cli.main(["demo"]) == 0
        out = capsys.readouterr().out
        assert "install OK" in out
        assert "verdict=good" in out

    def test_demo_can_save_wav(self, tmp_path, capsys):
        out_wav = tmp_path / "demo.wav"
        assert cli.main(["demo", "--out", str(out_wav)]) == 0
        assert out_wav.exists()


class TestAnalyze:
    def test_analyze_good_wav_exit_zero(self, tmp_path, capsys):
        wav = save_wav(tmp_path / "good.wav", F.demo_heart_signal(seconds=6.0, amplitude=0.3), 48000)
        assert cli.main(["analyze", str(wav)]) == 0
        out = capsys.readouterr().out
        assert "verdict=good" in out
        assert "band energy" in out

    def test_analyze_silence_exit_one(self, tmp_path):
        import numpy as np

        wav = save_wav(tmp_path / "silent.wav", np.zeros(48000 * 3, dtype=np.float32), 48000)
        assert cli.main(["analyze", str(wav)]) == 1

    def test_analyze_writes_figure(self, tmp_path):
        wav = save_wav(tmp_path / "good.wav", F.demo_heart_signal(seconds=4.0, amplitude=0.3), 48000)
        assert cli.main(["analyze", str(wav), "--figures"]) == 0
        assert (tmp_path / "good.png").exists()


class TestDevices:
    def test_devices_lists_modules(self, fake_sd, capsys):
        assert cli.main(["devices"]) == 0
        out = capsys.readouterr().out
        assert "usb_mic" in out
        assert "USB PnP Sound Device" in out


class TestRecord:
    def test_record_single_position(self, fake_sd, tmp_path, capsys):
        out_root = tmp_path / "recs"
        # NOTE: the fake backend emits a steady 40 Hz tone, so the quality
        # gate will (correctly) NOT call it "good" -- exit code 0 or 1 both
        # mean the command itself worked. Verdict logic is covered in
        # test_quality.py.
        code = cli.main(
            [
                "record", "--module", "usb_mic", "--position", "mitral",
                "--seconds", "0.3", "--out", str(out_root),
            ]
        )
        assert code in (0, 1)
        wavs = list(out_root.rglob("*.wav"))
        assert len(wavs) == 1
        assert "mitral" in wavs[0].name
        out = capsys.readouterr().out
        assert "saved:" in out

    def test_export_rebuilds_packet(self, fake_sd, tmp_path, capsys):
        out_root = tmp_path / "recs"
        assert cli.main(
            ["record", "--module", "usb_mic", "--position", "mitral",
             "--seconds", "0.3", "--out", str(out_root)]
        ) in (0, 1)
        session_dir = next(out_root.iterdir())
        assert cli.main(["export", str(session_dir)]) == 0
        zips = list(out_root.glob("*.zip"))
        assert len(zips) == 1
        out = capsys.readouterr().out
        assert "physician packet:" in out


class TestParser:
    def test_unknown_command_exits(self, capsys):
        with pytest.raises(SystemExit):
            cli.main(["frobnicate"])

    def test_version_flag(self, capsys):
        with pytest.raises(SystemExit) as exc:
            cli.main(["--version"])
        assert exc.value.code == 0