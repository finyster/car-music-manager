from pathlib import Path

from car_music_manager.dedupe import (
    DedupeIndex,
    canonical_source_key,
    durations_match,
    sha256_file,
    track_key,
)


def test_canonical_source_key_matches_youtube_music_and_youtube() -> None:
    music = "https://music.youtube.com/watch?v=abc123&si=tracking"
    regular = "https://www.youtube.com/watch?v=abc123&feature=share"
    short = "https://youtu.be/abc123?si=tracking"

    assert canonical_source_key(music) == "youtube:video:abc123"
    assert canonical_source_key(regular) == canonical_source_key(music)
    assert canonical_source_key(short) == canonical_source_key(music)


def test_canonical_source_key_matches_artist_hosts_and_tabs() -> None:
    music = "https://music.youtube.com/@ExampleArtist?si=tracking"
    regular = "https://www.youtube.com/@ExampleArtist/videos"

    assert canonical_source_key(music) == "youtube:page:/@exampleartist"
    assert canonical_source_key(regular) == canonical_source_key(music)


def test_track_key_normalizes_unicode_spacing_and_punctuation() -> None:
    assert track_key("Joe Hisaishi", "A Town With An Ocean View") == track_key(
        "Ｊｏｅ　Ｈｉｓａｉｓｈｉ",
        "A-Town_With An Ocean View!",
    )


def test_durations_match_uses_conservative_tolerance() -> None:
    assert durations_match(180, 183)
    assert not durations_match(180, 184)
    assert not durations_match(180, None)


def test_sha256_file_detects_identical_content(tmp_path: Path) -> None:
    first = tmp_path / "first.bin"
    second = tmp_path / "second.bin"
    first.write_bytes(b"same audio bytes")
    second.write_bytes(b"same audio bytes")

    assert sha256_file(first) == sha256_file(second)


def test_dedupe_index_round_trip(tmp_path: Path) -> None:
    index = DedupeIndex()
    index.add(
        source_key="youtube:video:abc123",
        content_hash="deadbeef",
        track=track_key("Artist", "Song"),
    )
    path = index.save(tmp_path)

    assert path.name == ".car-music-dedupe.json"
    loaded = DedupeIndex.load(tmp_path)
    assert loaded.source_keys == {"youtube:video:abc123"}
    assert loaded.content_sha256 == {"deadbeef"}
    assert loaded.track_keys == {track_key("Artist", "Song")}


def test_corrupt_dedupe_index_falls_back_to_empty(tmp_path: Path) -> None:
    (tmp_path / ".car-music-dedupe.json").write_text("not json", encoding="utf-8")

    assert DedupeIndex.load(tmp_path) == DedupeIndex()
