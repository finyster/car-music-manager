import pytest

from car_music_manager.errors import ValidationError
from car_music_manager.ytmusic import (
    classify_ytmusic_url,
    is_ytmusic_url,
    normalize_ytmusic_url,
    ytmusic_candidate_urls,
    ytmusic_entry_from_info,
)


def test_detects_and_normalizes_ytmusic_tracking_url() -> None:
    source = "https://music.youtube.com/watch?v=abc123&si=tracking&list=PL123"
    assert is_ytmusic_url(source)
    assert normalize_ytmusic_url(source) == (
        "https://music.youtube.com/watch?v=abc123&list=PL123"
    )
    assert classify_ytmusic_url(source) == "track"


def test_classifies_album_playlist() -> None:
    source = "https://music.youtube.com/playlist?list=OLAK5uy_example"
    assert classify_ytmusic_url(source) == "album"


def test_artist_candidates_prefer_regular_youtube_videos_tab() -> None:
    source = "https://music.youtube.com/@cateen_hayatosumino?si=tracking"
    assert ytmusic_candidate_urls(source) == [
        "https://www.youtube.com/@cateen_hayatosumino/videos",
        "https://www.youtube.com/@cateen_hayatosumino",
        "https://music.youtube.com/@cateen_hayatosumino",
    ]


def test_rejects_non_ytmusic_url() -> None:
    with pytest.raises(ValidationError):
        normalize_ytmusic_url("https://www.youtube.com/watch?v=abc123")


def test_entry_prefers_music_metadata_fields() -> None:
    entry = ytmusic_entry_from_info(
        {
            "id": "video123",
            "title": "Video title",
            "track": "Song title",
            "artist": "Artist name",
            "album": "Album name",
            "duration": 245.8,
            "channel": "Artist Topic",
            "thumbnails": [{"url": "small"}, {"url": "large"}],
        }
    )
    assert entry.source == "https://music.youtube.com/watch?v=video123"
    assert entry.title == "Song title"
    assert entry.artist == "Artist name"
    assert entry.album == "Album name"
    assert entry.duration_seconds == 245
    assert entry.uploader == "Artist Topic"
    assert entry.thumbnail_url == "large"
