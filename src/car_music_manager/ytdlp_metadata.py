"""Shared yt-dlp extraction and download authentication fallback."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .errors import CarMusicError

_ANSI_ESCAPE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")


class MetadataAuthenticationError(CarMusicError):
    """Authentication cannot proceed; alternate URL forms will not fix it."""


def clean_error_text(value: object) -> str:
    """Remove terminal formatting before displaying an extractor error in Qt."""
    return _ANSI_ESCAPE.sub("", str(value)).strip()


def _needs_authentication(message: str) -> bool:
    folded = message.casefold()
    return any(
        marker in folded
        for marker in (
            "sign in to confirm",
            "login required",
            "authentication required",
            "use --cookies-from-browser or --cookies",
        )
    )


class _YtdlpLogger:
    """Retain errors suppressed by ignoreerrors, without writing credential logs."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def debug(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        self.messages.append(clean_error_text(message))

    def error(self, message: str) -> None:
        self.messages.append(clean_error_text(message))


def _cookie_options() -> dict[str, Any]:
    browser = os.environ.get("CAR_MUSIC_YTDLP_BROWSER", "").strip().casefold()
    cookie_file = os.environ.get("CAR_MUSIC_YTDLP_COOKIE_FILE", "").strip()
    if browser and cookie_file:
        raise MetadataAuthenticationError(
            "請只設定 CAR_MUSIC_YTDLP_BROWSER 或 CAR_MUSIC_YTDLP_COOKIE_FILE 其中一項。"
        )
    if cookie_file:
        path = Path(cookie_file).expanduser()
        if not path.is_absolute() or not path.is_file():
            raise MetadataAuthenticationError(
                "CAR_MUSIC_YTDLP_COOKIE_FILE 必須指向存在的 Netscape cookies.txt 絕對路徑；"
                "建議存放在專案外。"
            )
        return {"cookiefile": str(path)}
    if browser:
        if browser not in {"chrome", "firefox"}:
            raise MetadataAuthenticationError(
                "CAR_MUSIC_YTDLP_BROWSER 目前支援 chrome 或 firefox。"
            )
        profile = os.environ.get("CAR_MUSIC_YTDLP_PROFILE", "").strip() or None
        return {"cookiesfrombrowser": (browser, profile, None, None)}
    raise MetadataAuthenticationError(
        "YouTube 要求登入／bot 驗證，匿名讀取失敗。請設定 CAR_MUSIC_YTDLP_BROWSER "
        "為 firefox 或 chrome，或設定 CAR_MUSIC_YTDLP_COOKIE_FILE 為專案外的 "
        "Netscape cookies.txt 絕對路徑，再重新啟動 GUI。"
    )


def _failure_text(error: Exception, logger: _YtdlpLogger) -> str:
    # CookieLoadError wraps the useful Windows error in __context__.
    messages = list(logger.messages)
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        messages.append(clean_error_text(current))
        current = current.__cause__ or current.__context__
    return "\n".join(messages)


def _authentication_failure(message: str) -> MetadataAuthenticationError:
    folded = message.casefold()
    if "could not copy chrome cookie database" in folded:
        return MetadataAuthenticationError(
            "無法讀取 Chrome cookie 資料庫：Windows 下常因 Chrome 或背景程序鎖定檔案，"
            "也可能是存取權限問題。請儲存工作後完整退出 Chrome，確認背景程序已結束再試；"
            "若仍失敗，改用已登入 YouTube 的 Firefox 或專案外的 Netscape cookies.txt。"
            "關閉 Chrome 仍不保證 cookie 可以解密。"
        )
    if any(marker in folded for marker in ("dpapi", "decrypt", "unknown cookie version")):
        return MetadataAuthenticationError(
            "瀏覽器 cookie 無法解密，可能涉及 Windows DPAPI 或 Chrome App-Bound 加密。"
            "請改用已登入 YouTube 的 Firefox，或專案外的 Netscape cookies.txt。"
        )
    if _needs_authentication(message):
        return MetadataAuthenticationError(
            "已嘗試設定的 cookie 來源，但 YouTube 仍要求登入／bot 驗證。"
            "請確認選用的瀏覽器 profile 已登入且可播放同一網址；"
            "cookies.txt 也可能已過期。Cookie 不保證能解除 YouTube 的驗證。"
        )
    return MetadataAuthenticationError(
        "無法載入設定的 cookie 來源。請確認瀏覽器／profile 存在、檔案可讀，"
        "或 cookies.txt 是有效的 Netscape 格式。"
    )


def extract_with_authentication(
    url: str, options: dict[str, Any], *, download: bool = False
) -> tuple[dict[str, Any], str | None]:
    """Try anonymous extraction, then retry once on an authentication failure.

    Browser cookies are accessed only when explicitly selected through the
    environment. Successful partial playlists retain existing ignoreerrors
    behavior. No cookie sources are combined or automatically exported.
    """
    try:
        import yt_dlp
        from yt_dlp.cookies import CookieLoadError
    except ImportError as error:  # pragma: no cover - declared dependency
        raise CarMusicError("yt-dlp is not installed") from error

    cookie_options: dict[str, Any] = {}
    for authenticated in (False, True):
        logger = _YtdlpLogger()
        attempt_options = {
            **options,
            "no_color": True,
            "logger": logger,
            **cookie_options,
        }
        try:
            with yt_dlp.YoutubeDL(attempt_options) as downloader:
                metadata = downloader.extract_info(url, download=download)
                if not isinstance(metadata, dict):
                    raise CarMusicError("未取得 metadata。")
                filename = downloader.prepare_filename(metadata) if download else None
            entries = metadata.get("entries")
            if (
                isinstance(entries, list)
                and not any(entries)
                and any(_needs_authentication(message) for message in logger.messages)
            ):
                raise CarMusicError("播放清單項目需要登入／bot 驗證。")
            return metadata, filename
        except (yt_dlp.utils.DownloadError, CookieLoadError, CarMusicError) as error:
            message = _failure_text(error, logger)
            if authenticated:
                if (
                    isinstance(error, CookieLoadError)
                    or any(
                        marker in message.casefold()
                        for marker in (
                            "could not copy chrome cookie database",
                            "dpapi",
                            "decrypt",
                            "unknown cookie version",
                        )
                    )
                    or _needs_authentication(message)
                ):
                    raise _authentication_failure(message) from error
                raise CarMusicError(clean_error_text(error)) from error
            if not _needs_authentication(message):
                raise CarMusicError(clean_error_text(error)) from error
            cookie_options = _cookie_options()
    raise AssertionError("yt-dlp attempts exhausted")  # pragma: no cover


def extract_metadata(url: str, options: dict[str, Any]) -> dict[str, Any]:
    """Read metadata using the shared fallback without downloading media."""
    metadata, _ = extract_with_authentication(url, options)
    return metadata
