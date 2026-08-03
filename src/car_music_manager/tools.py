"""Small, safely invoked wrappers around FFmpeg tools."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

from .errors import ExternalToolError


def run_command(
    command: Sequence[str], *, timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    """Run an external command without a shell and turn OS errors into app errors."""
    try:
        return subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            timeout=timeout,
        )
    except FileNotFoundError as error:
        raise ExternalToolError(f"Executable not found: {command[0]}") from error
    except subprocess.TimeoutExpired as error:
        raise ExternalToolError(f"Command timed out: {command[0]}") from error


def require_success(
    result: subprocess.CompletedProcess[str], description: str
) -> subprocess.CompletedProcess[str]:
    """Raise a concise error when a completed tool invocation failed."""
    if result.returncode:
        message = (result.stderr or result.stdout).strip()
        raise ExternalToolError(
            f"{description} failed (exit {result.returncode}): {message[-1000:]}"
        )
    return result


def ffprobe_json(path: Path, ffprobe: str = "ffprobe") -> dict[str, object]:
    """Read media metadata in a machine-safe JSON form."""
    result = run_command(
        [ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]
    )
    require_success(result, f"ffprobe for {path}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ExternalToolError(f"ffprobe returned invalid JSON for {path}") from error
