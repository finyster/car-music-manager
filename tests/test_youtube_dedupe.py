from car_music_manager.dedupe import canonical_source_key
from car_music_manager.youtube import _entry_source


def test_flat_youtube_video_id_becomes_watch_url() -> None:
    source = _entry_source({"id": "abc123", "url": "abc123"})

    assert source == "https://www.youtube.com/watch?v=abc123"
    assert canonical_source_key(source) == "youtube:video:abc123"


def test_webpage_url_is_preferred_for_youtube_entry() -> None:
    source = _entry_source(
        {
            "id": "abc123",
            "url": "abc123",
            "webpage_url": "https://music.youtube.com/watch?v=abc123&si=tracking",
        }
    )

    assert canonical_source_key(source) == "youtube:video:abc123"
