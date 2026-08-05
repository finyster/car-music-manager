"""Conservative duplicate detection for GUI imports and processed music."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from mutagen import File

_INDEX_FILENAME = ".car-music-dedupe.json"
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
_YOUTUBE_HOSTS = {
    "m.youtube.com",
    "music.youtube.com",
    "www.youtube.com",
    "youtu.be",
    "youtube.com",
}
_VIDEO_PATH_PREFIXES = ("/embed/", "/live/", "/shorts/")


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"[^\w]+", "", normalized, flags=re.UNICODE)


def track_key(artist: str, title: str) -> str:
    """Return a strict normalized artist/title key suitable for duplicate checks."""
    normalized_title = _normalize_text(title)
    if not normalized_title:
        return ""
    return f"{_normalize_text(artist)}\0{normalized_title}"


def durations_match(
    first: int | None,
    second: int | None,
    *,
    tolerance_seconds: int = 3,
) -> bool:
    """Return whether two known durations are close enough to be the same version."""
    if first is None or second is None:
        return False
    return abs(int(first) - int(second)) <= tolerance_seconds


def canonical_source_key(value: str) -> str:
    """Return a stable identity for local paths and common YouTube URL variants."""
    candidate = value.strip()
    if not candidate:
        return ""

    lowered = candidate.casefold()
    if "://" not in candidate and lowered.startswith(
        ("youtube.com/", "www.youtube.com/", "music.youtube.com/", "youtu.be/")
    ):
        candidate = f"https://{candidate}"

    parsed = urlsplit(candidate)
    if not parsed.scheme or not parsed.hostname:
        resolved = Path(candidate).expanduser().resolve(strict=False)
        return f"file:{str(resolved).casefold()}"

    host = (parsed.hostname or "").casefold()
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    query = dict(query_items)
    path = parsed.path.rstrip("/") or "/"

    if host in _YOUTUBE_HOSTS:
        video_id = ""
        if host == "youtu.be":
            video_id = path.strip("/").split("/", 1)[0]
        elif path == "/watch":
            video_id = query.get("v", "")
        else:
            for prefix in _VIDEO_PATH_PREFIXES:
                if path.startswith(prefix):
                    video_id = path[len(prefix) :].split("/", 1)[0]
                    break
        if video_id:
            return f"youtube:video:{video_id}"
        playlist_id = query.get("list", "")
        if path == "/playlist" and playlist_id:
            return f"youtube:playlist:{playlist_id}"
        return f"youtube:page:{path.casefold()}"

    filtered_query = sorted(
        (key, item)
        for key, item in query_items
        if key.casefold() not in _TRACKING_QUERY_KEYS
    )
    normalized_url = urlunsplit(
        (
            parsed.scheme.casefold(),
            host,
            path,
            urlencode(filtered_query, doseq=True),
            "",
        )
    )
    return f"url:{normalized_url}"


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Hash a source file without loading it all into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def scan_existing_track_keys(destination: Path) -> set[str]:
    """Read strict artist/title keys from existing MP3 outputs."""
    keys: set[str] = set()
    if not destination.exists():
        return keys
    for path in destination.rglob("*.mp3"):
        try:
            media = File(path, easy=True)
            tags = media.tags if media else None
            artist_values = tags.get("artist", []) if tags else []
            title_values = tags.get("title", []) if tags else []
            artist = str(artist_values[0]) if artist_values else ""
            title = str(title_values[0]) if title_values else ""
            key = track_key(artist, title)
            if key:
                keys.add(key)
        except Exception:
            continue
    return keys


@dataclass
class DedupeIndex:
    """Persistent identities for outputs successfully produced in a destination."""

    source_keys: set[str] = field(default_factory=set)
    content_sha256: set[str] = field(default_factory=set)
    track_keys: set[str] = field(default_factory=set)

    @classmethod
    def load(cls, destination: Path) -> DedupeIndex:
        """Load the destination index; malformed or absent indexes start empty."""
        path = destination / _INDEX_FILENAME
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return cls()
        if not isinstance(payload, dict):
            return cls()

        def values(name: str) -> set[str]:
            raw = payload.get(name, [])
            if not isinstance(raw, list):
                return set()
            return {str(item) for item in raw if item}

        return cls(
            source_keys=values("source_keys"),
            content_sha256=values("content_sha256"),
            track_keys=values("track_keys"),
        )

    def add(self, *, source_key: str = "", content_hash: str = "", track: str = "") -> None:
        """Record one successfully processed track identity."""
        if source_key:
            self.source_keys.add(source_key)
        if content_hash:
            self.content_sha256.add(content_hash)
        if track:
            self.track_keys.add(track)

    def save(self, destination: Path) -> Path:
        """Atomically save the duplicate index in the output destination."""
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / _INDEX_FILENAME
        temporary = path.with_suffix(path.suffix + ".tmp")
        payload = {
            "version": 1,
            "source_keys": sorted(self.source_keys),
            "content_sha256": sorted(self.content_sha256),
            "track_keys": sorted(self.track_keys),
        }
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return path
