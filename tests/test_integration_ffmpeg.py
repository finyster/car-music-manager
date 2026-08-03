"""Opt-in integration coverage requiring FFmpeg and ffprobe on PATH."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from car_music_manager.analyze import analyze_audio
from car_music_manager.process import process_one

pytestmark = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="FFmpeg and ffprobe are required",
)


def test_full_encode_normalize_and_decode(tmp_path: Path) -> None:
    source = tmp_path / "測試音樂.wav"
    generated = subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(source)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    assert generated.returncode == 0, generated.stderr

    result = process_one(source, tmp_path / "USB")
    info = analyze_audio(result)

    assert result.suffix == ".mp3"
    assert info.sample_rate == 44100
    assert info.channels == 2
