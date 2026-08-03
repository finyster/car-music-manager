"""Conservative matching of authorized inbox audio to a catalog selection."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .analyze import analyze_audio
from .files import discover_audio
from .tags import read_tags

_SIMPLIFIED_TO_TRADITIONAL = str.maketrans(
    "邓丽杰苏叶齐费刘张孙陈杨荣杰佰忆莺萧范伦",
    "鄧麗傑蘇葉齊費劉張孫陳楊榮傑佰憶鶯蕭范倫",
)
_NOISE = re.compile(
    r"\b(official\s*(audio|mv|video)?|audio|music\s*video|lyrics?|hd|hq|mv|karaoke|ktv|"
    r"live|concert|cover|remix|instrumental|伴奏|翻唱|演唱會|現場|官方|原版|歌詞)\b",
    re.IGNORECASE,
)
_TRACK_PREFIX = re.compile(r"^\s*\d{1,3}\s*[._\-、]+\s*")
_SPLIT = re.compile(r"\s*(?:-|–|—|_|／|/)\s*")


@dataclass(frozen=True)
class InboxMetadata:
    """Best-effort source metadata from embedded tags plus a filename fallback."""

    path: Path
    artist: str
    title: str
    album: str
    bitrate_bps: int | None


@dataclass(frozen=True)
class MatchDecision:
    """A catalog candidate and its conservative matching confidence."""

    source: InboxMetadata
    catalog_id: str | None
    confidence: float
    status: str
    reason: str


def normalize_text(value: str) -> str:
    """Normalize predictable CJK/Latin spelling differences for comparison only."""
    value = unicodedata.normalize("NFKC", value).translate(_SIMPLIFIED_TO_TRADITIONAL)
    value = _TRACK_PREFIX.sub("", value)
    value = _NOISE.sub("", value)
    return "".join(character for character in value.casefold() if character.isalnum())


def metadata_from_path(path: Path) -> InboxMetadata:
    """Read media tags, falling back to common ``artist - title`` file names."""
    try:
        tags = read_tags(path)
        artist, title, album = tags.artist or "", tags.title or "", tags.album or ""
    except Exception:
        artist = title = album = ""
    stem = _NOISE.sub("", _TRACK_PREFIX.sub("", unicodedata.normalize("NFKC", path.stem))).strip()
    parts = [part.strip() for part in _SPLIT.split(stem) if part.strip()]
    if not artist and len(parts) >= 2:
        artist = parts[0]
    if not title and len(parts) >= 2:
        title = parts[-1]
    if not title:
        title = stem
    try:
        bitrate = analyze_audio(path).bitrate_bps
    except Exception:
        bitrate = None
    return InboxMetadata(path, artist, title, album, bitrate)


def match_metadata(metadata: InboxMetadata, selection: list[dict[str, str]]) -> MatchDecision:
    """Return only exact/high-confidence matches; preserve ambiguity for review."""
    artist = normalize_text(metadata.artist)
    title = normalize_text(metadata.title)
    scored: list[tuple[float, dict[str, str], str]] = []
    for row in selection:
        target_artist, target_title = normalize_text(row["artist"]), normalize_text(row["title"])
        artist_score = 0.35 if artist and artist == target_artist else 0.0
        title_score = 0.65 if title and title == target_title else 0.0
        if title and target_title and (title in target_title or target_title in title):
            title_score = max(title_score, 0.4)
        scored.append((artist_score + title_score, row, "tag/filename metadata"))
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored or scored[0][0] < 0.4:
        return MatchDecision(metadata, None, scored[0][0] if scored else 0.0, "UNMATCHED", "No close title match")
    score, row, reason = scored[0]
    tied = len(scored) > 1 and abs(score - scored[1][0]) < 0.15
    if score == 1.0 and not tied:
        return MatchDecision(metadata, row["id"], score, "MATCHED_EXACT", reason)
    if score >= 0.9 and not tied:
        return MatchDecision(metadata, row["id"], score, "MATCHED_HIGH_CONFIDENCE", reason)
    return MatchDecision(metadata, row["id"], score, "REVIEW", "Partial or ambiguous metadata match")


def quality_key(metadata: InboxMetadata) -> tuple[int, int]:
    """Prefer lossless, then higher-bitrate lossy formats for duplicate candidates."""
    tiers = {".flac": 5, ".wav": 4, ".m4a": 3, ".aac": 3, ".mp3": 2, ".ogg": 1}
    return tiers.get(metadata.path.suffix.lower(), 0), metadata.bitrate_bps or 0


def scan_and_match(inbox: Path, selection: list[dict[str, str]]) -> list[MatchDecision]:
    """Discover supported files and match each independently without side effects."""
    return [match_metadata(metadata_from_path(path), selection) for path in discover_audio(inbox)]
