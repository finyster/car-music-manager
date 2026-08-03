"""Authorized-source listing and download support via yt-dlp."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .errors import CarMusicError


@dataclass(frozen=True)
class SourceEntry:
    """A selectable remote source discovered without downloading media."""

    source: str
    title: str
    duration_seconds: int | None = None
    uploader: str | None = None
    selected: bool = False


def list_youtube(url: str) -> list[SourceEntry]:
    """List a video, playlist, or channel URL without downloading it.

    Users are responsible for having permission to download selected sources.
    """
    try:
        import yt_dlp
    except ImportError as error:  # pragma: no cover - packaging protects this
        raise CarMusicError("yt-dlp is not installed") from error
    options = {"quiet": True, "extract_flat": True, "skip_download": True, "noplaylist": False}
    with yt_dlp.YoutubeDL(options) as downloader:
        metadata = downloader.extract_info(url, download=False)
    entries = metadata.get("entries") or [metadata]
    return [
        SourceEntry(
            source=str(entry.get("webpage_url") or entry.get("url") or ""),
            title=str(entry.get("title") or "untitled"),
            duration_seconds=entry.get("duration"),
            uploader=entry.get("uploader") or entry.get("channel"),
        )
        for entry in entries
        if entry
    ]


def export_selection(entries: Iterable[SourceEntry], destination: Path) -> None:
    """Export a UTF-8 BOM CSV which a user can mark in the selected column."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=("selected", "source", "title", "duration_seconds", "uploader")
        )
        writer.writeheader()
        for item in entries:
            writer.writerow({"selected": "yes" if item.selected else "", **item.__dict__})


def download_authorized(url: str, destination: Path) -> Path:
    """Download one authorized source to a controlled temporary directory."""
    try:
        import yt_dlp
    except ImportError as error:  # pragma: no cover
        raise CarMusicError("yt-dlp is not installed") from error
    destination.mkdir(parents=True, exist_ok=True)
    options = {
        "format": "bestaudio/best",
        "outtmpl": str(destination / "%(title).180B-%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "restrictfilenames": False,
    }
    with yt_dlp.YoutubeDL(options) as downloader:
        metadata = downloader.extract_info(url, download=True)
        filename = Path(downloader.prepare_filename(metadata))
    if not filename.exists():
        candidates = list(destination.glob(f"*-{metadata['id']}.*"))
        if candidates:
            return candidates[0]
        raise CarMusicError("yt-dlp did not create the expected audio file")
    return filename
