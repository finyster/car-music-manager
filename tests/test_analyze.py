import subprocess
from pathlib import Path

from car_music_manager.analyze import analyze_audio


def test_analyze_audio_parses_ffprobe_payload(monkeypatch) -> None:
    payload = {
        "format": {"format_name": "mp3", "duration": "123.4", "bit_rate": "256000"},
        "streams": [
            {"codec_type": "audio", "codec_name": "mp3", "sample_rate": "44100", "channels": 2}
        ],
    }
    monkeypatch.setattr("car_music_manager.analyze.ffprobe_json", lambda *_: payload)

    info = analyze_audio(Path("中文 song.mp3"))

    assert info.duration_seconds == 123.4
    assert info.bitrate_bps == 256000
    assert info.sample_rate == 44100
    assert info.channels == 2


def test_run_command_uses_argument_list_without_shell(monkeypatch) -> None:
    captured = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        captured["args"] = args
        return subprocess.CompletedProcess(args[0], 0, "{}", "")

    monkeypatch.setattr("car_music_manager.tools.subprocess.run", fake_run)
    from car_music_manager.tools import run_command

    run_command(["ffprobe", "C:/測試 folder/song.mp3"])
    assert captured["args"][0] == ["ffprobe", "C:/測試 folder/song.mp3"]
    assert captured["shell"] is False
