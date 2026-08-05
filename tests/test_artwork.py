from io import BytesIO
from pathlib import Path

import pytest
from mutagen.id3 import ID3
from PIL import Image

from car_music_manager.artwork import prepare_artwork_jpeg, validate_artwork_url
from car_music_manager.errors import ValidationError
from car_music_manager.tags import embed_artwork_jpeg


def _png_bytes(size: tuple[int, int] = (1200, 800)) -> bytes:
    buffer = BytesIO()
    Image.new("RGBA", size, (10, 120, 220, 180)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_prepare_artwork_jpeg_creates_square_car_cover() -> None:
    output = prepare_artwork_jpeg(_png_bytes(), max_size=500)

    assert output.startswith(b"\xff\xd8")
    with Image.open(BytesIO(output)) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"
        assert image.size == (500, 500)


def test_prepare_artwork_jpeg_rejects_empty_response() -> None:
    with pytest.raises(ValidationError, match="empty"):
        prepare_artwork_jpeg(b"")


def test_validate_artwork_url_accepts_only_http_urls() -> None:
    assert validate_artwork_url("https://i.ytimg.com/vi/example/maxresdefault.jpg") == (
        "https://i.ytimg.com/vi/example/maxresdefault.jpg"
    )
    with pytest.raises(ValidationError):
        validate_artwork_url("file:///C:/cover.jpg")


def test_embed_artwork_jpeg_adds_front_cover(tmp_path: Path) -> None:
    mp3_path = tmp_path / "song.mp3"
    ID3().save(mp3_path, v2_version=3)
    jpeg_data = prepare_artwork_jpeg(_png_bytes((640, 640)), max_size=500)

    embed_artwork_jpeg(mp3_path, jpeg_data)

    frames = ID3(mp3_path).getall("APIC")
    assert len(frames) == 1
    assert frames[0].type == 3
    assert frames[0].mime == "image/jpeg"
    assert frames[0].data == jpeg_data
