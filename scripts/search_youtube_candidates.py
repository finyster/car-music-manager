"""Write metadata-only YouTube candidate and review reports for the catalog."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from build_catalog import _enabled, _read_selection, _write_csv

from car_music_manager.library_layout import LibraryLayout
from car_music_manager.youtube_candidates import YoutubeCandidate, search_youtube

LOGGER = logging.getLogger(__name__)


def _candidate_row(catalog_id: str, candidate: YoutubeCandidate, rank: int) -> dict[str, Any]:
    return {
        "id": catalog_id,
        "artist": candidate.artist,
        "title": candidate.title,
        "rank": rank,
        "video_title": candidate.video_title,
        "channel": candidate.channel,
        "url": candidate.url,
        "duration": candidate.duration or "",
        "upload_date": candidate.upload_date or "",
        "official_signal": candidate.official_signal,
        "best_candidate": "yes" if rank == 1 else "",
        "authorization_status": "NEEDS_LEGAL_SOURCE",
    }


def search(selection_path: Path, reports: Path, max_candidates: int = 5) -> list[dict[str, Any]]:
    """Search each selected catalog row once and create review-only CSV reports."""
    selection = [row for row in _read_selection(selection_path) if _enabled(row["selected"])]
    candidates: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    for row in selection:
        try:
            found = search_youtube(row["artist"], row["title"], max_candidates)
        except Exception as error:
            LOGGER.warning("Search failed for %s: %s", row["id"], error)
            found = []
        for rank, candidate in enumerate(found, start=1):
            candidates.append(_candidate_row(row["id"], candidate, rank))
        best = found[0] if found else None
        review.append(
            {
                "id": row["id"],
                "artist": row["artist"],
                "title": row["title"],
                "best_url": best.url if best else "",
                "official_signal": best.official_signal if best else "NO_CANDIDATE",
                "authorization_status": "NEEDS_LEGAL_SOURCE",
                "action": "Review candidate; add only a separately authorized source to selection.csv.",
            }
        )
    candidate_fields = [
        "id",
        "artist",
        "title",
        "rank",
        "video_title",
        "channel",
        "url",
        "duration",
        "upload_date",
        "official_signal",
        "best_candidate",
        "authorization_status",
    ]
    _write_csv(reports / "youtube-candidates.csv", candidates, candidate_fields)
    _write_csv(
        reports / "youtube-review.csv",
        review,
        ["id", "artist", "title", "best_url", "official_signal", "authorization_status", "action"],
    )
    return review


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Search YouTube metadata without downloading audio")
    parser.add_argument("--selection", type=Path, default=Path("data/selection.csv"))
    parser.add_argument("--reports", type=Path, default=Path("reports"))
    parser.add_argument("--library-root", type=Path, help="Use <root>/reports for private reports")
    parser.add_argument("--max-candidates", type=int, default=5)
    args = parser.parse_args(argv)
    if not 1 <= args.max_candidates <= 5:
        parser.error("--max-candidates must be between 1 and 5")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    reports = LibraryLayout.from_root(args.library_root).ensure().reports if args.library_root else args.reports
    search(args.selection, reports, args.max_candidates)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
