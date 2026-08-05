"""Metadata extraction, ID3v2.3 writing, and compatible artwork embedding."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from mutagen import File
from mutagen.id3 import (
    APIC,
    COMM,
    ID3,
    ID3NoHeaderError,
    TALB,
    TCON,
    TDRC,
    TIT2,
    TPE1,
    TPE2,
    TPOS,
    TRCK,
)
from PIL import Image

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


def _open_id3(path: Path) -> ID3:
    try:
        return ID3(path)
    except ID3NoHeaderError:
        return ID3()


def embed_artwork_jpeg(mp3_path: Path, jpeg_data: bytes) -> None:
    """Embed already-normalized JPEG bytes as the front cover in ID3v2.3."""
    if not jpeg_data.startswith(b"\xff\xd8"):
        raise ValueError("artwork data is not JPEG")
    id3 = _open_id3(mp3_path)
    id3.delall("APIC")
    id3.add(
        APIC(
            encoding=3,
            mime="image/jpeg",
            type=3,
            desc="Cover",
            data=jpeg_data,
        )
    )
    id3.save(mp3_path, v2_version=3)


def embed_artwork(mp3_path: Path, artwork_path: Path, *, max_size: int = 500) -> None:
    """Convert an image to a compact JPEG and embed it as ID3v2.3 cover art."""
    if max_size < 1:
        raise ValueError("max_size must be positive")
    with Image.open(artwork_path) as source:
        image = source.convert("RGB")
        image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=88, optimize=True)
    embed_artwork_jpeg(mp3_path, buffer.getvalue())
