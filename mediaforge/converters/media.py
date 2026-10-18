"""Validated video and audio conversion using the shared external-process context."""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import TYPE_CHECKING

from mediaforge.core.errors import ConversionError
from mediaforge.engines.ffmpeg import FFmpegProgress, media_duration, probe

if TYPE_CHECKING:
    from mediaforge.core.models import Job
    from mediaforge.engines.base import ConversionContext

VIDEO_CONTAINERS = {
    "mp4": {"h264", "hevc", "mpeg4"}, "m4v": {"h264", "hevc", "mpeg4"},
    "mov": {"h264", "hevc", "mpeg4", "prores"},
    "mkv": {"h264", "hevc", "vp8", "vp9", "av1", "mpeg4", "mpeg2video", "prores", "ffv1"},
    "avi": {"h264", "mpeg4", "mjpeg"}, "webm": {"vp8", "vp9", "av1"},
}
AUDIO_CONTAINERS = {
    "mp4": {"aac", "mp3", "alac"}, "m4v": {"aac", "mp3", "alac"},
    "mov": {"aac", "mp3", "alac", "pcm_s16le", "pcm_s16be"},
    "mkv": {"aac", "mp3", "opus", "vorbis", "flac", "alac", "ac3", "eac3", "dts", "pcm_s16le", "pcm_s16be"},
    "avi": {"mp3", "pcm_s16le", "ac3"}, "webm": {"opus", "vorbis"},
    "mp3": {"mp3"}, "wav": {"pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le"},
    "flac": {"flac"}, "aac": {"aac"}, "m4a": {"aac", "alac"},
    "ogg": {"vorbis", "opus", "flac"}, "opus": {"opus"},
    "aiff": {"pcm_s16be", "pcm_s24be", "pcm_s32be"},
}
ENCODERS = {
    "h264": ("libx264", "h264"), "h265": ("libx265", "hevc"), "hevc": ("libx265", "hevc"),
    "vp9": ("libvpx-vp9", "vp9"), "mpeg4": ("mpeg4", "mpeg4"),
    "aac": ("aac", "aac"), "mp3": ("libmp3lame", "mp3"), "opus": ("libopus", "opus"),
    "vorbis": ("libvorbis", "vorbis"), "flac": ("flac", "flac"),
    "pcm_s16le": ("pcm_s16le", "pcm_s16le"), "pcm_s16be": ("pcm_s16be", "pcm_s16be"),
}
AUDIO_DEFAULTS = {"mp3": "mp3", "wav": "pcm_s16le", "flac": "flac", "aac": "aac",
                  "m4a": "aac", "ogg": "vorbis", "opus": "opus", "aiff": "pcm_s16be",
                  "mp4": "aac", "m4v": "aac", "mov": "aac", "mkv": "aac",
                  "avi": "mp3", "webm": "opus"}
MUXERS = {"mkv": "matroska", "m4v": "mp4", "m4a": "ipod", "aac": "adts"}
TEXT_SUBTITLES = {"subrip", "srt", "ass", "ssa", "mov_text", "webvtt", "text"}


def _number(params: dict, key: str, default: float = 0, maximum: float = 1e9) -> float:
    try:
        raw = params.get(key, default)
        value = float(default if raw is None or raw == "" else raw)
    except (TypeError, ValueError) as exc:
        raise ConversionError(f"无效参数：{key}") from exc
    if not math.isfinite(value) or value < 0 or value > maximum:
        raise ConversionError(f"参数 {key} 超出支持范围（0–{maximum:g}）")
    return value


def _bitrate(params: dict, key: str) -> str | None:
    value = params.get(key)
    if value in (None, "", 0):
        return None
    value = str(value).strip()
    if not re.fullmatch(r"[1-9][0-9]*(?:\.[0-9]+)?[kKmM]?", value):
        raise ConversionError(f"{key} 应为正数，例如 192k 或 4M")
    return value


def _codec(name: str, allowed: set[str], encoders: set[str]) -> str:
    if name == "copy":
        return "copy"
    if name not in ENCODERS or ENCODERS[name][1] not in allowed:
        raise ConversionError(f"目标容器不支持编码 {name}；请选择自动或其他目标格式")
    encoder = ENCODERS[name][0]
    if encoder not in encoders:
        raise ConversionError(f"当前 FFmpeg 未安装编码器 {encoder}；请更换 FFmpeg 构建或编码设置")
    return encoder


def _audio_streams(params: dict, streams: list[dict], category: str) -> list[dict]:
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    if params.get("remove_audio"):
        return []
    selected = params.get("audio_track", "all" if category == "video" else 0)
    if selected == "all" and category == "video":
        return audio
    if selected == "all":
        selected = 0  # Standalone audio containers expose one selected track.
    try:
        index = int(selected)
    except (TypeError, ValueError) as exc:
        raise ConversionError("音轨序号必须是从 0 开始的整数") from exc
    if not 0 <= index < len(audio):
        raise ConversionError(f"音轨 {index} 不存在；文件包含 {len(audio)} 条音轨")
    return [audio[index]]


def build_media_command(job: Job, output: Path, probe_data: dict, encoders: set[str]) -> list[str]:
    """Return validated argv WITHOUT executable. Output must be a private staging file."""
    if len(job.inputs) != 1:
        raise ConversionError("每个音视频转换任务应只包含一个输入文件；批量转换请创建多个任务")
    if job.category not in {"video", "audio"}:
        raise ConversionError("媒体引擎仅支持视频或音频任务")
    target, params = job.target_format.lower(), job.params
    allowed_targets = VIDEO_CONTAINERS if job.category == "video" else set(AUDIO_DEFAULTS) - set(VIDEO_CONTAINERS)
    if target not in allowed_targets:
        raise ConversionError(f"不支持的{job.category}目标格式：{target}")
    streams = probe_data.get("streams", [])
    video = [s for s in streams if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")]
    if job.category == "video" and not video:
        raise ConversionError("输入文件没有可转换的视频流")
    selected_audio = _audio_streams(params, streams, job.category)
    if job.category == "audio" and not selected_audio:
        raise ConversionError("输入文件没有可转换的音轨，或已选择移除音轨")
    start, end = _number(params, "trim_start"), _number(params, "trim_end")
    duration = media_duration(probe_data)
    if end and end <= start:
        raise ConversionError("裁剪终点必须晚于起点")
    if duration and start >= duration:
        raise ConversionError("裁剪起点超出媒体时长")
    args = ["-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
            "-protocol_whitelist", "file,pipe", "-i", str(job.inputs[0])]
    if start:
        args += ["-ss", f"{start:g}"]
    if end:
        args += ["-t", f"{end - start:g}"]
    args += ["-map_metadata", "0" if params.get("preserve_metadata", True) else "-1"]
    # Chapters cannot be kept accurately when the source timeline is cropped.
    args += ["-map_chapters", "-1" if start or end or job.category == "audio" else "0"]
    if job.category == "video":
        codec_name = params.get("video_codec", "auto")
        if codec_name == "auto":
            codec_name = "vp9" if target == "webm" else "mpeg4" if target == "avi" else "h264"
        codec = _codec(codec_name, VIDEO_CONTAINERS[target], encoders)
        width, height = _number(params, "width", maximum=16384), _number(params, "height", maximum=16384)
        fps, bitrate = _number(params, "fps", maximum=240), _bitrate(params, "video_bitrate")
        if any(value and (value < 2 or value != int(value) or int(value) % 2) for value in (width, height)):
            raise ConversionError("视频宽度和高度必须是大于 1 的偶数")
        args += ["-map", f"0:{video[0]['index']}", "-c:v", codec]
        if codec == "copy":
            if video[0].get("codec_name") not in VIDEO_CONTAINERS[target]:
                raise ConversionError("原视频编码与目标容器不兼容，不能使用流复制")
            if width or height or fps or bitrate or start or end:
                raise ConversionError("流复制不能同时调整分辨率、帧率、码率或精确裁剪；请选择重新编码")
        else:
            if width and height:
                scale = f"scale={int(width)}:{int(height)}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={int(width)}:{int(height)}:(ow-iw)/2:(oh-ih)/2,setsar=1"
            elif width or height:
                scale = f"scale={int(width) if width else -2}:{int(height) if height else -2}"
            else:
                scale = "pad=ceil(iw/2)*2:ceil(ih/2)*2"
            args += ["-vf", scale, "-pix_fmt", "yuv420p", "-threads", "2", "-metadata:s:v:0", "rotate=0"]
            if codec in {"libx264", "libx265"}:
                args += ["-preset", "medium"]
                if not bitrate:
                    args += ["-crf", "23" if codec == "libx264" else "26"]
            elif codec == "libvpx-vp9":
                args += ["-deadline", "good", "-cpu-used", "2"]
                if not bitrate:
                    args += ["-crf", "32", "-b:v", "0"]
            elif codec == "mpeg4" and not bitrate:
                args += ["-q:v", "4"]
            if codec == "libx265" and target in {"mp4", "m4v", "mov"}:
                args += ["-tag:v", "hvc1"]
            if fps:
                args += ["-r", f"{fps:g}"]
            if bitrate:
                args += ["-b:v", bitrate]
        subtitle_mode = params.get("subtitles", "remove")
        subtitles = [s for s in streams if s.get("codec_type") == "subtitle"]
        if subtitle_mode not in {"remove", "copy", "convert"}:
            raise ConversionError("字幕选项必须为 remove、copy 或 convert")
        if subtitle_mode != "remove" and subtitles:
            if target == "avi":
                raise ConversionError("AVI 不支持此字幕保留方式；请选择移除字幕或 MKV")
            accepted = {"mov_text"} if target in {"mp4", "m4v", "mov"} else {"webvtt"} if target == "webm" else {"subrip", "ass", "ssa", "webvtt", "dvd_subtitle", "dvb_subtitle", "hdmv_pgs_subtitle"}
            if subtitle_mode == "copy" and accepted and any(s.get("codec_name") not in accepted for s in subtitles):
                raise ConversionError("原字幕编码不兼容目标容器；请选择转换文字字幕、移除字幕或 MKV")
            if subtitle_mode == "convert" and any(s.get("codec_name") not in TEXT_SUBTITLES for s in subtitles):
                raise ConversionError("图片字幕不能直接转换为文字；请选择 MKV 流复制或移除字幕（OCR 未开放）")
            subtitle_codec = "copy" if subtitle_mode == "copy" else "mov_text" if target in {"mp4", "m4v", "mov"} else "webvtt" if target == "webm" else "srt"
            if subtitle_codec != "copy" and subtitle_codec not in encoders:
                raise ConversionError(f"当前 FFmpeg 未安装字幕编码器 {subtitle_codec}")
            args += ["-map", "0:s", "-c:s", subtitle_codec]
            if target == "mkv" and subtitle_mode == "copy":
                args += ["-map", "0:t?", "-c:t", "copy"]
        else:
            args += ["-sn"]
    if selected_audio:
        for stream in selected_audio:
            args += ["-map", f"0:{stream['index']}"]
        codec_name = params.get("audio_codec", "auto")
        if codec_name == "auto":
            codec_name = AUDIO_DEFAULTS[target]
        codec = _codec(codec_name, AUDIO_CONTAINERS[target], encoders)
        rate = _number(params, "sample_rate", maximum=384000)
        channels = _number(params, "channels", maximum=8)
        volume = _number(params, "volume", default=1, maximum=16)
        bitrate = _bitrate(params, "audio_bitrate")
        if rate != int(rate) or channels != int(channels):
            raise ConversionError("采样率与声道数必须是整数")
        args += ["-c:a", codec]
        if codec == "copy":
            if any(s.get("codec_name") not in AUDIO_CONTAINERS[target] for s in selected_audio):
                raise ConversionError("原音轨编码与目标容器不兼容，不能使用流复制")
            if rate or channels or volume != 1 or bitrate or start or end:
                raise ConversionError("音频流复制不能同时调整采样率、声道、音量、码率或精确裁剪")
        else:
            if codec == "libopus" and rate and rate not in {8000, 12000, 16000, 24000, 48000}:
                raise ConversionError("Opus 采样率仅支持 8000、12000、16000、24000 或 48000 Hz")
            if rate:
                args += ["-ar", str(int(rate))]
            if channels:
                args += ["-ac", str(int(channels))]
            if volume != 1:
                args += ["-af", f"volume={volume:g}"]
            if bitrate and codec not in {"flac", "pcm_s16le", "pcm_s16be"}:
                args += ["-b:a", bitrate]
            elif codec == "libvorbis":
                # Fixed 192 kb/s is invalid for common low-rate mono inputs.
                args += ["-q:a", "4"]
            elif codec in {"aac", "libmp3lame", "libopus"}:
                args += ["-b:a", "192k" if codec != "libopus" else "128k"]
    else:
        args += ["-an"]
    if job.category == "audio":
        args += ["-sn", "-dn"]
        covers = [s for s in streams if s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic") and s.get("codec_name") in {"mjpeg", "png"}]
        if params.get("preserve_cover", True) and target in {"mp3", "m4a", "flac"} and covers:
            args += ["-map", f"0:{covers[0]['index']}", "-c:v", "copy", "-disposition:v:0", "attached_pic"]
        else:
            args += ["-vn"]
        if target == "mp3":
            args += ["-id3v2_version", "3"]
    if target in {"mp4", "m4v", "mov", "m4a"}:
        args += ["-movflags", "+faststart"]
    args += ["-max_muxing_queue_size", "2048", "-f", MUXERS.get(target, target), str(output)]
    return args


def convert(job: Job, output: Path, context: ConversionContext) -> list[Path]:
    context.check_cancelled()
    executable = context.tools.require("ffmpeg")
    context.progress(None, "正在读取媒体信息")
    data = probe(job.inputs[0], context.tools, context)
    args = build_media_command(job, output, data, context.tools.encoders())
    streams = data.get("streams", [])
    selected = _audio_streams(job.params, streams, job.category)
    if job.category == "video":
        selected += [stream for stream in streams if stream.get("codec_type") == "video" and not stream.get("disposition", {}).get("attached_pic")][:1]
    stream_lengths = [media_duration({"streams": [stream]}) for stream in selected]
    selected_duration = max(stream_lengths) if stream_lengths and all(length is not None for length in stream_lengths) else None
    duration = selected_duration or media_duration(data)
    all_media = {stream["index"] for stream in streams if stream.get("codec_type") in {"audio", "video"} and not stream.get("disposition", {}).get("attached_pic")}
    # Container length is not a valid truncation check for one shorter audio
    # track extracted from a longer video or a multi-track container.
    validate_length = selected_duration is not None or {stream["index"] for stream in selected} == all_media
    start, end = _number(job.params, "trim_start"), _number(job.params, "trim_end")
    if duration:
        duration = max(0, min(duration, end) - start) if end else duration - start
    elif end:
        duration = end - start
    context.progress(0.0 if duration else None, "正在转换")
    context.run([executable, *args], on_line=FFmpegProgress(duration, context.progress))
    context.check_cancelled()
    if not output.is_file() or output.stat().st_size < 32:
        raise ConversionError("转换工具没有生成有效文件")
    verified = probe(output, context.tools, context)
    expected = "video" if job.category == "video" else "audio"
    if not any(s.get("codec_type") == expected for s in verified.get("streams", [])):
        raise ConversionError("输出文件验证失败：缺少目标媒体流")
    actual_duration = media_duration(verified)
    if validate_length and duration and actual_duration is not None:
        # Encoder delay and timestamp rounding matter most for tiny excerpts.
        tolerance = max(0.1, duration * 0.5) if duration <= 1 else max(0.5, duration * 0.05)
        if actual_duration <= 0 or actual_duration + tolerance < duration:
            raise ConversionError("输出文件验证失败：媒体时长异常缩短")
    context.progress(100.0, "媒体输出已验证")
    return [output]
