from pathlib import Path

from car_music_manager.inbox import InboxMetadata, match_metadata, metadata_from_path, quality_key
from car_music_manager.models import TagData


def _selection() -> list[dict[str, str]]:
    return [
        {"id": "01", "artist": "鄧麗君", "title": "月亮代表我的心"},
        {"id": "31", "artist": "周杰倫", "title": "晴天"},
    ]


def test_chinese_simplified_filename_metadata_matches_exactly() -> None:
    metadata = InboxMetadata(Path("01 - 邓丽君 - 月亮代表我的心 Official Audio.flac"), "邓丽君", "月亮代表我的心 Official Audio", "", None)

    decision = match_metadata(metadata, _selection())

    assert decision.catalog_id == "01"
    assert decision.status == "MATCHED_EXACT"


def test_missing_tags_falls_back_to_chinese_filename(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "31 - 周杰伦 - 晴天 官方 MV.mp3"
    path.touch()
    monkeypatch.setattr("car_music_manager.inbox.read_tags", lambda _: TagData())
    monkeypatch.setattr("car_music_manager.inbox.analyze_audio", lambda _: type("Info", (), {"bitrate_bps": 320000})())

    metadata = metadata_from_path(path)
    decision = match_metadata(metadata, _selection())

    assert metadata.artist == "周杰伦"
    assert metadata.title == "晴天"
    assert decision.catalog_id == "31"
    assert decision.status == "MATCHED_EXACT"


def test_lossless_sources_outrank_higher_bitrate_mp3() -> None:
    flac = InboxMetadata(Path("song.flac"), "鄧麗君", "月亮代表我的心", "", 900000)
    mp3 = InboxMetadata(Path("song.mp3"), "鄧麗君", "月亮代表我的心", "", 320000)

    assert quality_key(flac) > quality_key(mp3)


def test_partial_title_is_sent_to_review_instead_of_forced_match() -> None:
    metadata = InboxMetadata(Path("unknown.mp3"), "", "月亮代表", "", None)

    decision = match_metadata(metadata, _selection())

    assert decision.catalog_id == "01"
    assert decision.status == "REVIEW"
