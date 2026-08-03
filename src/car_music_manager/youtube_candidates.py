"""Metadata-only YouTube candidate discovery for human source review."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .inbox import normalize_text

_EXCLUDED = re.compile(
    r"\b(cover|karaoke|ktv|live|concert|remix|sped\s*up|slowed|loop|instrumental)\b|"
    r"翻唱|伴奏|演唱會|現場|加速|降調|循環",
    re.IGNORECASE,
)
_OFFICIAL_AUDIO = re.compile(r"official\s*audio|官方\s*(音源|音樂)", re.IGNORECASE)
_OFFICIAL_MV = re.compile(r"official\s*(mv|music\s*video)|官方\s*mv", re.IGNORECASE)
_TOPIC = re.compile(r"\btopic\b", re.IGNORECASE)
_LABEL_CHANNEL = re.compile(r"\b(official|records?|music|vevo)\b|唱片|娛樂", re.IGNORECASE)


@dataclass(frozen=True)
class YoutubeCandidate:
    """One searchable candidate; this metadata never authorizes downloading."""

    artist: str
    title: str
    video_title: str
    channel: str
    url: str
    duration: int | None
    upload_date: str | None
    official_signal: str
    title_match: str
    priority: int


def is_excluded(video_title: str) -> bool:
    """Reject alternate/derived performances that are not the requested studio release."""
    return bool(_EXCLUDED.search(video_title))


def official_signal(video_title: str, channel: str, artist: str) -> tuple[str, int]:
    """Rank visible official indicators without claiming they grant download rights."""
    channel_folded = channel.casefold()
    artist_folded = artist.casefold()
    if _TOPIC.search(channel):
        return "ARTIST_TOPIC", 40
    if artist_folded and artist_folded in channel_folded:
        return "ARTIST_NAMED_CHANNEL", 50
    if _LABEL_CHANNEL.search(channel):
        return "LABEL_OR_OFFICIAL_CHANNEL", 45
    if _OFFICIAL_AUDIO.search(video_title):
        return "OFFICIAL_AUDIO", 30
    if _OFFICIAL_MV.search(video_title):
        return "OFFICIAL_MV", 20
    return "UNVERIFIED", 0


def candidate_from_entry(artist: str, title: str, entry: dict[str, Any]) -> YoutubeCandidate | None:
    """Normalize one yt-dlp flat-search result into a reviewable candidate."""
    video_title = str(entry.get("title") or "").strip()
    if not video_title or is_excluded(video_title):
        return None
    channel = str(entry.get("channel") or entry.get("uploader") or "").strip()
    normalized_title = normalize_text(title)
    normalized_video = normalize_text(video_title)
    normalized_artist = normalize_text(artist)
    normalized_context = normalize_text(f"{video_title} {channel}")
    if len(normalized_title) >= 2 and normalized_title not in normalized_video:
        return None
    if len(normalized_title) < 2 and normalized_artist not in normalized_context:
        return None
    signal, priority = official_signal(video_title, channel, artist)
    artist_removed = normalized_video.replace(normalized_artist, "") if normalized_artist else normalized_video
    title_match = "EXACT_TITLE" if artist_removed == normalized_title else "NAME_REVIEW"
    video_id = entry.get("id")
    url = str(entry.get("webpage_url") or entry.get("url") or "").strip()
    if not url and video_id:
        url = f"https://www.youtube.com/watch?v={video_id}"
    if not url:
        return None
    duration = entry.get("duration")
    return YoutubeCandidate(
        artist=artist,
        title=title,
        video_title=video_title,
        channel=channel,
        url=url,
        duration=int(duration) if isinstance(duration, (int, float)) else None,
        upload_date=str(entry["upload_date"]) if entry.get("upload_date") else None,
        official_signal=signal,
        title_match=title_match,
        priority=priority,
    )


def search_youtube(artist: str, title: str, max_candidates: int = 5) -> list[YoutubeCandidate]:
    """Search YouTube metadata only; never download or request media streams."""
    try:
        import yt_dlp
    except ImportError as error:  # pragma: no cover - dependency is declared
        raise RuntimeError("yt-dlp is not installed") from error
    options = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "noplaylist": True,
        "socket_timeout": 15,
    }
    query = f"ytsearch10:{artist} {title} official audio"
    with yt_dlp.YoutubeDL(options) as downloader:
        metadata = downloader.extract_info(query, download=False)
    candidates = [
        candidate
        for entry in (metadata.get("entries") or [])
        if entry and (candidate := candidate_from_entry(artist, title, entry))
    ]
    candidates.sort(key=lambda candidate: (-candidate.priority, candidate.video_title.casefold()))
    return candidates[:max_candidates]
