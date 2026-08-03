from pathlib import Path

from car_music_manager.models import ProcessingOptions, TagData
from car_music_manager.process import _loudnorm_filter, _measurement_from_stderr, process_one


def test_loudnorm_second_pass_includes_all_measurements() -> None:
    values = {
        "input_i": "-20",
        "input_tp": "-3",
        "input_lra": "5",
        "input_thresh": "-30",
        "target_offset": "1",
    }
    filter_text = _loudnorm_filter(ProcessingOptions(), values)
    assert "measured_I=-20" in filter_text
    assert "linear=true" in filter_text


def test_measurement_parser_uses_last_json_block() -> None:
    stderr = 'noise\n{ "input_i" : "-20", "input_tp" : "-3", "input_lra" : "5", "input_thresh" : "-30", "target_offset" : "1" }'
    assert _measurement_from_stderr(stderr)["target_offset"] == "1"


def test_process_publishes_only_after_validation(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "原始檔.wav"
    source.write_bytes(b"source")
    output = tmp_path / "output"
    order: list[str] = []

    monkeypatch.setattr(
        "car_music_manager.process._analysis_pass",
        lambda *args: {
            "input_i": "-20",
            "input_tp": "-3",
            "input_lra": "5",
            "input_thresh": "-30",
            "target_offset": "1",
        },
    )

    def encode(_source, destination, *_args):
        order.append("encode")
        destination.write_bytes(b"encoded")

    monkeypatch.setattr("car_music_manager.process._encode_pass", encode)
    monkeypatch.setattr(
        "car_music_manager.process.verify_decodable", lambda *_: order.append("verify")
    )
    monkeypatch.setattr("car_music_manager.process.write_id3v23", lambda *_: order.append("tag"))
    monkeypatch.setattr("car_music_manager.process.read_tags", lambda *_: TagData(title="x"))

    result = process_one(source, output)

    assert result.exists()
    assert source.read_bytes() == b"source"
    assert order == ["encode", "tag", "verify"]
