"""Machine-readable result reporting and capacity checks."""

from __future__ import annotations

import csv
import json
import shutil
from collections.abc import Iterable
from dataclasses import asdict, is_dataclass
from pathlib import Path

try:
    import psutil
except ImportError:  # Allows diagnostic commands in constrained Python environments.
    psutil = None  # type: ignore[assignment]

from .models import AudioInfo, ItemResult, ProcessingOptions


def estimate_output_bytes(info: AudioInfo, options: ProcessingOptions) -> int | None:
    """Estimate target CBR output size with a modest MP3/container allowance."""
    if info.duration_seconds is None:
        return None
    return int(info.duration_seconds * options.bitrate_kbps * 1000 / 8 * 1.02)


def check_output_space(output_dir: Path, estimated_bytes: int) -> tuple[int, bool]:
    """Return available bytes and whether capacity is sufficient."""
    free = psutil.disk_usage(output_dir).free if psutil else shutil.disk_usage(output_dir).free
    return free, free >= estimated_bytes


def write_report(results: Iterable[ItemResult], destination: Path) -> None:
    """Write results to JSON or CSV based on the requested file extension."""
    rows = [item.to_dict() for item in results]
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.suffix.lower() == ".csv":
        keys = ("source", "status", "output", "error", "details")
        with destination.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=keys)
            writer.writeheader()
            for row in rows:
                row["details"] = json.dumps(row["details"], ensure_ascii=False)
                writer.writerow(row)
        return
    if destination.suffix.lower() != ".json":
        raise ValueError("Report format must be .json or .csv")
    with destination.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=2)


def as_json(value: object) -> str:
    """Serialize dataclasses and paths in a CLI-friendly way."""

    def default(item: object) -> object:
        if isinstance(item, Path):
            return str(item)
        if is_dataclass(item):
            return asdict(item)
        raise TypeError(f"Cannot serialize {type(item).__name__}")

    return json.dumps(value, ensure_ascii=False, indent=2, default=default)
