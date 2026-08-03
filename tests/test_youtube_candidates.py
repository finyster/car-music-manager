import sys
from pathlib import Path

from car_music_manager.youtube_candidates import (
    YoutubeCandidate,
    candidate_from_entry,
    is_excluded,
    official_signal,
)


def test_excludes_non_studio_candidate_titles() -> None:
    assert is_excluded("Song Name (Live Concert)")
    assert is_excluded("歌曲 翻唱")
    assert not is_excluded("Song Name (Official Audio)")


def test_topic_channel_has_higher_official_signal() -> None:
    signal, priority = official_signal("Song", "Artist - Topic", "Artist")

    assert signal == "ARTIST_TOPIC"
    assert priority > official_signal("Song (Official Audio)", "Label", "Artist")[1]


def test_artist_named_channel_has_top_priority() -> None:
    signal, priority = official_signal("Song", "Artist Official", "Artist")

    assert signal == "ARTIST_NAMED_CHANNEL"
    assert priority > official_signal("Song", "Artist - Topic", "Artist")[1]


def test_candidate_captures_required_metadata_without_download() -> None:
    candidate = candidate_from_entry(
        "Artist",
        "Song",
        {
            "id": "abc123",
            "title": "Song (Official Audio)",
            "channel": "Artist - Topic",
            "duration": 210,
            "upload_date": "20240101",
        },
    )

    assert candidate is not None
    assert candidate.url == "https://www.youtube.com/watch?v=abc123"
    assert candidate.duration == 210
    assert candidate.upload_date == "20240101"
    assert candidate.title_match == "EXACT_TITLE"


def test_candidate_rejects_unrelated_title_even_from_ranked_channel() -> None:
    candidate = candidate_from_entry(
        "Artist",
        "Requested Song",
        {"id": "abc123", "title": "Different Song", "channel": "Artist Official"},
    )

    assert candidate is None


def test_search_report_marks_all_candidates_as_needing_legal_source(tmp_path: Path, monkeypatch) -> None:
    scripts = Path(__file__).parents[1] / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        import search_youtube_candidates

        candidate = YoutubeCandidate(
            artist="Artist",
            title="Song",
            video_title="Song (Official Audio)",
            channel="Artist - Topic",
            url="https://www.youtube.com/watch?v=abc",
            duration=200,
            upload_date="20240101",
            official_signal="ARTIST_TOPIC",
            title_match="EXACT_TITLE",
            priority=40,
        )
        monkeypatch.setattr(search_youtube_candidates, "search_youtube", lambda *_: [candidate])
        selection = Path(__file__).parents[1] / "data" / "selection.csv"

        review = search_youtube_candidates.search(selection, tmp_path, max_candidates=5)

        assert len(review) == 50
        assert {row["authorization_status"] for row in review} == {"NEEDS_LEGAL_SOURCE"}
        assert (tmp_path / "youtube-candidates.csv").exists()
        assert (tmp_path / "youtube-review.csv").exists()
    finally:
        sys.path.remove(str(scripts))
