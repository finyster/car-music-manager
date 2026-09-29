from pathlib import Path

import pytest
import yt_dlp
from yt_dlp.cookies import CookieLoadError
from yt_dlp.utils import DownloadError

from car_music_manager.errors import CarMusicError
from car_music_manager.youtube import download_authorized, list_youtube
from car_music_manager.youtube_candidates import search_youtube
from car_music_manager.ytdlp_metadata import (
    MetadataAuthenticationError,
    clean_error_text,
    extract_metadata,
)
from car_music_manager.ytmusic import list_ytmusic

URL = "https://youtube.com/watch?v=example"
AUTH = "Sign in to confirm you’re not a bot."
TRACK = {"id": "example", "title": "Song", "duration": 200}


@pytest.fixture
def fake_ydl(monkeypatch):
    for name in ("BROWSER", "PROFILE", "COOKIE_FILE"):
        monkeypatch.delenv(f"CAR_MUSIC_YTDLP_{name}", raising=False)
    calls = []
    outcomes = []

    class FakeYoutubeDL:
        requests = []
        create_download = True

        def __init__(self, options):
            self.options = options
            calls.append(options)

        def __enter__(self):
            self.active = True
            return self

        def __exit__(self, *args):
            self.active = False
            return False

        def extract_info(self, url, download):
            self.requests.append((url, download))
            outcome = outcomes.pop(0)
            if callable(outcome):
                outcome = outcome(self.options)
            if isinstance(outcome, Exception):
                raise outcome
            if download and self.create_download and isinstance(outcome, dict):
                Path(self.prepare_filename(outcome)).touch()
            return outcome

        def prepare_filename(self, metadata):
            assert self.active  # Use the same successful downloader inside its context.
            return (
                self.options["outtmpl"]
                .replace("%(title).180B", metadata["title"])
                .replace("%(id)s", metadata["id"])
                .replace("%(ext)s", "webm")
            )

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)
    return calls, outcomes


def test_anonymous_success_does_not_read_cookie_source(fake_ydl, monkeypatch):
    calls, outcomes = fake_ydl
    monkeypatch.setenv("CAR_MUSIC_YTDLP_BROWSER", "chrome")
    outcomes.append(TRACK)
    assert extract_metadata(URL, {}) == TRACK
    assert len(calls) == 1
    assert "cookiesfrombrowser" not in calls[0]
    assert "cookiefile" not in calls[0]
    assert calls[0]["no_color"] is True


@pytest.mark.parametrize("browser", ["chrome", "firefox"])
def test_authentication_retries_once_with_selected_browser(fake_ydl, monkeypatch, browser):
    calls, outcomes = fake_ydl
    monkeypatch.setenv("CAR_MUSIC_YTDLP_BROWSER", browser)
    monkeypatch.setenv("CAR_MUSIC_YTDLP_PROFILE", "Profile 1")
    outcomes.extend([DownloadError(AUTH), TRACK])
    original = {"skip_download": True, "extract_flat": True}
    assert extract_metadata(URL, original) == TRACK
    assert len(calls) == 2
    assert calls[1]["cookiesfrombrowser"] == (browser, "Profile 1", None, None)
    assert original == {"skip_download": True, "extract_flat": True}


def test_auth_without_configuration_has_actionable_message(fake_ydl):
    calls, outcomes = fake_ydl
    outcomes.append(DownloadError(AUTH))
    with pytest.raises(MetadataAuthenticationError, match="CAR_MUSIC_YTDLP_BROWSER"):
        extract_metadata(URL, {})
    assert len(calls) == 1


@pytest.mark.parametrize("message", ["HTTP Error 429", "Video unavailable", "Connection timed out"])
def test_unrelated_failure_does_not_read_browser_cookies(fake_ydl, monkeypatch, message):
    calls, outcomes = fake_ydl
    monkeypatch.setenv("CAR_MUSIC_YTDLP_BROWSER", "chrome")
    outcomes.append(DownloadError(message))
    with pytest.raises(CarMusicError, match=message):
        extract_metadata(URL, {})
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("Could not copy Chrome cookie database.", "背景程序"),
        ("Failed to decrypt with DPAPI", "無法解密"),
        (AUTH, "仍要求登入"),
    ],
)
def test_cookie_retry_failure_is_clear_and_bounded(fake_ydl, monkeypatch, failure, expected):
    calls, outcomes = fake_ydl
    monkeypatch.setenv("CAR_MUSIC_YTDLP_BROWSER", "chrome")
    outcomes.extend([DownloadError(AUTH), DownloadError(failure)])
    with pytest.raises(MetadataAuthenticationError, match=expected):
        extract_metadata(URL, {})
    assert len(calls) == 2


def test_wrapped_cookie_load_error_retains_lock_diagnosis(fake_ydl, monkeypatch):
    _, outcomes = fake_ydl
    monkeypatch.setenv("CAR_MUSIC_YTDLP_BROWSER", "chrome")
    wrapped = CookieLoadError("failed to load cookies")
    wrapped.__context__ = DownloadError("Could not copy Chrome cookie database.")
    outcomes.extend([DownloadError(AUTH), wrapped])
    with pytest.raises(MetadataAuthenticationError, match="鎖定檔案"):
        extract_metadata(URL, {})


def test_suppressed_music_auth_error_can_trigger_fallback(fake_ydl, monkeypatch):
    calls, outcomes = fake_ydl
    monkeypatch.setenv("CAR_MUSIC_YTDLP_BROWSER", "firefox")

    def suppressed(options):
        assert options["ignoreerrors"] is True
        options["logger"].error(AUTH)
        return None

    outcomes.extend([suppressed, TRACK])
    assert list_ytmusic("https://music.youtube.com/watch?v=example")[0].title == "Song"
    assert len(calls) == 2


def test_music_stops_alternate_urls_after_cookie_lock(fake_ydl, monkeypatch):
    calls, outcomes = fake_ydl
    monkeypatch.setenv("CAR_MUSIC_YTDLP_BROWSER", "chrome")
    outcomes.extend([DownloadError(AUTH), DownloadError("Could not copy Chrome cookie database.")])
    with pytest.raises(MetadataAuthenticationError, match="Chrome"):
        list_ytmusic("https://music.youtube.com/watch?v=example")
    assert len(calls) == 2


@pytest.mark.parametrize("entries", [[], [None, None]])
def test_playlist_with_all_auth_failures_retries(fake_ydl, monkeypatch, entries):
    calls, outcomes = fake_ydl
    monkeypatch.setenv("CAR_MUSIC_YTDLP_BROWSER", "firefox")

    def suppressed(options):
        options["logger"].error(AUTH)
        return {"entries": entries}

    outcomes.extend([suppressed, {"entries": [TRACK]}])
    assert list_ytmusic("https://music.youtube.com/playlist?list=PL123")[0].title == "Song"
    assert len(calls) == 2


def test_partial_auth_playlist_keeps_successful_entries_without_retry(fake_ydl, monkeypatch):
    calls, outcomes = fake_ydl
    monkeypatch.setenv("CAR_MUSIC_YTDLP_BROWSER", "firefox")

    def partial(options):
        options["logger"].error(AUTH)
        return {"entries": [None, TRACK]}

    outcomes.append(partial)
    assert list_ytmusic("https://music.youtube.com/playlist?list=PL123")[0].title == "Song"
    assert len(calls) == 1


def test_missing_metadata_without_auth_does_not_retry(fake_ydl, monkeypatch):
    calls, outcomes = fake_ydl
    monkeypatch.setenv("CAR_MUSIC_YTDLP_BROWSER", "firefox")
    outcomes.append(None)
    with pytest.raises(CarMusicError, match="未取得 metadata"):
        extract_metadata(URL, {})
    assert len(calls) == 1


def test_cookie_source_load_failure_is_actionable(fake_ydl, monkeypatch):
    _, outcomes = fake_ydl
    monkeypatch.setenv("CAR_MUSIC_YTDLP_BROWSER", "firefox")
    outcomes.extend([DownloadError(AUTH), CookieLoadError("failed to load cookies")])
    with pytest.raises(MetadataAuthenticationError, match="Netscape"):
        extract_metadata(URL, {})


def test_unsupported_browser_is_reported(fake_ydl, monkeypatch):
    _, outcomes = fake_ydl
    monkeypatch.setenv("CAR_MUSIC_YTDLP_BROWSER", "invalid-browser")
    outcomes.append(DownloadError(AUTH))
    with pytest.raises(MetadataAuthenticationError, match="chrome 或 firefox"):
        extract_metadata(URL, {})


def test_music_preserves_url_fallback_and_partial_playlist(fake_ydl):
    calls, outcomes = fake_ydl
    outcomes.extend([DownloadError("Unsupported URL"), {"entries": [None, TRACK, TRACK]}])
    entries = list_ytmusic("https://music.youtube.com/playlist?list=PL123", max_entries=10)
    assert len(entries) == 1
    assert entries[0].title == "Song"
    assert len(calls) == 2
    assert calls[1]["playlistend"] == 10


def test_youtube_listing_uses_fallback_without_downloading(fake_ydl, monkeypatch):
    calls, outcomes = fake_ydl
    monkeypatch.setenv("CAR_MUSIC_YTDLP_BROWSER", "firefox")
    outcomes.extend([DownloadError(AUTH), TRACK])
    assert list_youtube(URL)[0].title == "Song"
    assert calls[1]["skip_download"] is True


def test_cookie_file_retry_uses_only_existing_selected_file(fake_ydl, monkeypatch, tmp_path):
    calls, outcomes = fake_ydl
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.touch()  # Empty fixture; no real cookies are read or saved.
    monkeypatch.setenv("CAR_MUSIC_YTDLP_COOKIE_FILE", str(cookie_file))
    outcomes.extend([DownloadError(AUTH), TRACK])
    assert extract_metadata(URL, {}) == TRACK
    assert calls[1]["cookiefile"] == str(cookie_file)
    assert "cookiesfrombrowser" not in calls[1]


@pytest.mark.parametrize("path", ["cookies.txt", "C:/nonexistent/car-music-cookies.txt"])
def test_invalid_cookie_path_is_reported(fake_ydl, monkeypatch, path):
    _, outcomes = fake_ydl
    monkeypatch.setenv("CAR_MUSIC_YTDLP_COOKIE_FILE", path)
    outcomes.append(DownloadError(AUTH))
    with pytest.raises(MetadataAuthenticationError, match="絕對路徑"):
        extract_metadata(URL, {})


def test_conflicting_cookie_sources_are_rejected(fake_ydl, monkeypatch):
    _, outcomes = fake_ydl
    monkeypatch.setenv("CAR_MUSIC_YTDLP_BROWSER", "chrome")
    monkeypatch.setenv("CAR_MUSIC_YTDLP_COOKIE_FILE", "cookies.txt")
    outcomes.append(DownloadError(AUTH))
    with pytest.raises(MetadataAuthenticationError, match="其中一項"):
        extract_metadata(URL, {})


def test_ansi_error_is_removed_before_gui_worker_receives_it(fake_ydl):
    from car_music_manager.gui import MetadataLoader

    _, outcomes = fake_ydl
    outcomes.append(DownloadError("\x1b[0;31mERROR:\x1b[0m Video unavailable"))
    result = []
    loader = MetadataLoader([URL])
    loader.loaded.connect(lambda entries, errors: result.append((entries, errors)))
    loader.run()
    assert result[0][0] == []
    assert "\x1b" not in result[0][1][0]
    assert "Video unavailable" in result[0][1][0]
    assert clean_error_text("\x1b[0;31mERROR:\x1b[0m") == "ERROR:"


@pytest.fixture(params=["youtube", "ytmusic", "search", "download"])
def entry_point(request, tmp_path):
    """Exercise public callers, not just the shared helper."""
    name = request.param

    def invoke():
        if name == "youtube":
            return list_youtube(URL)
        if name == "ytmusic":
            return list_ytmusic("https://music.youtube.com/watch?v=example")
        if name == "search":
            return search_youtube("Artist", "Song")
        return download_authorized(URL, tmp_path / "download")

    return name, invoke


def assert_entry_options(name, calls):
    for options in calls:
        assert options["quiet"] is True
        assert options["no_color"] is True
        if name == "download":
            assert options["format"] == "bestaudio/best"
            assert options["outtmpl"].endswith("%(title).180B-%(id)s.%(ext)s")
            assert options["noplaylist"] is True
            assert options["restrictfilenames"] is False
            assert "skip_download" not in options
        else:
            assert options["skip_download"] is True
            if name == "youtube":
                assert options["extract_flat"] is True
                assert options["noplaylist"] is False
            elif name == "ytmusic":
                assert options["extract_flat"] == "in_playlist"
                assert options["ignoreerrors"] is True
                assert options["noplaylist"] is False
                assert options["playlistend"] == 500
            else:
                assert options["extract_flat"] == "in_playlist"
                assert options["noplaylist"] is True
                assert options["socket_timeout"] == 15
    assert all(download == (name == "download") for _, download in yt_dlp.YoutubeDL.requests)
    if name == "search":
        assert all(
            url == "ytsearch10:Artist Song official audio" for url, _ in yt_dlp.YoutubeDL.requests
        )


def test_all_entry_points_anonymous_success_ignores_invalid_config(
    entry_point, fake_ydl, monkeypatch
):
    name, invoke = entry_point
    calls, outcomes = fake_ydl
    monkeypatch.setenv("CAR_MUSIC_YTDLP_BROWSER", "invalid")
    monkeypatch.setenv("CAR_MUSIC_YTDLP_COOKIE_FILE", "nonexistent.txt")
    outcomes.append({"entries": [TRACK]} if name == "search" else TRACK)
    assert invoke()
    assert len(calls) == 1
    assert "cookiefile" not in calls[0]
    assert "cookiesfrombrowser" not in calls[0]
    assert_entry_options(name, calls)


@pytest.mark.parametrize("source", ["chrome", "firefox", "file"])
def test_all_entry_points_share_cookie_fallback(
    entry_point, fake_ydl, monkeypatch, tmp_path, source
):
    name, invoke = entry_point
    calls, outcomes = fake_ydl
    if source == "file":
        cookie_file = tmp_path / "cookies-test.txt"
        cookie_file.touch()
        monkeypatch.setenv("CAR_MUSIC_YTDLP_COOKIE_FILE", str(cookie_file))
        expected = {"cookiefile": str(cookie_file)}
    else:
        monkeypatch.setenv("CAR_MUSIC_YTDLP_BROWSER", source)
        monkeypatch.setenv("CAR_MUSIC_YTDLP_PROFILE", "Profile 1")
        expected = {"cookiesfrombrowser": (source, "Profile 1", None, None)}
    outcomes.extend([DownloadError(AUTH), {"entries": [TRACK]} if name == "search" else TRACK])
    result = invoke()
    assert result
    if name == "download":
        assert result.name == "Song-example.webm"
        assert result.exists()
    assert len(calls) == 2
    assert "cookiefile" not in calls[0]
    assert "cookiesfrombrowser" not in calls[0]
    assert {key: calls[1][key] for key in expected} == expected
    assert_entry_options(name, calls)


def test_all_entry_points_missing_auth_configuration(entry_point, fake_ydl):
    _, invoke = entry_point
    calls, outcomes = fake_ydl
    outcomes.append(DownloadError(AUTH))
    with pytest.raises(MetadataAuthenticationError, match="CAR_MUSIC_YTDLP_BROWSER"):
        invoke()
    assert len(calls) == 1


def test_all_entry_points_cookie_failure_is_bounded(entry_point, fake_ydl, monkeypatch):
    _, invoke = entry_point
    calls, outcomes = fake_ydl
    monkeypatch.setenv("CAR_MUSIC_YTDLP_BROWSER", "chrome")
    outcomes.extend([DownloadError(AUTH), CookieLoadError("failed to load cookies")])
    with pytest.raises(MetadataAuthenticationError, match="Netscape"):
        invoke()
    assert len(calls) == 2


def test_all_entry_points_clean_errors_without_auth_retry(entry_point, fake_ydl, monkeypatch):
    name, invoke = entry_point
    calls, outcomes = fake_ydl
    monkeypatch.setenv("CAR_MUSIC_YTDLP_BROWSER", "chrome")
    failure = DownloadError("\x1b[31mVideo unavailable\x1b[0m")
    outcomes.extend([failure] * (2 if name == "ytmusic" else 1))
    with pytest.raises(CarMusicError, match="Video unavailable") as caught:
        invoke()
    assert "\x1b" not in str(caught.value)
    # Music retains its ordinary alternate-URL behavior.
    assert len(calls) == (2 if name == "ytmusic" else 1)
    assert all("cookiesfrombrowser" not in options for options in calls)


def test_pipeline_metadata_success_then_download_auth_fallback(fake_ydl, monkeypatch, tmp_path):
    calls, outcomes = fake_ydl
    monkeypatch.setenv("CAR_MUSIC_YTDLP_BROWSER", "firefox")
    outcomes.extend([TRACK, DownloadError(AUTH), TRACK])
    assert list_youtube(URL)[0].title == "Song"
    assert download_authorized(URL, tmp_path).exists()
    assert len(calls) == 3
    assert "cookiesfrombrowser" not in calls[0]
    assert "cookiesfrombrowser" not in calls[1]
    assert calls[2]["cookiesfrombrowser"] == ("firefox", None, None, None)
    assert yt_dlp.YoutubeDL.requests == [(URL, False), (URL, True), (URL, True)]


@pytest.mark.parametrize("worker_name", ["ProcessingWorker", "ArtworkProcessingWorker"])
def test_download_failure_is_clean_in_gui_processing_signal(fake_ydl, tmp_path, worker_name):
    from car_music_manager.gui import ProcessingWorker
    from car_music_manager.gui_ytmusic import ArtworkProcessingWorker

    _, outcomes = fake_ydl
    outcomes.append(DownloadError("\x1b[31mVideo unavailable\x1b[0m"))
    job = {
        "row": 0,
        "title": "Song",
        "artist": "Artist",
        "source_type": "YouTube",
        "source": URL,
        "rights_confirmed": True,
    }
    if worker_name == "ProcessingWorker":
        worker = ProcessingWorker([job], tmp_path, None)
    else:
        worker = ArtworkProcessingWorker([job], tmp_path, None, dedupe_enabled=False)
    received = []
    worker.row_finished.connect(lambda *args: received.append(args))
    worker.run()
    assert len(received) == 1
    assert "Video unavailable" in received[0][2]
    assert "\x1b" not in received[0][2]


def test_all_entry_points_do_not_retry_again_when_cookies_rejected(
    entry_point, fake_ydl, monkeypatch
):
    _, invoke = entry_point
    calls, outcomes = fake_ydl
    monkeypatch.setenv("CAR_MUSIC_YTDLP_BROWSER", "firefox")
    outcomes.extend([DownloadError(AUTH), DownloadError(AUTH)])
    with pytest.raises(MetadataAuthenticationError):
        invoke()
    assert len(calls) == 2


@pytest.mark.parametrize("alternate_extension", [True, False])
def test_download_retains_filename_fallback_and_missing_file_error(
    fake_ydl, tmp_path, alternate_extension
):
    _, outcomes = fake_ydl
    yt_dlp.YoutubeDL.create_download = False
    outcomes.append(TRACK)
    if alternate_extension:
        actual = tmp_path / "Song-example.m4a"
        actual.touch()
        assert download_authorized(URL, tmp_path) == actual
    else:
        with pytest.raises(CarMusicError, match="did not create the expected audio file"):
            download_authorized(URL, tmp_path)
