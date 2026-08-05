from pathlib import Path

from mutagen.id3 import ID3
from PIL import Image

from car_music_manager.gui import output_stem, parse_batch_urls, split_artist_title
from car_music_manager.tags import embed_artwork


def test_parse_batch_urls_preserves_order_and_removes_duplicates() -> None:
    assert parse_batch_urls("\nhttps://a\n# note\nhttps://b\nhttps://a\n") == [
        "https://a",
        "https://b",
    ]


def test_split_artist_title_supports_chinese_separator() -> None:
    assert split_artist_title("鄧麗君－月亮代表我的心") == ("鄧麗君", "月亮代表我的心")


def test_split_artist_title_falls_back_to_uploader() -> None:
    assert split_artist_title("月亮代表我的心", "鄧麗君 Official") == (
        "鄧麗君 Official",
        "月亮代表我的心",
    )


def test_output_stem_is_windows_safe() -> None:
    assert output_stem(3, "歌手:名字", "歌/名") == "03 - 歌手_名字 - 歌_名"


def test_embed_artwork_creates_jpeg_apic(tmp_path: Path) -> None:
    mp3_path = tmp_path / "song.mp3"
    ID3().save(mp3_path, v2_version=3)
    artwork_path = tmp_path / "cover.png"
    Image.new("RGBA", (1200, 800), (255, 0, 0, 128)).save(artwork_path)

    embed_artwork(mp3_path, artwork_path, max_size=500)

    tags = ID3(mp3_path)
    frames = tags.getall("APIC")
    assert len(frames) == 1
    assert frames[0].mime == "image/jpeg"
    assert frames[0].data.startswith(b"\xff\xd8")
