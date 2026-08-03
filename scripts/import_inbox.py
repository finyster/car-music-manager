"""Match authorized local inbox files to the catalog and build safe outputs."""

from __future__ import annotations

import argparse
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

from build_catalog import _enabled, _read_selection, _write_csv, build

from car_music_manager.inbox import MatchDecision, quality_key, scan_and_match

LOGGER = logging.getLogger(__name__)


def _decision_row(decision: MatchDecision) -> dict[str, Any]:
    return {
        "source": str(decision.source.path),
        "artist": decision.source.artist,
        "title": decision.source.title,
        "album": decision.source.album,
        "format": decision.source.path.suffix.lower(),
        "bitrate_bps": decision.source.bitrate_bps or "",
        "catalog_id": decision.catalog_id or "",
        "confidence": f"{decision.confidence:.2f}",
        "status": decision.status,
        "reason": decision.reason,
    }


def _write_match_reports(reports: Path, decisions: list[MatchDecision]) -> dict[str, Path]:
    reports.mkdir(parents=True, exist_ok=True)
    fields = [
        "source",
        "artist",
        "title",
        "album",
        "format",
        "bitrate_bps",
        "catalog_id",
        "confidence",
        "status",
        "reason",
    ]
    scan_rows = [_decision_row(decision) for decision in decisions]
    _write_csv(reports / "inbox-scan.csv", scan_rows, fields)
    accepted = [
        decision
        for decision in decisions
        if decision.status in {"MATCHED_EXACT", "MATCHED_HIGH_CONFIDENCE"}
    ]
    grouped: dict[str, list[MatchDecision]] = defaultdict(list)
    for decision in accepted:
        assert decision.catalog_id is not None
        grouped[decision.catalog_id].append(decision)
    winners: dict[str, Path] = {}
    matched_rows: list[dict[str, Any]] = []
    for catalog_id, candidates in grouped.items():
        candidates.sort(key=lambda item: (quality_key(item.source), str(item.source.path).casefold()), reverse=True)
        winner = candidates[0]
        winners[catalog_id] = winner.source.path
        for candidate in candidates:
            row = _decision_row(candidate)
            row["chosen_for_import"] = "yes" if candidate is winner else "no"
            if candidate is not winner:
                row["reason"] = "Lower-quality duplicate candidate for this catalog item"
            matched_rows.append(row)
    _write_csv(reports / "matched-files.csv", matched_rows, [*fields, "chosen_for_import"])
    _write_csv(
        reports / "match-review.csv",
        [_decision_row(decision) for decision in decisions if decision.status == "REVIEW"],
        fields,
    )
    _write_csv(
        reports / "unmatched-files.csv",
        [_decision_row(decision) for decision in decisions if decision.status == "UNMATCHED"],
        fields,
    )
    return winners


def _write_dry_summary(selection: list[dict[str, str]], winners: dict[str, Path], reports: Path) -> None:
    rows = []
    for item in selection:
        status = "PLANNED_IMPORT" if item["id"] in winners else "NEEDS_LEGAL_SOURCE"
        rows.append({**item, "status": status, "output": "", "error": ""})
    _write_csv(
        reports / "catalog-summary.csv",
        rows,
        ["id", "category", "artist", "title", "status", "output", "error"],
    )


def run(inbox: Path, selection_path: Path, library: Path, reports: Path, dry_run: bool = False) -> int:
    """Scan inbox, write conservative match reports, and import selected winners."""
    if inbox.exists() and not inbox.is_dir():
        raise ValueError(f"Inbox is not a directory: {inbox}")
    inbox.mkdir(parents=True, exist_ok=True)
    selection = [item for item in _read_selection(selection_path) if _enabled(item["selected"])]
    decisions = scan_and_match(inbox, selection)
    winners = _write_match_reports(reports, decisions)
    if dry_run:
        _write_dry_summary(selection, winners, reports)
        return 0
    build(selection_path, library, reports, local_sources=winners)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import authorized local inbox music conservatively")
    parser.add_argument("--inbox", type=Path, default=Path("library/inbox"))
    parser.add_argument("--selection", type=Path, default=Path("data/selection.csv"))
    parser.add_argument("--library", type=Path, default=Path("library"))
    parser.add_argument("--reports", type=Path, default=Path("reports"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    return run(args.inbox, args.selection, args.library, args.reports, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
