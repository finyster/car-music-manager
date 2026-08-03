from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from car_music_manager.errors import ValidationError
from car_music_manager.models import AudioInfo
from car_music_manager.usb_export import (
    MIN_FREE_BYTES,
    UsbDrive,
    discover_mp3,
    export_flat,
    run_auto_export,
    select_auto_usb,
)


def _drive(root: Path, *, free_bytes: int = 2 * 1024 * 1024 * 1024) -> UsbDrive:
    return UsbDrive(root, "exFAT", free_bytes * 2, free_bytes)


def _valid_info(path: Path) -> AudioInfo:
    return AudioInfo(path, "mp3", 1.0, 256000, 44100, 2, "mp3")


def _source(tmp_path: Path, relative: str = "genre/01 - 歌手 - 歌名.mp3") -> Path:
    path = tmp_path / "source" / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(b"verified car music")
    return path


def test_auto_usb_refuses_zero_or_multiple_drives(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        select_auto_usb([])
    with pytest.raises(ValidationError, match="found 2"):
        select_auto_usb([_drive(tmp_path / "E"), _drive(tmp_path / "F")])


def test_auto_usb_refuses_the_source_volume_even_if_windows_calls_it_removable(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source_drive = Path(source.resolve().drive + "\\")

    with pytest.raises(ValidationError, match="distinct from the source volume"):
        run_auto_export(source, "Music", tmp_path / "reports", drive_detector=lambda: [_drive(source_drive)])


def test_empty_source_folder_stops_safely(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    with pytest.raises(ValidationError, match="No MP3"):
        discover_mp3(empty)


def test_export_uses_flat_layout_and_does_not_modify_source(tmp_path: Path, monkeypatch) -> None:
    source = _source(tmp_path, "nested/folder/01 - 歌手 - 歌名.mp3")
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    usb = tmp_path / "usb"
    usb.mkdir()
    monkeypatch.setattr("car_music_manager.usb_export.validate_mp3", _valid_info)

    entries = export_flat(tmp_path / "source", _drive(usb), "Music", tmp_path / "reports")

    assert entries[0].status == "COPIED"
    assert entries[0].destination == usb / "Music" / "01 - 歌手 - 歌名.mp3"
    assert entries[0].destination.is_file()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
    assert not (usb / "Music" / "nested").exists()


def test_same_sha_is_skipped_as_duplicate(tmp_path: Path, monkeypatch) -> None:
    source = _source(tmp_path)
    usb = tmp_path / "usb"
    destination = usb / "Music"
    destination.mkdir(parents=True)
    existing = destination / source.name
    existing.write_bytes(source.read_bytes())
    monkeypatch.setattr("car_music_manager.usb_export.validate_mp3", _valid_info)

    entries = export_flat(tmp_path / "source", _drive(usb), "Music", tmp_path / "reports")

    assert entries[0].status == "DUPLICATE"
    assert existing.read_bytes() == source.read_bytes()


def test_same_name_with_different_content_gets_stable_suffix(tmp_path: Path, monkeypatch) -> None:
    source = _source(tmp_path)
    usb = tmp_path / "usb"
    destination = usb / "Music"
    destination.mkdir(parents=True)
    (destination / source.name).write_bytes(b"different existing audio")
    monkeypatch.setattr("car_music_manager.usb_export.validate_mp3", _valid_info)

    entries = export_flat(tmp_path / "source", _drive(usb), "Music", tmp_path / "reports")

    assert entries[0].status == "COPIED"
    assert entries[0].destination == destination / "01 - 歌手 - 歌名 (2).mp3"


def test_capacity_preflight_does_not_create_usb_folder(tmp_path: Path, monkeypatch) -> None:
    source = _source(tmp_path)
    usb = tmp_path / "usb"
    usb.mkdir()
    monkeypatch.setattr("car_music_manager.usb_export.validate_mp3", _valid_info)
    free_bytes = MIN_FREE_BYTES + source.stat().st_size - 1

    entries = export_flat(tmp_path / "source", _drive(usb, free_bytes=free_bytes), "Music", tmp_path / "reports")

    assert entries[0].status == "FAILED"
    assert not (usb / "Music").exists()


def test_failed_copy_verification_never_publishes_final_file(tmp_path: Path, monkeypatch) -> None:
    _source(tmp_path)
    usb = tmp_path / "usb"
    usb.mkdir()

    def fail_copying_validation(path: Path) -> AudioInfo:
        if path.suffix == ".copying":
            raise ValidationError("simulated target verification failure")
        return _valid_info(path)

    monkeypatch.setattr("car_music_manager.usb_export.validate_mp3", fail_copying_validation)
    entries = export_flat(tmp_path / "source", _drive(usb), "Music", tmp_path / "reports")

    assert entries[0].status == "FAILED"
    assert not list((usb / "Music").glob("*.mp3"))
    assert not list((usb / "Music").glob("*.copying"))
