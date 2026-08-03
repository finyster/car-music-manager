"""Metadata extraction and ID3v2.3 writing."""

from __future__ import annotations

from pathlib import Path

from mutagen import File
from mutagen.id3 import COMM, ID3, TALB, TCON, TDRC, TIT2, TPE1, TPE2, TPOS, TRCK

from .models import TagData


def _first(tags: object, *keys: str) -> str | None:
    if not tags:
        return None
    for key in keys:
        value = tags.get(key)  # type: ignore[union-attr]
        if value:
            if isinstance(value, (list, tuple)):
                return str(value[0])
            return str(value)
    return None


def read_tags(path: Path) -> TagData:
    """Best-effort read tags from any Mutagen-supported input file."""
    media = File(path, easy=True)
    tags = media.tags if media else None
    return TagData(
        title=_first(tags, "title"),
        artist=_first(tags, "artist"),
        album=_first(tags, "album"),
        album_artist=_first(tags, "albumartist"),
        track_number=_first(tags, "tracknumber"),
        disc_number=_first(tags, "discnumber"),
        date=_first(tags, "date", "year"),
        genre=_first(tags, "genre"),
        comment=_first(tags, "comment", "description"),
    )


def write_id3v23(path: Path, tags: TagData) -> None:
    """Write Unicode-compatible ID3v2.3 text frames to an MP3 output."""
    id3 = ID3()
    frame_map = (
        (TIT2, tags.title),
        (TPE1, tags.artist),
        (TALB, tags.album),
        (TPE2, tags.album_artist),
        (TRCK, tags.track_number),
        (TPOS, tags.disc_number),
        (TDRC, tags.date),
        (TCON, tags.genre),
    )
    for frame_class, value in frame_map:
        if value:
            id3.add(frame_class(encoding=1, text=value))
    if tags.comment:
        id3.add(COMM(encoding=1, lang="eng", desc="", text=tags.comment))
    id3.save(path, v2_version=3)
