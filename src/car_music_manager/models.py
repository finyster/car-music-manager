"""Typed data structures used across the application."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AudioInfo:
    """Audio stream metadata returned by ffprobe."""

    path: Path
    format_name: str | None = None
    duration_seconds: float | None = None
    bitrate_bps: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    codec_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["path"] = str(self.path)
        return data


@dataclass(frozen=True)
class TagData:
    """Portable metadata mapped to ID3 tags when outputting MP3."""

    title: str | None = None
    artist: str | None = None
    album: str | None = None
    album_artist: str | None = None
    track_number: str | None = None
    disc_number: str | None = None
    date: str | None = None
    genre: str | None = None
    comment: str | None = None


@dataclass(frozen=True)
class ProcessingOptions:
    """User-configurable target audio settings."""

    lufs: float = -16.0
    true_peak_db: float = -1.5
    bitrate_kbps: int = 256
    sample_rate: int = 44100
    channels: int = 2


@dataclass
class ItemResult:
    """Outcome for a single requested item."""

    source: Path
    status: str
    output: Path | None = None
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source"] = str(self.source)
        data["output"] = str(self.output) if self.output else None
        return data
