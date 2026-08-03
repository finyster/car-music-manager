from pathlib import Path

from car_music_manager.cli import main


def test_cli_scan_writes_json_report(tmp_path: Path, capsys) -> None:
    (tmp_path / "song.ogg").touch()
    report = tmp_path / "report.json"
    assert main(["scan", str(tmp_path), "--report", str(report)]) == 0
    assert "song.ogg" in capsys.readouterr().out
    assert report.exists()
