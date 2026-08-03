# car-music-manager

Windows-first CLI for safely preparing music for a car stereo or USB drive. It scans local files, normalizes loudness with FFmpeg's two-pass `loudnorm`, creates compatible MP3 files, preserves useful metadata as ID3v2.3 (including Chinese text), and verifies every published output by fully decoding it.

The original files are read-only inputs: this tool never renames, tags, moves, overwrites, or deletes them.

## Requirements

- Windows and Python 3.13 (Python 3.11+ is supported by the package)
- FFmpeg and ffprobe available on `PATH`, with `libmp3lame`
- Permission to download every remote source selected through yt-dlp

Install FFmpeg on Windows, then open a new terminal so its PATH update is visible:

```powershell
winget install --id Gyan.FFmpeg --exact
```

Set up the project:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

If PowerShell is configured to block activation, invoke `.venv\Scripts\python.exe` directly instead. `psutil`, `mutagen`, and `yt-dlp` are installed with the application; `pytest` and `ruff` are in the `dev` extra.

## Commands

All path arguments accept Windows paths with spaces and Chinese characters.

```powershell
# Discover MP3, M4A, AAC, FLAC, WAV, and OGG files recursively.
car-music scan "D:\Music Library" --report reports\scan.json

# Read format, duration, bitrate, sample rate, channels and codec with ffprobe.
car-music analyze "D:\Music Library\歌曲.flac"

# Encode a file or folder. Nothing in the source is modified.
car-music process "D:\Music Library" "E:\Car Music" --report reports\process.csv

# Preview without encoding.
car-music process "D:\Music Library" "E:\Car Music" --dry-run

# Decode-test a source or completed output folder.
car-music verify "E:\Car Music"

# Export a selectable CSV for a video, playlist, or channel. Mark selected rows yes/X.
car-music list "https://www.youtube.com/playlist?list=..." reports\selection.csv

# Process selected local paths or remote sources from the CSV.
car-music batch reports\selection.csv "E:\Car Music" --report reports\batch.json
```

`process` and `batch` accept these control flags:

- `--dry-run` plans outputs without creating audio files.
- `--overwrite` replaces an output with the same sanitized base name.
- `--fail-fast` stops after the first failed item; by default errors are logged and processing continues.
- `--report report.json` or `--report report.csv` writes machine-readable outcomes.

Without `--overwrite`, existing target names are skipped during a resumed local batch. Newly created collisions are assigned names such as `Song (2).mp3`; Windows-reserved names and illegal characters are sanitized.

## Output profile and safety

Defaults are 256 kbps CBR MP3, 44.1 kHz stereo, -16 LUFS integrated loudness, and -1.5 dBTP. The process is:

1. Probe source data with `ffprobe`.
2. Run FFmpeg loudness analysis (`loudnorm` JSON measurement).
3. Encode using the measured second-pass filter into a per-item temporary directory.
4. Write Unicode ID3v2.3 metadata with Mutagen.
5. Fully decode-test the temporary MP3 with FFmpeg.
6. Move it to the requested output directory only after validation succeeds.

Before a batch starts, the target volume is checked with `psutil`. Estimated CBR output space is based on media duration and target bitrate. USB output is just any writable directory or drive letter, for example `E:\Car Music`.

## Optional configuration

Copy `config.example.toml` to `config.local.toml`, adjust it, then pass `--config config.local.toml`. Local configuration is intentionally ignored by Git; do not commit absolute paths, cookies, credentials, or API keys.

```powershell
car-music --config config.local.toml process input output
```

## 50-song catalog template

`data/selection.csv` is a 50-song candidate template arranged in the five car-library folders. It intentionally contains no URLs or private paths. Every row starts as `selected=yes` and `NEEDS_LEGAL_SOURCE`.

After filling a row with a local purchased download/CD-rip path or an explicitly authorized URL, and setting `rights_confirmed=yes`, build the catalog with:

```powershell
python scripts\build_catalog.py
```

The script copies rather than changes local originals, checks duplicate hashes plus artist/title/duration, creates `library/originals` and categorized `library/car-ready`, and writes the requested reports under `reports`. It never downloads ordinary commercial YouTube videos: only `source_type=authorized_url` plus an explicit rights confirmation permits yt-dlp.

## Local inbox import

Place only audio you are allowed to use in `library/inbox` (the whole `library` tree is Git-ignored). Then run:

```powershell
python scripts\import_inbox.py --dry-run
python scripts\import_inbox.py
```

The importer reads Mutagen tags first and then common `artist - title` filenames. It normalizes full/half-width text, selected common simplified/traditional characters, track prefixes, punctuation, and suffixes such as `Official Audio` or `官方 MV`. Exact or high-confidence matches are ranked per song as FLAC/WAV, then M4A/AAC by bitrate, then MP3. Ambiguous files are never imported; review `reports/match-review.csv` instead. Each run also writes `inbox-scan.csv`, `matched-files.csv`, and `unmatched-files.csv`.

### External Windows drive

To keep the private music library outside the repository, pass an external root. This creates `inbox`, `originals`, `car-ready`, `reports`, and `temp` beneath that root:

```powershell
python scripts\import_inbox.py --library-root "D:\CarMusic" --dry-run
python scripts\import_inbox.py --library-root "D:\CarMusic"
python scripts\build_catalog.py --library-root "D:\CarMusic"
```

With `--library-root "D:\CarMusic"`, reports are written to `D:\CarMusic\reports`. Inbox sources are read only; originals are copied through `D:\CarMusic\temp` and probe-checked before publishing. Car-ready MP3 files are encoded, tagged, and decode-verified in the same temporary location before they are moved into `car-ready`. Without `--library-root`, the existing repository-relative defaults remain unchanged.

## YouTube / remote sources

`list` uses yt-dlp metadata-only mode and does not download media. `batch` downloads only rows marked `yes`, `x`, `true`, `1`, or `selected`. It is deliberately the user's responsibility to select only sources they have authorization to download. Cookies, account credentials, API keys, and download archives are neither required nor supported as committed project configuration.

To create a review-only candidate report for the catalog without downloading media:

```powershell
python scripts\search_youtube_candidates.py --library-root "D:\CarMusic"
```

The script writes `youtube-candidates.csv` and `youtube-review.csv` below the chosen reports directory, retaining at most five non-excluded candidates per song. A visible `ARTIST_TOPIC`, `OFFICIAL_AUDIO`, or `OFFICIAL_MV` signal is only a ranking hint, never download permission. Every candidate remains `NEEDS_LEGAL_SOURCE` until the user records a separately authorized source in `selection.csv`; then `build_catalog.py` can use the existing authorized-source path.

To make the existing candidates easy to inspect without re-searching or downloading anything:

```powershell
python scripts\generate_youtube_manual_review.py --library-root "D:\CarMusic"
```

The command first verifies the locked `selection.csv` SHA-256, then writes clickable `youtube-manual-review.html` and `approved-links.csv` to `D:\CarMusic\reports`. The CSV approval column is intentionally blank; a user must explicitly fill it after checking the link, version, and legal source permission.

After explicitly confirming download rights for every current recommended link, use the existing safe build path without changing `selection.csv`:

```powershell
python scripts\import_approved_links.py --library-root "D:\CarMusic" --confirm-authorized
```

The command creates only a temporary authorization manifest under `D:\CarMusic\temp`; each downloaded source is preserved in `originals` and only published to `car-ready` after the established normalization and decode verification.

## Development

```powershell
python -m pytest -q
ruff check .
```

The test suite includes mocked unit tests plus an FFmpeg integration test that generates a one-second sine wave, runs the real normalization path, and verifies the resulting MP3. The integration test is skipped only when FFmpeg/ffprobe are unavailable.

## Current limitations

- Artwork, genre taxonomy, and advanced playlist ordering are intentionally out of scope so that they cannot block the core conversion path.
- Loudness is validated by FFmpeg processing and decodability; no separate post-encode LUFS measurement is currently reported.
- Resuming is based on already-existing sanitized output names. For audit-grade identity tracking across duplicate titles, retain the generated JSON/CSV report with the input batch.
