"""Safe, verified flat-layout export of car-ready MP3 files to a USB drive."""

from __future__ import annotations

import csv
import ctypes
import hashlib
import os
import shutil
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import psutil

from .analyze import analyze_audio
from .errors import ValidationError
from .files import sanitize_filename
from .models import AudioInfo
from .verify import verify_decodable

MIN_FREE_BYTES = 500 * 1024 * 1024
_DRIVE_REMOVABLE = 2


@dataclass(frozen=True)
class UsbDrive:
    """A removable Windows volume eligible for the explicit USB export."""

    mountpoint: Path
    filesystem: str
    total_bytes: int
    free_bytes: int


@dataclass
class ExportEntry:
    source: Path
    destination: Path | None
    status: str
    size: int = 0
    sha256: str = ""
    codec: str = ""
    bitrate: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    message: str = ""


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of *path* without loading it all into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detect_removable_drives() -> list[UsbDrive]:
    """Return Windows volumes explicitly reported as removable by the OS."""
    if os.name != "nt":
        return []
    drives: list[UsbDrive] = []
    get_drive_type = ctypes.windll.kernel32.GetDriveTypeW
    for partition in psutil.disk_partitions(all=False):
        mountpoint = Path(partition.mountpoint)
        if get_drive_type(str(mountpoint)) != _DRIVE_REMOVABLE:
            continue
        try:
            usage = psutil.disk_usage(str(mountpoint))
        except OSError:
            continue
        drives.append(
            UsbDrive(
                mountpoint=mountpoint,
                filesystem=partition.fstype or "unknown",
                total_bytes=usage.total,
                free_bytes=usage.free,
            )
        )
    return sorted(drives, key=lambda drive: str(drive.mountpoint).casefold())


def select_auto_usb(drives: list[UsbDrive]) -> UsbDrive:
    """Require exactly one removable drive; never guess a target volume."""
    if len(drives) != 1:
        details = ", ".join(
            f"{drive.mountpoint} ({drive.filesystem}, {drive.free_bytes} free)" for drive in drives
        ) or "none"
        raise ValidationError(f"Expected exactly one removable USB drive, found {len(drives)}: {details}")
    return drives[0]


def discover_mp3(source: Path) -> list[Path]:
    """Find only MP3 files beneath the explicitly provided car-ready folder."""
    if not source.is_dir():
        raise ValidationError(f"Source folder does not exist or is not a folder: {source}")
    files = sorted(
        (path for path in source.rglob("*") if path.is_file() and path.suffix.casefold() == ".mp3"),
        key=lambda path: str(path).casefold(),
    )
    if not files:
        raise ValidationError(f"No MP3 files found under source folder: {source}")
    return files


def validate_mp3(path: Path) -> AudioInfo:
    """Require the car-ready profile and a full FFmpeg decode before export."""
    info = analyze_audio(path)
    verify_decodable(path)
    bitrate_ok = info.bitrate_bps is not None and 240_000 <= info.bitrate_bps <= 270_000
    if not (
        info.codec_name == "mp3"
        and info.sample_rate == 44_100
        and info.channels == 2
        and bitrate_ok
    ):
        raise ValidationError(
            "Unexpected car-ready profile "
            f"(codec={info.codec_name}, bitrate={info.bitrate_bps}, "
            f"sample_rate={info.sample_rate}, channels={info.channels})"
        )
    return info


def _flat_filename(source: Path) -> str:
    return f"{sanitize_filename(source.stem)}.mp3"


def _stable_destination(directory: Path, filename: str, source_hash: str) -> tuple[Path, bool]:
    """Choose a non-overwriting destination, returning whether it already matches."""
    stem = Path(filename).stem
    candidate = directory / filename
    index = 2
    while candidate.exists():
        if candidate.is_file() and sha256_file(candidate) == source_hash:
            return candidate, True
        candidate = directory / f"{stem} ({index}).mp3"
        index += 1
    return candidate, False


def _entry_from_info(source: Path, info: AudioInfo, digest: str) -> ExportEntry:
    return ExportEntry(
        source=source,
        destination=None,
        status="PLANNED",
        size=source.stat().st_size,
        sha256=digest,
        codec=info.codec_name or "",
        bitrate=info.bitrate_bps,
        sample_rate=info.sample_rate,
        channels=info.channels,
    )


def create_plan(source_files: list[Path], destination: Path) -> list[ExportEntry]:
    """Inspect sources and decide every destination without writing to the USB."""
    entries: list[ExportEntry] = []
    planned_hashes: set[str] = set()
    existing_hashes: dict[str, Path] = {}
    if destination.is_dir():
        for existing in destination.glob("*.mp3"):
            try:
                existing_hashes.setdefault(sha256_file(existing), existing)
            except OSError:
                continue
    for source in source_files:
        try:
            info = validate_mp3(source)
            digest = sha256_file(source)
            entry = _entry_from_info(source, info, digest)
            if digest in planned_hashes:
                entry.status = "DUPLICATE"
                entry.message = "Duplicate source SHA-256 in this export; skipped."
            elif digest in existing_hashes:
                entry.destination = existing_hashes[digest]
                entry.status = "DUPLICATE"
                entry.message = "Identical SHA-256 already exists on USB; skipped."
            else:
                target, identical = _stable_destination(destination, _flat_filename(source), digest)
                entry.destination = target
                if identical:
                    entry.status = "DUPLICATE"
                    entry.message = "Identical filename and SHA-256 already exists on USB; skipped."
                else:
                    planned_hashes.add(digest)
            entries.append(entry)
        except Exception as error:
            entries.append(ExportEntry(source=source, destination=None, status="WARNING", message=str(error)))
    return entries


def _copy_and_verify(entry: ExportEntry, temp_paths: set[Path]) -> None:
    assert entry.destination is not None
    temporary = entry.destination.with_suffix(".mp3.copying")
    if temporary.exists():
        raise ValidationError(f"Temporary export file already exists; left untouched: {temporary}")
    temp_paths.add(temporary)
    shutil.copyfile(entry.source, temporary)
    if temporary.stat().st_size != entry.size:
        raise ValidationError("Copied file size does not match source.")
    if sha256_file(temporary) != entry.sha256:
        raise ValidationError("Copied file SHA-256 does not match source.")
    validate_mp3(temporary)
    temporary.rename(entry.destination)
    temp_paths.discard(temporary)
    entry.status = "COPIED"
    entry.message = "Copied and verified."


def cleanup_temporary_files(temp_paths: set[Path]) -> None:
    """Remove only .copying files created by this process after interruption/failure."""
    for path in tuple(temp_paths):
        try:
            if path.exists() and path.suffix == ".copying":
                path.unlink()
        except OSError:
            pass
        finally:
            temp_paths.discard(path)


def _write_reports(entries: list[ExportEntry], drive: UsbDrive, report_root: Path) -> None:
    report_root.mkdir(parents=True, exist_ok=True)
    fields = [
        "source",
        "destination",
        "status",
        "size",
        "sha256",
        "codec",
        "bitrate",
        "sample_rate",
        "channels",
        "message",
    ]
    with (report_root / "usb-export.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for entry in entries:
            writer.writerow(
                {
                    "source": entry.source,
                    "destination": entry.destination or "",
                    "status": entry.status,
                    "size": entry.size,
                    "sha256": entry.sha256,
                    "codec": entry.codec,
                    "bitrate": entry.bitrate or "",
                    "sample_rate": entry.sample_rate or "",
                    "channels": entry.channels or "",
                    "message": entry.message,
                }
            )
    counts = Counter(entry.status for entry in entries)
    copied_bytes = sum(entry.size for entry in entries if entry.status == "COPIED")
    lines = [
        "# USB export summary",
        "",
        f"- USB: {drive.mountpoint}",
        f"- File system: {drive.filesystem}",
        f"- Source total: {len(entries)}",
        f"- Copied: {counts['COPIED']}",
        f"- Duplicate/skipped: {counts['DUPLICATE']}",
        f"- Warning: {counts['WARNING']}",
        f"- Failed: {counts['FAILED']}",
        f"- Copied bytes: {copied_bytes}",
        f"- USB free bytes before export: {drive.free_bytes}",
    ]
    (report_root / "usb-export-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_flat(
    source: Path,
    drive: UsbDrive,
    folder: str,
    report_root: Path,
    *,
    dry_run: bool = False,
) -> list[ExportEntry]:
    """Preflight then safely copy verified files to one folder on *drive*."""
    if Path(folder).name != folder or folder in {"", ".", ".."}:
        raise ValidationError("--folder must be a single folder name.")
    source_files = discover_mp3(source)
    destination = drive.mountpoint / sanitize_filename(folder)
    entries = create_plan(source_files, destination)
    required = sum(entry.size for entry in entries if entry.status == "PLANNED")
    if drive.free_bytes - required < MIN_FREE_BYTES:
        for entry in entries:
            if entry.status == "PLANNED":
                entry.status = "FAILED"
                entry.message = "USB capacity preflight failed; 500 MB free space must remain."
        _write_reports(entries, drive, report_root)
        return entries
    if dry_run:
        for entry in entries:
            if entry.status == "PLANNED":
                entry.status = "DRY_RUN"
                entry.message = "Preflight passed; no file copied."
        _write_reports(entries, drive, report_root)
        return entries

    destination.mkdir(parents=True, exist_ok=True)
    temporary_paths: set[Path] = set()
    try:
        for entry in entries:
            if entry.status != "PLANNED":
                continue
            try:
                _copy_and_verify(entry, temporary_paths)
            except Exception as error:
                cleanup_temporary_files(temporary_paths)
                entry.status = "FAILED"
                entry.message = str(error)
    except KeyboardInterrupt:
        cleanup_temporary_files(temporary_paths)
        raise
    finally:
        cleanup_temporary_files(temporary_paths)
        _write_reports(entries, drive, report_root)
    return entries


def format_summary(entries: list[ExportEntry], drive: UsbDrive) -> str:
    """Build the concise terminal result without exposing any control operations."""
    counts = Counter(entry.status for entry in entries)
    copied_bytes = sum(entry.size for entry in entries if entry.status == "COPIED")
    return "\n".join(
        [
            f"USB: {drive.mountpoint}",
            f"File system: {drive.filesystem}",
            f"Source total: {len(entries)}",
            f"Copied: {counts['COPIED']}",
            f"Already present / duplicate: {counts['DUPLICATE']}",
            f"Warning: {counts['WARNING']}",
            f"Failed: {counts['FAILED']}",
            f"Copied bytes: {copied_bytes}",
            f"USB free bytes before export: {drive.free_bytes}",
        ]
    )


def run_auto_export(
    source: Path,
    folder: str,
    report_root: Path,
    *,
    dry_run: bool = False,
    drive_detector: Callable[[], list[UsbDrive]] = detect_removable_drives,
) -> tuple[UsbDrive, list[ExportEntry]]:
    """Detect exactly one removable drive and export only after safe preflight."""
    detected = drive_detector()
    source_volume = Path(source).resolve().drive.casefold()
    eligible = [
        drive
        for drive in detected
        if drive.mountpoint.resolve().drive.casefold() != source_volume
    ]
    if len(eligible) != 1:
        details = ", ".join(
            f"{drive.mountpoint} ({drive.filesystem}, {drive.free_bytes} free)" for drive in detected
        ) or "none"
        raise ValidationError(
            "Expected exactly one removable USB drive distinct from the source volume "
            f"{source_volume or source}; found {len(eligible)} eligible drives. Detected: {details}"
        )
    drive = select_auto_usb(eligible)
    return drive, export_flat(source, drive, folder, report_root, dry_run=dry_run)
