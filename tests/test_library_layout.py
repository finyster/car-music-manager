import hashlib
import sys
from pathlib import Path

from car_music_manager.library_layout import LibraryLayout


def test_layout_accepts_windows_drive_root() -> None:
    layout = LibraryLayout.from_root(Path(r"D:\CarMusic"))

    assert layout.inbox == Path(r"D:\CarMusic\inbox")
    assert layout.originals == Path(r"D:\CarMusic\originals")
    assert layout.car_ready == Path(r"D:\CarMusic\car-ready")
    assert layout.reports == Path(r"D:\CarMusic\reports")
    assert layout.temp == Path(r"D:\CarMusic\temp")


def test_layout_creates_chinese_space_paths(tmp_path: Path) -> None:
    layout = LibraryLayout.from_root(tmp_path / "外接 音樂庫 中文").ensure()

    assert all(
        path.is_dir()
        for path in (layout.inbox, layout.originals, layout.car_ready, layout.reports, layout.temp)
    )


def test_dry_run_keeps_inbox_source_and_publishes_no_audio(tmp_path: Path) -> None:
    scripts = Path(__file__).parents[1] / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        from import_inbox import run

        layout = LibraryLayout.from_root(tmp_path / "D CarMusic 中文 空白").ensure()
        source = layout.inbox / "未知 歌曲.mp3"
        source.write_bytes(b"not real audio")
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        selection = Path(__file__).parents[1] / "data" / "selection.csv"

        assert run(layout.inbox, selection, layout.root, layout.reports, dry_run=True, temp=layout.temp) == 0

        assert hashlib.sha256(source.read_bytes()).hexdigest() == before
        assert not list(layout.originals.glob("*"))
        assert not list(layout.car_ready.rglob("*.mp3"))
    finally:
        sys.path.remove(str(scripts))
