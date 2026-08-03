"""Build a car-ready catalog from explicitly authorized selection CSV rows.

The script intentionally does nothing with a remote URL unless the row says
``rights_confirmed=yes``. Empty or unconfirmed rows are reported as missing.
Original sources are copied/downloaded once into ``library/originals`` and are
never modified, re-encoded, or overwritten.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from car_music_manager.analyze import analyze_audio
from car_music_manager.files import (
    ensure_writable_directory,
    is_supported_audio,
    unique_output_path,
)
from car_music_manager.models import TagData
from car_music_manager.process import process_one
from car_music_manager.tags import read_tags
from car_music_manager.verify import verify_decodable
from car_music_manager.youtube import download_authorized

LOGGER = logging.getLogger(__name__)
TRUE_VALUES = {"1", "true", "yes", "y"}
REQUIRED_COLUMNS = {
    "id",
    "category",
    "artist",
    "title",
    "selected",
    "source_type",
    "source",
    "rights_confirmed",
    "status",
    "notes",
}


def _enabled(value: str) -> bool:
    return value.strip().casefold() in TRUE_VALUES


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_selection(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"Selection CSV misses columns: {', '.join(sorted(missing))}")
        return [dict(row) for row in reader]


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _source_for(row: dict[str, str], originals: Path) -> Path | None:
    source = row["source"].strip()
    if not source or not _enabled(row["rights_confirmed"]):
        return None
    if row["source_type"].strip().casefold() == "authorized_url":
        return download_authorized(source, originals)
    local = Path(source).expanduser()
    if not local.is_file():
        raise FileNotFoundError(f"Authorized local source does not exist: {local}")
    return local


def _same_record(first: dict[str, Any], second: dict[str, Any]) -> bool:
    if first["sha256"] == second["sha256"]:
        return True
    return (
        first["artist"].casefold() == second["artist"].casefold()
        and first["title"].casefold() == second["title"].casefold()
        and first["duration"] is not None
        and second["duration"] is not None
        and abs(first["duration"] - second["duration"]) <= 2
    )


def _valid_output(path: Path) -> bool:
    try:
        info = analyze_audio(path)
        verify_decodable(path)
    except Exception:
        return False
    return (
        info.codec_name == "mp3"
        and info.bitrate_bps == 256000
        and info.sample_rate == 44100
        and info.channels == 2
    )


def build(
    selection: Path,
    library: Path,
    reports: Path,
    local_sources: dict[str, Path] | None = None,
) -> list[dict[str, Any]]:
    """Process selected, authorized rows and create non-private reports."""
    originals = ensure_writable_directory(library / "originals")
    car_ready = ensure_writable_directory(library / "car-ready")
    rows = _read_selection(selection)
    results: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    known: list[dict[str, Any]] = []
    for existing in originals.rglob("*"):
        if not is_supported_audio(existing):
            continue
        try:
            existing_info = analyze_audio(existing)
            existing_tags = read_tags(existing)
            known.append(
                {
                    "id": "existing-original",
                    "artist": existing_tags.artist or "",
                    "title": existing_tags.title or "",
                    "source": str(existing),
                    "sha256": _sha256(existing),
                    "duration": existing_info.duration_seconds,
                }
            )
        except Exception as error:
            LOGGER.warning("Could not inspect existing original %s: %s", existing, error)

    for row in rows:
        result: dict[str, Any] = {
            "id": row["id"],
            "category": row["category"],
            "artist": row["artist"],
            "title": row["title"],
            "status": row["status"] or "PENDING",
            "output": "",
            "error": "",
        }
        if not _enabled(row["selected"]):
            result["status"] = "NOT_SELECTED"
            results.append(result)
            continue
        try:
            source = (local_sources or {}).get(row["id"]) or _source_for(row, originals)
            if source is None:
                result["status"] = "NEEDS_LEGAL_SOURCE"
                result["error"] = "Provide a local purchased/CD-rip file or an explicitly authorized URL."
                results.append(result)
                continue
            info = analyze_audio(source)
            record = {
                "id": row["id"],
                "artist": row["artist"],
                "title": row["title"],
                "source": str(source),
                "sha256": _sha256(source),
                "duration": info.duration_seconds,
            }
            duplicate = next((previous for previous in known if _same_record(previous, record)), None)
            if duplicate:
                result["status"] = "DUPLICATE"
                result["error"] = f"Duplicates catalog item {duplicate['id']}"
                duplicates.append({**record, "duplicate_of": duplicate["id"]})
                results.append(result)
                continue
            known.append(record)
            original = source
            if source.parent != originals:
                stem = f"{row['id']} - {row['artist']} - {row['title']}"
                original = unique_output_path(originals, stem, source.suffix.lower())
                shutil.copy2(source, original)
            target_dir = ensure_writable_directory(car_ready / row["category"])
            output_stem = f"{row['id']} - {row['artist']} - {row['title']}"
            expected = target_dir / f"{output_stem}.mp3"
            if expected.exists():
                if _valid_output(expected):
                    result["status"] = "SKIPPED_COMPLETE"
                    result["output"] = str(expected)
                else:
                    result["status"] = "OUTPUT_EXISTS_UNVERIFIED"
                    result["error"] = "Existing output is not a verified target MP3; it was left unchanged."
                results.append(result)
                continue
            inherited = read_tags(original)
            tags = TagData(
                title=row["title"],
                artist=row["artist"],
                album=row.get("album") or inherited.album,
                album_artist=inherited.album_artist,
                track_number=row["id"],
                disc_number=inherited.disc_number,
                date=inherited.date,
                genre=inherited.genre,
                comment=inherited.comment,
            )
            output = process_one(original, target_dir, tags=tags, output_stem=output_stem)
            if not _valid_output(output):
                raise ValueError("Post-process profile/decode validation failed")
            result["status"] = "COMPLETED"
            result["output"] = str(output)
        except Exception as error:
            LOGGER.error("Catalog item %s failed: %s", row["id"], error)
            result["status"] = "FAILED"
            result["error"] = str(error)
        results.append(result)

    reports.mkdir(parents=True, exist_ok=True)
    _write_csv(
        reports / "catalog-summary.csv",
        results,
        ["id", "category", "artist", "title", "status", "output", "error"],
    )
    _write_csv(
        reports / "missing-sources.csv",
        [result for result in results if result["status"] == "NEEDS_LEGAL_SOURCE"],
        ["id", "category", "artist", "title", "status", "error"],
    )
    _write_csv(
        reports / "duplicates.csv",
        duplicates,
        ["id", "duplicate_of", "artist", "title", "sha256", "duration"],
    )
    with (reports / "process-results.json").open("w", encoding="utf-8-sig") as handle:
        json.dump(results, handle, ensure_ascii=False, indent=2)
    counts = Counter(item["status"] for item in results)
    verified = [Path(item["output"]) for item in results if item["status"] in {"COMPLETED", "SKIPPED_COMPLETE"}]
    capacity = sum(path.stat().st_size for path in verified if path.exists())
    verification = [
        "# Final verification",
        "",
        f"- Total tracks: {len(rows)}",
        f"- Completed: {counts['COMPLETED']}",
        f"- Skipped complete: {counts['SKIPPED_COMPLETE']}",
        f"- Missing legal source: {counts['NEEDS_LEGAL_SOURCE']}",
        f"- Failed: {counts['FAILED']}",
        f"- Duplicates: {counts['DUPLICATE']}",
        f"- Verified output bytes: {capacity}",
        "",
        "Outputs marked completed/skipped complete passed ffprobe target checks and full FFmpeg decoding.",
    ]
    (reports / "final-verification.md").write_text("\n".join(verification) + "\n", encoding="utf-8")
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a car catalog from explicitly authorized sources")
    parser.add_argument("--selection", type=Path, default=Path("data/selection.csv"))
    parser.add_argument("--library", type=Path, default=Path("library"))
    parser.add_argument("--reports", type=Path, default=Path("reports"))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    build(args.selection, args.library, args.reports)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
