"""argparse command-line interface for car-music-manager."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .analyze import analyze_audio
from .batch import process_manifest, process_paths
from .config import load_config
from .files import discover_audio, ensure_writable_directory
from .models import ItemResult
from .reporting import as_json, write_report
from .verify import verify_decodable
from .youtube import export_selection, list_youtube


def _add_processing_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--dry-run", action="store_true", help="Show planned outputs without encoding"
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Replace matching output file names"
    )
    parser.add_argument(
        "--fail-fast", action="store_true", help="Stop after the first item failure"
    )
    parser.add_argument("--report", type=Path, help="Write a .json or .csv processing report")


def build_parser() -> argparse.ArgumentParser:
    """Create the parser without inspecting files or tools at import time."""
    parser = argparse.ArgumentParser(
        prog="car-music", description="Prepare audio safely for car USB playback"
    )
    parser.add_argument("--config", type=Path, help="Optional TOML configuration file")
    parser.add_argument("--verbose", action="store_true", help="Show debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Find supported audio files")
    scan.add_argument("source", type=Path)
    scan.add_argument("--report", type=Path, help="Write .json or .csv scan report")

    analyze = sub.add_parser("analyze", help="Probe audio format and stream properties")
    analyze.add_argument("source", type=Path)

    process = sub.add_parser("process", help="Normalize a file or folder into target MP3 files")
    process.add_argument("source", type=Path)
    process.add_argument("output", type=Path)
    _add_processing_flags(process)

    verify = sub.add_parser("verify", help="Decode-test one file or a folder")
    verify.add_argument("source", type=Path)

    listing = sub.add_parser(
        "list", help="Export a YouTube URL, playlist, or channel as selectable CSV"
    )
    listing.add_argument("url")
    listing.add_argument("csv", type=Path)

    batch = sub.add_parser("batch", help="Process selected rows from a CSV manifest")
    batch.add_argument("manifest", type=Path)
    batch.add_argument("output", type=Path)
    _add_processing_flags(batch)
    return parser


def _scan_results(paths: list[Path]) -> list[ItemResult]:
    return [
        ItemResult(
            path, "found", details={"extension": path.suffix.lower(), "bytes": path.stat().st_size}
        )
        for path in paths
    ]


def _emit_results(results: list[ItemResult], report: Path | None) -> int:
    if report:
        write_report(results, report)
    print(as_json([result.to_dict() for result in results]))
    return 1 if any(result.status == "failed" for result in results) else 0


def main(argv: list[str] | None = None) -> int:
    """Execute the CLI and return a conventional process exit status."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s: %(message)s"
    )
    try:
        options, ffmpeg, ffprobe = load_config(args.config)
        if args.command == "scan":
            return _emit_results(_scan_results(discover_audio(args.source)), args.report)
        if args.command == "analyze":
            paths = discover_audio(args.source)
            print(as_json([analyze_audio(path, ffprobe).to_dict() for path in paths]))
            return 0
        if args.command == "process":
            ensure_writable_directory(args.output)
            results = process_paths(
                [args.source],
                args.output,
                options=options,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
                fail_fast=args.fail_fast,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
            )
            return _emit_results(results, args.report)
        if args.command == "verify":
            results: list[ItemResult] = []
            for path in discover_audio(args.source):
                try:
                    verify_decodable(path, ffmpeg)
                    results.append(ItemResult(path, "verified"))
                except Exception as error:
                    results.append(ItemResult(path, "failed", error=str(error)))
            return _emit_results(results, None)
        if args.command == "list":
            entries = list_youtube(args.url)
            export_selection(entries, args.csv)
            print(as_json([entry.__dict__ for entry in entries]))
            return 0
        if args.command == "batch":
            ensure_writable_directory(args.output)
            results = process_manifest(
                args.manifest,
                args.output,
                options=options,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
                fail_fast=args.fail_fast,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
            )
            return _emit_results(results, args.report)
    except Exception as error:
        logging.getLogger(__name__).error("%s", error)
        return 2
    return 2  # pragma: no cover - argparse constrains command values


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
