"""Two-pass loudness normalization and safe MP3 output."""

from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
from pathlib import Path

from .files import ensure_writable_directory, unique_output_path
from .models import ProcessingOptions, TagData
from .tags import read_tags, write_id3v23
from .tools import require_success, run_command
from .verify import verify_decodable

LOGGER = logging.getLogger(__name__)


def _loudnorm_filter(options: ProcessingOptions, measurements: dict[str, str] | None = None) -> str:
    base = f"loudnorm=I={options.lufs}:TP={options.true_peak_db}:LRA=11"
    if not measurements:
        return f"{base}:print_format=json"
    fields = {
        "measured_I": measurements["input_i"],
        "measured_TP": measurements["input_tp"],
        "measured_LRA": measurements["input_lra"],
        "measured_thresh": measurements["input_thresh"],
        "offset": measurements["target_offset"],
    }
    suffix = ":".join(f"{key}={value}" for key, value in fields.items())
    return f"{base}:{suffix}:linear=true:print_format=summary"


def _measurement_from_stderr(stderr: str) -> dict[str, str]:
    """Extract the JSON report emitted by loudnorm's analysis pass."""
    matches = re.findall(r"\{\s*\"input_i\".*?\}", stderr, re.DOTALL)
    if not matches:
        raise ValueError("FFmpeg loudnorm measurement JSON was not found")
    data = json.loads(matches[-1])
    required = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    if any(key not in data for key in required):
        raise ValueError("FFmpeg loudnorm measurement JSON was incomplete")
    return {key: str(data[key]) for key in required}


def _analysis_pass(source: Path, options: ProcessingOptions, ffmpeg: str) -> dict[str, str]:
    result = run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-i",
            str(source),
            "-af",
            _loudnorm_filter(options),
            "-f",
            "null",
            "-",
        ]
    )
    require_success(result, f"Loudness analysis for {source}")
    return _measurement_from_stderr(result.stderr)


def _encode_pass(
    source: Path,
    destination: Path,
    options: ProcessingOptions,
    measurements: dict[str, str],
    ffmpeg: str,
) -> None:
    result = run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-y",
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-vn",
            "-af",
            _loudnorm_filter(options, measurements),
            "-ar",
            str(options.sample_rate),
            "-ac",
            str(options.channels),
            "-c:a",
            "libmp3lame",
            "-b:a",
            f"{options.bitrate_kbps}k",
            "-minrate",
            f"{options.bitrate_kbps}k",
            "-maxrate",
            f"{options.bitrate_kbps}k",
            "-write_xing",
            "0",
            str(destination),
        ]
    )
    require_success(result, f"Encoding {source}")


def process_one(
    source: Path,
    output_dir: Path,
    *,
    options: ProcessingOptions | None = None,
    overwrite: bool = False,
    ffmpeg: str = "ffmpeg",
    tags: TagData | None = None,
) -> Path:
    """Normalize one source and atomically publish a verified MP3 output.

    The source is never modified. The final output is created only after the
    temporary encode has been tagged and successfully decoded.
    """
    options = options or ProcessingOptions()
    output_dir = ensure_writable_directory(output_dir)
    final_path = (
        output_dir / f"{source.stem}.mp3"
        if overwrite
        else unique_output_path(output_dir, source.stem)
    )
    if final_path.exists() and not overwrite:
        raise FileExistsError(final_path)
    with tempfile.TemporaryDirectory(prefix="car-music-", dir=output_dir) as temp_dir:
        temporary = Path(temp_dir) / "encoded.mp3"
        measurements = _analysis_pass(source, options, ffmpeg)
        _encode_pass(source, temporary, options, measurements, ffmpeg)
        write_id3v23(temporary, tags or read_tags(source))
        verify_decodable(temporary, ffmpeg)
        if final_path.exists() and not overwrite:
            raise FileExistsError(final_path)
        shutil.move(str(temporary), str(final_path))
    LOGGER.info("Processed %s -> %s", source, final_path)
    return final_path
