"""Render a clickable, metadata-only YouTube candidate review document."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
from collections import defaultdict
from pathlib import Path

from build_catalog import _read_selection, _write_csv

from car_music_manager.library_layout import LibraryLayout

LOCKED_SELECTION_SHA256 = "278DD4D0D0B7269BD4BFB7A853B4A6E6E8D82468C7D5D4E3D4A33D96EF80E029"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _duration(seconds: str) -> str:
    try:
        total = int(seconds)
    except ValueError:
        return "Unknown"
    return f"{total // 60}:{total % 60:02d}"


def _notes(candidate: dict[str, str] | None, review: dict[str, str] | None) -> str:
    if candidate is None:
        return "No sufficiently relevant candidate was retained; do not substitute another song."
    notes = []
    signal = candidate["official_signal"]
    if signal == "UNVERIFIED":
        notes.append("Channel is unverified; possible non-official upload.")
    elif signal == "ARTIST_NAMED_CHANNEL":
        notes.append("Artist-named channel signal; verify the channel independently.")
    elif signal == "LABEL_OR_OFFICIAL_CHANNEL":
        notes.append("Label/official-channel signal; verify the uploader independently.")
    elif signal == "ARTIST_TOPIC":
        notes.append("Artist Topic signal; this is still not download permission.")
    if candidate["title_match"] != "EXACT_TITLE":
        notes.append("Video title is not an exact normalized song-name match.")
    try:
        duration = int(candidate["duration"])
        if duration < 60 or duration > 600:
            notes.append("Duration is unusual; confirm it is the full studio release.")
    except ValueError:
        notes.append("Duration is unavailable; confirm it manually.")
    if review and review.get("review_status") == "MANUAL_REVIEW":
        notes.append(f"Review flags: {review.get('action') or 'manual review required'}.")
    return " ".join(notes) or "Candidate found; legal authorization is still required."


def _candidate_html(kind: str, candidate: dict[str, str], notes: str) -> str:
    url = html.escape(candidate["url"], quote=True)
    fields = [
        f"<strong>{html.escape(kind)}</strong>",
        f"影片：{html.escape(candidate['video_title'])}",
        f"頻道：{html.escape(candidate['channel'])}",
        f"時長：{html.escape(_duration(candidate['duration']))}",
        f"官方訊號：{html.escape(candidate['official_signal'])}",
        f'<a href="{url}" target="_blank" rel="noopener">開啟 YouTube</a>',
        f"原因：{html.escape(notes)}",
    ]
    return "<li>" + "<br>".join(fields) + "</li>"


def generate(selection_path: Path, reports: Path, expected_sha256: str = LOCKED_SELECTION_SHA256) -> dict[str, int]:
    """Verify the locked catalog and write HTML plus an intentionally blank approval CSV."""
    actual = hashlib.sha256(selection_path.read_bytes()).hexdigest().upper()
    if actual != expected_sha256.upper():
        raise ValueError(f"selection.csv SHA-256 mismatch: expected {expected_sha256}, got {actual}")
    selection = _read_selection(selection_path)
    candidates_by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    for candidate in _read_csv(reports / "youtube-candidates.csv"):
        candidates_by_id[candidate["id"]].append(candidate)
    for candidates in candidates_by_id.values():
        candidates.sort(key=lambda candidate: int(candidate["rank"]))
    reviews = {row["id"]: row for row in _read_csv(reports / "youtube-review.csv")}

    approved_rows: list[dict[str, str]] = []
    sections: list[str] = []
    backup_songs = 0
    manual_count = 0
    for row in selection:
        item_id = row["id"]
        candidates = candidates_by_id[item_id][:3]
        recommended = candidates[0] if candidates else None
        alternatives = candidates[1:]
        review = reviews.get(item_id)
        notes = _notes(recommended, review)
        if alternatives:
            backup_songs += 1
        if (review and review.get("review_status") == "MANUAL_REVIEW") or (recommended and recommended["official_signal"] == "UNVERIFIED"):
            manual_count += 1
        candidate_html = []
        if recommended:
            candidate_html.append(_candidate_html("推薦候選", recommended, notes))
            for index, alternative in enumerate(alternatives, start=1):
                candidate_html.append(_candidate_html(f"備選 {index}", alternative, _notes(alternative, review)))
        else:
            candidate_html.append(f"<li><strong>NO_CANDIDATE</strong><br>{html.escape(notes)}</li>")
        sections.append(
            "<section>"
            f"<h2>{html.escape(item_id)} — {html.escape(row['artist'])} — {html.escape(row['title'])}</h2>"
            f"<p>授權狀態：<strong>NEEDS_LEGAL_SOURCE</strong></p><ul>{''.join(candidate_html)}</ul>"
            "</section>"
        )
        approved_rows.append(
            {
                "id": item_id,
                "artist": row["artist"],
                "title": row["title"],
                "recommended_url": recommended["url"] if recommended else "",
                "approved": "",
                "review_notes": notes,
            }
        )
    document = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><title>YouTube manual review</title>
<style>body{font-family:Segoe UI,Microsoft JhengHei,sans-serif;max-width:980px;margin:auto;padding:24px;line-height:1.5}section{border-bottom:1px solid #ccc;padding:12px 0}h2{font-size:1.1rem}a{color:#0645ad}strong{color:#693}</style>
</head><body><h1>YouTube 候選人工審核</h1><p>此文件僅含 metadata 候選，未下載媒體。所有連結仍需使用者確認合法來源與下載權利。</p>"""
    document += "\n".join(sections) + "</body></html>\n"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "youtube-manual-review.html").write_text(document, encoding="utf-8")
    _write_csv(
        reports / "approved-links.csv",
        approved_rows,
        ["id", "artist", "title", "recommended_url", "approved", "review_notes"],
    )
    return {"recommended": sum(bool(candidates_by_id[row["id"]]) for row in selection), "backups": backup_songs, "manual": manual_count}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create clickable YouTube candidate review documents")
    parser.add_argument("--selection", type=Path, default=Path("data/selection.csv"))
    parser.add_argument("--reports", type=Path, default=Path("reports"))
    parser.add_argument("--library-root", type=Path, help="Use <root>/reports for private documents")
    args = parser.parse_args(argv)
    reports = LibraryLayout.from_root(args.library_root).ensure().reports if args.library_root else args.reports
    generate(args.selection, reports)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
