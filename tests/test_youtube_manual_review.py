import csv
import sys
from pathlib import Path

import pytest


def _load_module():
    scripts = Path(__file__).parents[1] / "scripts"
    sys.path.insert(0, str(scripts))
    import generate_youtube_manual_review

    return scripts, generate_youtube_manual_review


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_manual_review_renders_links_and_leaves_approval_blank(tmp_path: Path) -> None:
    scripts, module = _load_module()
    try:
        fields = [
            "id", "artist", "title", "rank", "video_title", "channel", "url", "duration",
            "upload_date", "official_signal", "title_match", "best_candidate", "authorization_status",
        ]
        _write_csv(
            tmp_path / "youtube-candidates.csv",
            fields,
            [
                {"id": "01", "artist": "鄧麗君", "title": "月亮代表我的心", "rank": "1", "video_title": "月亮代表我的心", "channel": "Artist Official", "url": "https://example.test/one", "duration": "210", "upload_date": "", "official_signal": "ARTIST_NAMED_CHANNEL", "title_match": "EXACT_TITLE", "best_candidate": "yes", "authorization_status": "NEEDS_LEGAL_SOURCE"},
                {"id": "01", "artist": "鄧麗君", "title": "月亮代表我的心", "rank": "2", "video_title": "月亮代表我的心 (Official Audio)", "channel": "Label", "url": "https://example.test/two", "duration": "211", "upload_date": "", "official_signal": "LABEL_OR_OFFICIAL_CHANNEL", "title_match": "EXACT_TITLE", "best_candidate": "", "authorization_status": "NEEDS_LEGAL_SOURCE"},
            ],
        )
        _write_csv(
            tmp_path / "youtube-review.csv",
            ["id", "review_status", "action"],
            [{"id": "01", "review_status": "MANUAL_REVIEW", "action": "NAME_REVIEW"}],
        )
        selection = Path(__file__).parents[1] / "data" / "selection.csv"

        summary = module.generate(selection, tmp_path)

        html = (tmp_path / "youtube-manual-review.html").read_text(encoding="utf-8")
        with (tmp_path / "approved-links.csv").open(newline="", encoding="utf-8-sig") as handle:
            approved = list(csv.DictReader(handle))
        assert "https://example.test/one" in html
        assert "備選 1" in html
        assert approved[0]["approved"] == ""
        assert approved[0]["recommended_url"] == "https://example.test/one"
        assert summary["recommended"] == 1
    finally:
        sys.path.remove(str(scripts))


def test_manual_review_stops_when_selection_hash_is_wrong(tmp_path: Path) -> None:
    scripts, module = _load_module()
    try:
        selection = tmp_path / "selection.csv"
        selection.write_text("changed", encoding="utf-8")

        with pytest.raises(ValueError, match="SHA-256 mismatch"):
            module.generate(selection, tmp_path)
    finally:
        sys.path.remove(str(scripts))
