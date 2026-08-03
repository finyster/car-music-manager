"""Safely export verified car-ready MP3 files to exactly one removable USB drive."""

from __future__ import annotations

import argparse
from pathlib import Path

from car_music_manager.errors import ValidationError
from car_music_manager.usb_export import format_summary, run_auto_export


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export verified car-ready MP3 files to one USB drive")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--auto-usb", action="store_true", help="Require exactly one removable Windows drive")
    parser.add_argument("--folder", default="Music")
    parser.add_argument("--layout", choices=["flat"], default="flat")
    parser.add_argument("--verify", action="store_true", help="Require full source and copied-file checks")
    parser.add_argument("--report-root", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not args.auto_usb:
        parser.error("--auto-usb is required; this script never guesses a target disk.")
    if not args.verify:
        parser.error("--verify is required; USB exports are always fully verified.")
    try:
        drive, entries = run_auto_export(
            args.source,
            args.folder,
            args.report_root,
            dry_run=args.dry_run,
        )
    except (ValidationError, KeyboardInterrupt) as error:
        print(f"USB export stopped safely: {error}")
        return 2
    print(format_summary(entries, drive))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
