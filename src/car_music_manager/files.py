"""Safe file discovery and output naming."""

from __future__ import annotations

import re
from pathlib import Path

from .constants import SUPPORTED_EXTENSIONS, WINDOWS_RESERVED_NAMES
from .errors import ValidationError

_ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def is_supported_audio(path: Path) -> bool:
    """Return whether *path* is one of the accepted audio file types."""
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS


def discover_audio(source: Path) -> list[Path]:
    """Collect supported audio from one file or recursively from a directory."""
    source = source.expanduser()
    if not source.exists():
        raise ValidationError(f"Input does not exist: {source}")
    if source.is_file():
        if not is_supported_audio(source):
            raise ValidationError(f"Unsupported audio type: {source.suffix or source.name}")
        return [source]
    return sorted(
        (item for item in source.rglob("*") if is_supported_audio(item)),
        key=lambda item: str(item).casefold(),
    )


def sanitize_filename(name: str, replacement: str = "_") -> str:
    """Produce a Windows-safe filename stem without an extension."""
    cleaned = _ILLEGAL_FILENAME_CHARS.sub(replacement, name).rstrip(". ").strip()
    cleaned = re.sub(rf"{re.escape(replacement)}+", replacement, cleaned)
    if not cleaned:
        cleaned = "untitled"
    if cleaned.upper() in WINDOWS_RESERVED_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned[:180]


def unique_output_path(directory: Path, preferred_stem: str, extension: str = ".mp3") -> Path:
    """Choose a non-existing, safe output path without modifying the filesystem."""
    stem = sanitize_filename(preferred_stem)
    candidate = directory / f"{stem}{extension}"
    index = 2
    while candidate.exists():
        candidate = directory / f"{stem} ({index}){extension}"
        index += 1
    return candidate


def ensure_writable_directory(path: Path) -> Path:
    """Create and return the requested output directory."""
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise ValidationError(f"Output is not a directory: {path}")
    return path
