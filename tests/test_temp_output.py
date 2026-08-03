from pathlib import Path

from car_music_manager.models import TagData
from car_music_manager.process import process_one


def test_process_uses_configured_temp_directory(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"source")
    output = tmp_path / "car-ready"
    temp = tmp_path / "temporary staging"

    monkeypatch.setattr(
        "car_music_manager.process._analysis_pass",
        lambda *_: {
            "input_i": "-20",
            "input_tp": "-3",
            "input_lra": "5",
            "input_thresh": "-30",
            "target_offset": "1",
        },
    )

    def encode(_source: Path, destination: Path, *_args: object) -> None:
        assert destination.parent.parent == temp
        destination.write_bytes(b"encoded")

    monkeypatch.setattr("car_music_manager.process._encode_pass", encode)
    monkeypatch.setattr("car_music_manager.process.write_id3v23", lambda *_: None)
    monkeypatch.setattr("car_music_manager.process.verify_decodable", lambda *_: None)

    result = process_one(source, output, tags=TagData(title="x"), temp_dir=temp)

    assert result.exists()
    assert source.read_bytes() == b"source"
