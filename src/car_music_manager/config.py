"""Optional local TOML configuration loading."""

from __future__ import annotations

import tomllib
from dataclasses import replace
from pathlib import Path

from .models import ProcessingOptions


def load_config(path: Path | None) -> tuple[ProcessingOptions, str, str]:
    """Load target options and tool names; defaults apply when no config is supplied."""
    if path is None:
        return ProcessingOptions(), "ffmpeg", "ffprobe"
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    output = data.get("output", {})
    tools = data.get("tools", {})
    defaults = ProcessingOptions()
    options = replace(
        defaults,
        lufs=float(output.get("lufs", defaults.lufs)),
        true_peak_db=float(output.get("true_peak_db", defaults.true_peak_db)),
        bitrate_kbps=int(output.get("bitrate_kbps", defaults.bitrate_kbps)),
        sample_rate=int(output.get("sample_rate", defaults.sample_rate)),
        channels=int(output.get("channels", defaults.channels)),
    )
    return options, str(tools.get("ffmpeg", "ffmpeg")), str(tools.get("ffprobe", "ffprobe"))
