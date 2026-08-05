"""Safe retrieval and normalization of remote album artwork."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from PIL import Image, ImageOps

from .errors import ValidationError

_MAX_DOWNLOAD_BYTES = 12 * 1024 * 1024
_USER_AGENT = "car-music-manager/0.4 (+desktop artwork fetcher)"


def validate_artwork_url(value: str) -> str:
    """Validate and return an HTTP(S) artwork URL."""
    url = value.strip()
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValidationError("Artwork URL must be a valid HTTP or HTTPS URL")
    return url


def prepare_artwork_jpeg(
    data: bytes,
    *,
    max_size: int = 500,
    quality: int = 88,
) -> bytes:
    """Convert image bytes to a square, car-friendly JPEG without cropping."""
    if not data:
        raise ValidationError("Artwork response was empty")
    if max_size < 1:
        raise ValueError("max_size must be positive")
    if not 1 <= quality <= 95:
        raise ValueError("quality must be between 1 and 95")

    try:
        with Image.open(BytesIO(data)) as source:
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGB")
    except Exception as error:
        raise ValidationError(f"Artwork is not a supported image: {error}") from error

    image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (max_size, max_size), (0, 0, 0))
    left = (max_size - image.width) // 2
    top = (max_size - image.height) // 2
    canvas.paste(image, (left, top))

    buffer = BytesIO()
    canvas.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=False)
    return buffer.getvalue()


def download_artwork(
    url: str,
    destination: Path,
    *,
    max_size: int = 500,
    max_download_bytes: int = _MAX_DOWNLOAD_BYTES,
    timeout: float = 20.0,
) -> Path:
    """Download one public artwork image and atomically publish a normalized JPEG."""
    validated_url = validate_artwork_url(url)
    if max_download_bytes < 1:
        raise ValueError("max_download_bytes must be positive")

    request = Request(validated_url, headers={"User-Agent": _USER_AGENT})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL is validated above
        content_type = str(response.headers.get("Content-Type", "")).casefold()
        if content_type and not content_type.startswith("image/"):
            raise ValidationError(f"Artwork URL returned non-image content: {content_type}")
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > max_download_bytes:
            raise ValidationError("Artwork image is larger than the configured download limit")

        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_download_bytes:
                raise ValidationError("Artwork image exceeded the configured download limit")
            chunks.append(chunk)

    jpeg_data = prepare_artwork_jpeg(b"".join(chunks), max_size=max_size)
    destination = destination.with_suffix(".jpg")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        temporary.write_bytes(jpeg_data)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination
