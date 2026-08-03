"""Output decode validation."""

from __future__ import annotations

from pathlib import Path

from .tools import require_success, run_command


def verify_decodable(path: Path, ffmpeg: str = "ffmpeg") -> None:
    """Fully decode a media file into a null sink; raise on corrupt output."""
    result = run_command([ffmpeg, "-v", "error", "-i", str(path), "-f", "null", "-"])
    require_success(result, f"Decode verification for {path}")
