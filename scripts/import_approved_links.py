"""Import explicitly user-authorized first-choice review links without editing the catalog."""

from __future__ import annotations

import argparse
import csv
import tempfile
from pathlib import Path

from build_catalog import _read_selection, _write_csv, build
from generate_youtube_manual_review import LOCKED_SELECTION_SHA256

from car_music_manager.library_layout import LibraryLayout


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def import_links(selection: Path, library_root: Path, *, confirm_authorized: bool) -> list[dict[str, object]]:
    """Create a temporary authorized manifest and run the existing safe build path."""
    if not confirm_authorized:
        raise ValueError("Pass --confirm-authorized only after confirming download rights for every link.")
    actual = _sha256(selection)
    if actual != LOCKED_SELECTION_SHA256:
        raise ValueError(f"selection.csv SHA-256 mismatch: expected {LOCKED_SELECTION_SHA256}, got {actual}")
    layout = LibraryLayout.from_root(library_root).ensure()
    rows = _read_selection(selection)
    with (layout.reports / "approved-links.csv").open(newline="", encoding="utf-8-sig") as handle:
        approved = {row["id"]: row for row in csv.DictReader(handle)}
    missing = [row["id"] for row in rows if not approved.get(row["id"], {}).get("recommended_url")]
    if missing:
        raise ValueError(f"Missing recommended URL for catalog items: {', '.join(missing)}")
    fields = list(rows[0])
    with tempfile.TemporaryDirectory(prefix="authorized-manifest-", dir=layout.temp) as directory:
        manifest = Path(directory) / "selection.csv"
        authorized_rows = []
        for row in rows:
            authorized_rows.append(
                {
                    **row,
                    "source_type": "authorized_url",
                    "source": approved[row["id"]]["recommended_url"],
                    "rights_confirmed": "yes",
                }
            )
        _write_csv(manifest, authorized_rows, fields)
        return build(manifest, layout.root, layout.reports, temp=layout.temp)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import user-authorized recommended YouTube links")
    parser.add_argument("--library-root", type=Path, required=True)
    parser.add_argument("--selection", type=Path, default=Path("data/selection.csv"))
    parser.add_argument("--confirm-authorized", action="store_true")
    args = parser.parse_args(argv)
    import_links(args.selection, args.library_root, confirm_authorized=args.confirm_authorized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
