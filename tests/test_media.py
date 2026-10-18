from __future__ import annotations

import math
import struct
import threading
import wave
from pathlib import Path

import pytest

from mediaforge.converters.media import build_media_command, convert
from mediaforge.core.errors import CancelledError, ConversionError
from mediaforge.core.models import Job
from mediaforge.engines.base import ConversionContext
from mediaforge.engines.ffmpeg import FFmpegProgress, describe_media, media_duration, probe
from mediaforge.engines.process import run_process
from mediaforge.services.settings import Settings
from mediaforge.services.tools import ToolRegistry


ENCODERS = {"libx264", "libx265", "libvpx-vp9", "mpeg4", "aac", "libmp3lame", "libopus",
            "libvorbis", "pcm_s16le", "pcm_s16be", "flac", "mov_text", "srt", "webvtt"}
DATA = {"format": {"duration": "10.0"}, "streams": [
    {"index": 0, "codec_type": "video", "codec_name": "h264", "width": 320, "height": 240},
    {"index": 1, "codec_type": "audio", "codec_name": "aac"},
    {"index": 2, "codec_type": "audio", "codec_name": "aac"},
]}


def job(tmp_path, category="video", target="mp4", **params):
    return Job(category, [tmp_path / "中文 文件 & 空格.mkv"], target, tmp_path, params)


def command(tmp_path, category="video", target="mp4", data=None, **params):
    return build_media_command(job(tmp_path, category, target, **params), tmp_path / f"输出 文件.{target}", data or DATA, ENCODERS)


def test_paths_are_separate_arguments_and_protocols_are_local(tmp_path):
    args = command(tmp_path)
    assert str(tmp_path / "中文 文件 & 空格.mkv") == args[args.index("-i") + 1]
    assert args[args.index("-protocol_whitelist") + 1] == "file,pipe"
    assert args[-1] == str(tmp_path / "输出 文件.mp4")
    assert args[args.index("-c:v") + 1] == "libx264"


@pytest.mark.parametrize("target,encoder,muxer", [
    ("mp4", "libx264", "mp4"), ("m4v", "libx264", "mp4"),
    ("mkv", "libx264", "matroska"), ("mov", "libx264", "mov"),
    ("avi", "mpeg4", "avi"), ("webm", "libvpx-vp9", "webm"),
])
def test_video_defaults(tmp_path, target, encoder, muxer):
    args = command(tmp_path, target=target)
    assert args[args.index("-c:v") + 1] == encoder
    assert args[-2] == muxer


@pytest.mark.parametrize("target,encoder", [
    ("mp3", "libmp3lame"), ("wav", "pcm_s16le"), ("flac", "flac"), ("aac", "aac"),
    ("m4a", "aac"), ("ogg", "libvorbis"), ("opus", "libopus"), ("aiff", "pcm_s16be"),
])
def test_audio_defaults(tmp_path, target, encoder):
    args = command(tmp_path, category="audio", target=target)
    assert args[args.index("-c:a") + 1] == encoder
    assert "-vn" in args
    assert args.count("-map") == 1


def test_audio_track_selection_and_disable(tmp_path):
    args = command(tmp_path, audio_track=1)
    mapped = [args[i + 1] for i, item in enumerate(args) if item == "-map"]
    assert mapped == ["0:0", "0:2"]
    assert "-an" in command(tmp_path, remove_audio=True)
    with pytest.raises(ConversionError, match="不存在"):
        command(tmp_path, audio_track=9)


@pytest.mark.parametrize("params,message", [
    ({"video_codec": "h264"}, "容器不支持"),
    ({"video_codec": "copy"}, "原视频编码"),
])
def test_incompatible_webm_rejected(tmp_path, params, message):
    with pytest.raises(ConversionError, match=message):
        command(tmp_path, target="webm", **params)


@pytest.mark.parametrize("change", [{"width": 640}, {"fps": 30}, {"trim_start": 1}, {"video_bitrate": "2M"}])
def test_copy_rejects_video_processing(tmp_path, change):
    with pytest.raises(ConversionError, match="流复制不能"):
        command(tmp_path, video_codec="copy", **change)


def test_audio_copy_compatible_and_incompatible(tmp_path):
    assert "copy" in command(tmp_path, category="audio", target="m4a", audio_codec="copy")
    with pytest.raises(ConversionError, match="原音轨编码"):
        command(tmp_path, category="audio", target="mp3", audio_codec="copy")
    with pytest.raises(ConversionError, match="音频流复制不能"):
        command(tmp_path, category="audio", target="m4a", audio_codec="copy", volume=0.5)


def test_missing_encoder_is_actionable(tmp_path):
    with pytest.raises(ConversionError, match="未安装编码器 libx264"):
        build_media_command(job(tmp_path), tmp_path / "out.mp4", DATA, {"aac"})


def test_subtitle_conversion_and_image_subtitle_rejection(tmp_path):
    data = {"streams": [*DATA["streams"], {"index": 3, "codec_type": "subtitle", "codec_name": "ass"}]}
    args = command(tmp_path, data=data, subtitles="convert")
    assert args[args.index("-c:s") + 1] == "mov_text"
    with pytest.raises(ConversionError, match="原字幕编码"):
        command(tmp_path, data=data, subtitles="copy")
    data["streams"][-1]["codec_name"] = "hdmv_pgs_subtitle"
    with pytest.raises(ConversionError, match="图片字幕"):
        command(tmp_path, data=data, subtitles="convert")


def test_cover_preservation_only_where_supported(tmp_path):
    data = {"streams": [*DATA["streams"], {"index": 4, "codec_type": "video", "codec_name": "mjpeg", "disposition": {"attached_pic": 1}}]}
    args = command(tmp_path, category="audio", target="mp3", data=data)
    assert "attached_pic" in args and "0:4" in args
    assert "-vn" in command(tmp_path, category="audio", target="wav", data=data)


def test_audio_trim_volume_zero_and_rate(tmp_path):
    args = command(tmp_path, category="audio", target="wav", trim_start=1.5, trim_end=3, volume=0, sample_rate=22050, channels=1)
    assert args[args.index("-ss") + 1] == "1.5"
    assert args[args.index("-t") + 1] == "1.5"
    assert args[args.index("-af") + 1] == "volume=0"
    assert args[args.index("-ar") + 1] == "22050"
    assert args[args.index("-ac") + 1] == "1"


@pytest.mark.parametrize("params", [{"trim_start": 11}, {"trim_start": 2, "trim_end": 1}, {"width": 321}, {"fps": float("nan")}, {"video_bitrate": "1M -i file"}])
def test_invalid_parameters_rejected(tmp_path, params):
    with pytest.raises(ConversionError):
        command(tmp_path, **params)


def test_progress_uses_media_timestamps_monotonically():
    events = []
    parser = FFmpegProgress(10, lambda value, message: events.append(value))
    for line in ["frame=5", "out_time_us=2500000", "out_time_ms=1000000", "out_time=00:00:07.500", "out_time_us=N/A", "out_time_us=-9223372036854775807", "progress=end"]:
        parser(line)
    assert events == [25.0, 25.0, 75.0, 99.0]
    assert all(value < 100 for value in events)  # Only successful output validation completes.


def test_unknown_duration_is_indeterminate():
    events = []
    FFmpegProgress(None, lambda value, message: events.append(value))("out_time_us=3000000")
    assert events == [None]
    assert media_duration({"format": {"duration": "N/A"}}) is None
    assert "320×240" in describe_media(DATA)


def test_missing_input_and_tool(tmp_path):
    registry = ToolRegistry(Settings(ffprobe=str(tmp_path / "missing-ffprobe.exe")))
    with pytest.raises(ConversionError, match="找不到媒体文件"):
        probe(tmp_path / "absent.mp4", registry)
    source = tmp_path / "exists.mp4"
    source.write_bytes(b"not a video")
    with pytest.raises(ConversionError, match="ffprobe"):
        probe(source, registry)


def test_cancelled_before_conversion_creates_no_output(tmp_path):
    event = threading.Event()
    event.set()
    context = ConversionContext(ToolRegistry(Settings()), event, tmp_path / "log.txt", lambda *args: None)
    output = tmp_path / "out.mp4"
    with pytest.raises(CancelledError):
        convert(job(tmp_path), output, context)
    assert not output.exists()


@pytest.fixture(scope="module")
def real_tools():
    registry = ToolRegistry(Settings())
    if not registry.get("ffmpeg").available or not registry.get("ffprobe").available:
        pytest.skip("FFmpeg/FFprobe 未安装；需要真实工具才能执行媒体集成测试")
    return registry


@pytest.fixture(scope="module")
def samples(tmp_path_factory, real_tools):
    directory = tmp_path_factory.mktemp("媒体 样例")
    audio = directory / "中文 音频 & sample.wav"
    with wave.open(str(audio), "wb") as handle:
        handle.setparams((1, 2, 22050, 0, "NONE", "not compressed"))
        handle.writeframes(b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / 22050))) for i in range(22050)))
    video = directory / "中文 视频 & sample.mkv"
    run_process([real_tools.require("ffmpeg"), "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                 "testsrc2=size=160x120:rate=12:duration=1", "-i", str(audio), "-c:v", "mpeg4",
                 "-c:a", "pcm_s16le", "-y", str(video)], timeout=30)
    return audio, video


@pytest.mark.integration
@pytest.mark.parametrize("category,target", [("video", value) for value in ("mp4", "mkv", "mov", "avi", "webm", "m4v")]
                         + [("audio", value) for value in ("mp3", "wav", "flac", "aac", "m4a", "ogg", "opus", "aiff")])
def test_real_conversion_all_initial_formats(tmp_path, samples, real_tools, category, target):
    source = samples[1] if category == "video" else samples[0]
    output = tmp_path / f"真实 输出.{target}"
    events = []
    context = ConversionContext(real_tools, threading.Event(), tmp_path / "engine.log", lambda value, message: events.append(value), timeout=60)
    result = convert(Job(category, [source], target, tmp_path), output, context)
    assert result == [output] and output.stat().st_size > 100
    data = probe(output, real_tools)
    assert any(stream["codec_type"] == category for stream in data["streams"])
    assert 0.8 <= media_duration(data) <= 1.3
    assert events[-1] == 100
    # Decode every output: a readable container header alone is insufficient.
    run_process([real_tools.require("ffmpeg"), "-nostdin", "-v", "error", "-i", str(output), "-f", "null", "-"], timeout=30)


@pytest.mark.integration
def test_real_audio_extract_trim_and_silence(tmp_path, samples, real_tools):
    output = tmp_path / "提取.wav"
    context = ConversionContext(real_tools, threading.Event(), tmp_path / "engine.log", lambda *args: None)
    convert(Job("audio", [samples[1]], "wav", tmp_path, {"trim_start": 0.1, "trim_end": 0.7, "volume": 0, "sample_rate": 16000}), output, context)
    with wave.open(str(output), "rb") as handle:
        assert handle.getframerate() == 16000
        assert handle.getnframes() == pytest.approx(9600, abs=1)
        assert set(handle.readframes(handle.getnframes())) == {0}


@pytest.mark.integration
def test_extract_shorter_audio_from_long_video(tmp_path, real_tools):
    source = tmp_path / "长视频 短音轨.mp4"
    run_process([real_tools.require("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i", "color=s=160x120:r=12:d=3",
                 "-f", "lavfi", "-i", "sine=frequency=400:duration=0.5", "-c:v", "libx264", "-c:a", "aac", str(source)], timeout=30)
    output = tmp_path / "short.wav"
    context = ConversionContext(real_tools, threading.Event(), tmp_path / "engine.log", lambda *args: None)
    convert(Job("audio", [source], "wav", tmp_path), output, context)
    assert 0.45 <= media_duration(probe(output, real_tools)) <= 0.6
