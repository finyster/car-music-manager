from pathlib import Path

import pytest

from car_music_manager.errors import ValidationError
from car_music_manager.files import discover_audio, sanitize_filename, unique_output_path


def test_discover_audio_recurses_and_ignores_other_files(tmp_path: Path) -> None:
    (tmp_path / "song.MP3").touch()
    nested = tmp_path / "中文"
    nested.mkdir()
    (nested / "track.flac").touch()
    (nested / "notes.txt").touch()

    assert discover_audio(tmp_path) == [tmp_path / "song.MP3", nested / "track.flac"]


def test_discover_rejects_unsupported_file(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.touch()
    with pytest.raises(ValidationError, match="Unsupported"):
        discover_audio(source)


@pytest.mark.parametrize(
    ("raw", "expected"), [("bad:name. ", "bad_name"), ("CON", "_CON"), ("...", "untitled")]
)
def test_sanitize_filename(raw: str, expected: str) -> None:
    assert sanitize_filename(raw) == expected


def test_unique_output_path_suffixes_existing_file(tmp_path: Path) -> None:
    (tmp_path / "song.mp3").touch()
    (tmp_path / "song (2).mp3").touch()
    assert unique_output_path(tmp_path, "song") == tmp_path / "song (3).mp3"
