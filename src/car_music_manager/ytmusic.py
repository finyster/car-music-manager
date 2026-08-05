"""Metadata-only YouTube Music URL support.

This module is intentionally read-only. It normalizes YouTube Music links and
uses yt-dlp only to inspect track, playlist, album, and artist metadata. Media
is never downloaded here.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .errors import CarMusicError, ValidationError

_TRACKING_QUERY_KEYS = {
    "app",
    "feature",
    "si",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}
_YTMUSIC_HOSTS = {"music.youtube.com", "m.music.youtube.com"}
_CHANNEL_PREFIXES = ("/@", "/channel/", "/c/", "/user/")


@dataclass(frozen=True)
class YTMusicEntry:
    """One metadata-only result returned from YouTube Music."""

    source: str
    title: str
    artist: str = ""
    album: str = ""
    duration_seconds: int | None = None
    uploader: str = ""
    thumbnail_url: str = ""


def is_ytmusic_url(value: str) -> bool:
    """Return whether *value* points at the YouTube Music web host."""
    candidate = value.strip()
    if not candidate:
        return False
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    return (urlsplit(candidate).hostname or "").casefold() in _YTMUSIC_HOSTS


def normalize_ytmusic_url(value: str) -> str:
    """Normalize a YouTube Music URL and remove common tracking parameters."""
    candidate = value.strip()
    if not candidate:
        raise ValidationError("YouTube Music URL is empty")
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlsplit(candidate)
    host = (parsed.hostname or "").casefold()
    if host not in _YTMUSIC_HOSTS:
        raise ValidationError(f"Not a YouTube Music URL: {value}")
    filtered_query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if key.casefold() not in _TRACKING_QUERY_KEYS
    ]
    return urlunsplit(
        (
            "https",
            "music.youtube.com",
            parsed.path or "/",
            urlencode(filtered_query, doseq=True),
            "",
        )
    )


def classify_ytmusic_url(value: str) -> str:
    """Classify a normalized link as track, playlist, album, artist, or unknown."""
    normalized = normalize_ytmusic_url(value)
    parsed = urlsplit(normalized)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    path = parsed.path.rstrip("/") or "/"
    if path == "/watch" and query.get("v"):
        return "track"
    if path == "/playlist" and query.get("list"):
        return "album" if query["list"].startswith("OLAK5uy_") else "playlist"
    if path.startswith("/browse/MPRE"):
        return "album"
    if path.startswith(_CHANNEL_PREFIXES):
        return "artist"
    return "unknown"


def ytmusic_candidate_urls(value: str) -> list[str]:
    """Return ordered metadata fallbacks for a YouTube Music link."""
    normalized = normalize_ytmusic_url(value)
    parsed = urlsplit(normalized)
    kind = classify_ytmusic_url(normalized)
    regular = urlunsplit(("https", "www.youtube.com", parsed.path, parsed.query, ""))
    candidates: list[str] = []
    if kind == "artist":
        artist_path = parsed.path.rstrip("/")
        videos_path = artist_path if artist_path.endswith("/videos") else f"{artist_path}/videos"
        candidates.append(urlunsplit(("https", "www.youtube.com", videos_path, parsed.query, "")))
        candidates.append(regular)
        candidates.append(normalized)
    else:
        candidates.extend((normalized, regular))
    return list(dict.fromkeys(candidates))


def _thumbnail_url(info: dict[str, object]) -> str:
    direct = info.get("thumbnail")
    if direct:
        return str(direct)
    thumbnails = info.get("thumbnails")
    if isinstance(thumbnails, list):
        for item in reversed(thumbnails):
            if isinstance(item, dict) and item.get("url"):
                return str(item["url"])
    return ""


def _entry_source(info: dict[str, object]) -> str:
    source = info.get("webpage_url") or info.get("original_url")
    if source:
        return str(source)
    video_id = info.get("id")
    if video_id:
        return f"https://music.youtube.com/watch?v={video_id}"
    raw_url = info.get("url")
    return str(raw_url or "")


def ytmusic_entry_from_info(info: dict[str, object], *, fallback_album: str = "") -> YTMusicEntry:
    """Convert one yt-dlp metadata dictionary into a stable GUI model."""
    title = str(info.get("track") or info.get("title") or "未命名曲目")
    artist = str(
        info.get("artist")
        or info.get("creator")
        or info.get("uploader")
        or info.get("channel")
        or ""
    )
    album = str(info.get("album") or fallback_album or "")
    duration = info.get("duration")
    duration_seconds = int(duration) if isinstance(duration, (int, float)) else None
    uploader = str(info.get("uploader") or info.get("channel") or artist)
    return YTMusicEntry(
        source=_entry_source(info),
        title=title,
        artist=artist,
        album=album,
        duration_seconds=duration_seconds,
        uploader=uploader,
        thumbnail_url=_thumbnail_url(info),
    )


def _flatten_entries(
    metadata: dict[str, object],
    *,
    fallback_album: str = "",
) -> list[YTMusicEntry]:
    entries = metadata.get("entries")
    if not isinstance(entries, list):
        return [ytmusic_entry_from_info(metadata, fallback_album=fallback_album)]
    results: list[YTMusicEntry] = []
    parent_title = str(metadata.get("title") or fallback_album)
    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            continue
        nested = raw_entry.get("entries")
        if isinstance(nested, list):
            results.extend(_flatten_entries(raw_entry, fallback_album=parent_title))
            continue
        if raw_entry.get("_type") == "playlist" and not _entry_source(raw_entry):
            continue
        results.append(ytmusic_entry_from_info(raw_entry, fallback_album=fallback_album))
    return results


def list_ytmusic(value: str, *, max_entries: int = 500) -> list[YTMusicEntry]:
    """Read YouTube Music metadata without downloading audio or video."""
    try:
        import yt_dlp
    except ImportError as error:  # pragma: no cover - package dependency protects this
        raise CarMusicError("yt-dlp is not installed") from error

    kind = classify_ytmusic_url(value)
    failures: list[str] = []
    for candidate in ytmusic_candidate_urls(value):
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": "in_playlist",
            "ignoreerrors": True,
            "noplaylist": False,
            "playlistend": max_entries,
        }
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                metadata = downloader.extract_info(candidate, download=False)
        except Exception as error:  # yt-dlp boundary; preserve concise fallback diagnostics
            failures.append(f"{candidate}: {error}")
            continue
        if not isinstance(metadata, dict):
            failures.append(f"{candidate}: no metadata returned")
            continue
        fallback_album = str(metadata.get("title") or "") if kind == "album" else ""
        entries = _flatten_entries(metadata, fallback_album=fallback_album)
        deduplicated: list[YTMusicEntry] = []
        seen: set[str] = set()
        for entry in entries:
            identity = entry.source or f"{entry.artist}\0{entry.title}\0{entry.duration_seconds}"
            if not entry.source or identity in seen:
                continue
            seen.add(identity)
            deduplicated.append(entry)
        if deduplicated:
            return deduplicated[:max_entries]
        failures.append(f"{candidate}: no playable track entries")

    details = "\n".join(failures[-3:])
    raise CarMusicError(
        "Unable to read this YouTube Music link. Try a track, playlist, album playlist, "
        f"or artist URL.\n{details}"
    )
