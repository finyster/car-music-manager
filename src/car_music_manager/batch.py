"""Failure-isolated local and selected remote batch processing."""

from __future__ import annotations

import csv
import logging
import tempfile
from pathlib import Path

from .analyze import analyze_audio
from .errors import CarMusicError
from .files import discover_audio
from .models import ItemResult, ProcessingOptions
from .process import process_one
from .reporting import check_output_space, estimate_output_bytes
from .youtube import download_authorized

LOGGER = logging.getLogger(__name__)
_SELECTED = {"1", "true", "yes", "y", "selected", "x"}


def selected_csv_sources(manifest: Path) -> list[str]:
    """Read selected local paths or authorized URLs from an exported CSV."""
    with manifest.open(newline="", encoding="utf-8-sig") as handle:
        rows = csv.DictReader(handle)
        if not rows.fieldnames or "source" not in rows.fieldnames:
            raise CarMusicError("CSV must have a source column")
        return [
            row["source"]
            for row in rows
            if row.get("source") and row.get("selected", "").strip().casefold() in _SELECTED
        ]


def process_paths(
    sources: list[Path],
    output_dir: Path,
    *,
    options: ProcessingOptions | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
    fail_fast: bool = False,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
) -> list[ItemResult]:
    """Process all local sources, retaining a result for every attempted file."""
    options = options or ProcessingOptions()
    expanded: list[Path] = []
    for source in sources:
        expanded.extend(discover_audio(source))
    estimated = 0
    for source in expanded:
        try:
            size = estimate_output_bytes(analyze_audio(source, ffprobe), options)
            estimated += size or source.stat().st_size
        except Exception as error:  # Analysis is advisory; encoding yields the final status.
            LOGGER.warning("Could not estimate %s: %s", source, error)
            estimated += source.stat().st_size
    free, enough = check_output_space(output_dir, estimated)
    if not enough:
        raise CarMusicError(
            f"Insufficient output space: need about {estimated} bytes, only {free} available"
        )
    results: list[ItemResult] = []
    for source in expanded:
        target = output_dir / f"{source.stem}.mp3"
        if target.exists() and not overwrite:
            results.append(ItemResult(source, "skipped", target, "already exists"))
            continue
        if dry_run:
            results.append(ItemResult(source, "planned", target))
            continue
        try:
            output = process_one(
                source, output_dir, options=options, overwrite=overwrite, ffmpeg=ffmpeg
            )
            results.append(ItemResult(source, "completed", output))
        except Exception as error:
            LOGGER.error("Failed to process %s: %s", source, error)
            results.append(ItemResult(source, "failed", error=str(error)))
            if fail_fast:
                break
    return results


def process_manifest(manifest: Path, output_dir: Path, **kwargs: object) -> list[ItemResult]:
    """Process selected local paths and explicitly authorized remote URLs from CSV."""
    selected = selected_csv_sources(manifest)
    local = [Path(item) for item in selected if not item.startswith(("http://", "https://"))]
    results = process_paths(local, output_dir, **kwargs) if local else []
    urls = [item for item in selected if item.startswith(("http://", "https://"))]
    if not urls:
        return results
    if kwargs.get("dry_run"):
        results.extend(ItemResult(Path(url), "planned") for url in urls)
        return results
    with tempfile.TemporaryDirectory(prefix="car-music-download-") as temporary:
        for url in urls:
            try:
                downloaded = download_authorized(url, Path(temporary))
                results.extend(process_paths([downloaded], output_dir, **kwargs))
            except Exception as error:
                results.append(ItemResult(Path(url), "failed", error=str(error)))
                if kwargs.get("fail_fast"):
                    break
    return results
