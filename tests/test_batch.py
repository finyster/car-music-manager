from pathlib import Path

from car_music_manager.batch import process_paths, selected_csv_sources


def test_selected_csv_sources_only_returns_marked_rows(tmp_path: Path) -> None:
    manifest = tmp_path / "list.csv"
    manifest.write_text(
        "selected,source\nyes,https://example.test/a\n,skip.mp3\nX,keep.mp3\n", encoding="utf-8"
    )
    assert selected_csv_sources(manifest) == ["https://example.test/a", "keep.mp3"]


def test_process_paths_dry_run_skips_encoder(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "a.mp3"
    source.touch()
    output = tmp_path / "usb"
    output.mkdir()
    monkeypatch.setattr(
        "car_music_manager.batch.analyze_audio", lambda *_: type("I", (), {"duration_seconds": 1})()
    )
    monkeypatch.setattr("car_music_manager.batch.estimate_output_bytes", lambda *_: 1)
    monkeypatch.setattr("car_music_manager.batch.check_output_space", lambda *_: (10, True))
    monkeypatch.setattr(
        "car_music_manager.batch.process_one",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()),
    )
    results = process_paths([source], output, dry_run=True)
    assert results[0].status == "planned"


def test_check_output_space_passes_a_string_to_psutil(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Usage:
        free = 100

    def disk_usage(path: str) -> Usage:
        captured["path"] = path
        return Usage()

    monkeypatch.setattr("car_music_manager.reporting.psutil.disk_usage", disk_usage)
    from car_music_manager.reporting import check_output_space

    free, enough = check_output_space(tmp_path, 50)

    assert (free, enough) == (100, True)
    assert captured["path"] == str(tmp_path)
