"""Media analysis through ffprobe."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import AudioInfo
from .tools import ffprobe_json


def _number(value: object, kind: type[int] | type[float]) -> int | float | None:
    try:
        return kind(str(value))
    except (TypeError, ValueError):
        return None


def analyze_audio(path: Path, ffprobe: str = "ffprobe") -> AudioInfo:
    """Return normalized details for the first audio stream in *path*."""
    payload = ffprobe_json(path, ffprobe)
    streams = payload.get("streams", [])
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})
    fmt: dict[str, Any] = payload.get("format", {})
    return AudioInfo(
        path=path,
        format_name=fmt.get("format_name"),
        duration_seconds=_number(fmt.get("duration"), float),
        # For MP3, the container-level bit rate includes tag/container overhead.
        # Prefer the audio stream's declared rate so a 256 kbps CBR stream is
        # reported as 256000 rather than a slightly higher averaged value.
        bitrate_bps=_number(audio.get("bit_rate") or fmt.get("bit_rate"), int),
        sample_rate=_number(audio.get("sample_rate"), int),
        channels=_number(audio.get("channels"), int),
        codec_name=audio.get("codec_name"),
    )
