"""FFprobe inspection and FFmpeg's machine-readable progress protocol."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from mediaforge.core.errors import ConversionError
from mediaforge.engines.process import run_process

if TYPE_CHECKING:
    from mediaforge.engines.base import ConversionContext
    from mediaforge.services.tools import ToolRegistry


def probe(path: Path, tools: ToolRegistry, context: ConversionContext | None = None) -> dict:
    """Read streams and container information; never resolves remote protocols."""
    path = Path(path).resolve()
    if not path.is_file():
        raise ConversionError(f"找不到媒体文件：{path.name}")
    args = [tools.require("ffprobe"), "-v", "error", "-protocol_whitelist", "file,pipe",
            "-show_entries", "format=duration,size,format_name:stream=index,codec_type,codec_name,width,height,sample_rate,channels,duration:stream_disposition=attached_pic:stream_side_data=rotation",
            "-of", "json", str(path)]
    try:
        if context is not None:
            raw = context.run(args, timeout=60)
        else:
            raw = run_process(args, timeout=30)
        data = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise ConversionError(f"读取媒体信息失败：{path.name}（{exc}）") from exc
    if not isinstance(data, dict) or not isinstance(data.get("streams"), list):
        raise ConversionError(f"媒体信息无效：{path.name}")
    return data


def media_duration(data: dict) -> float | None:
    values = [data.get("format", {}).get("duration")]
    values.extend(stream.get("duration") for stream in data.get("streams", []))
    for value in values:
        try:
            number = float(value)
            if math.isfinite(number) and number > 0:
                return number
        except (ValueError, TypeError):
            pass
    return None


class FFmpegProgress:
    """Progress is elapsed output timestamp / expected duration, never a timer."""

    def __init__(self, duration: float | None, callback: Callable[[float | None, str], None]):
        self.duration = duration
        self.callback = callback
        self.last = 0.0

    def __call__(self, line: str) -> None:
        key, separator, value = line.strip().partition("=")
        if not separator:
            return
        seconds = None
        try:
            if key in {"out_time_us", "out_time_ms"}:
                # Despite its legacy name, out_time_ms is also in microseconds.
                seconds = int(value) / 1_000_000
            elif key == "out_time" and value != "N/A":
                hours, minutes, fraction = value.split(":")
                seconds = int(hours) * 3600 + int(minutes) * 60 + float(fraction)
        except (ValueError, OverflowError):
            return
        if seconds is not None and seconds >= 0 and math.isfinite(seconds):
            percent = min(99.0, max(self.last, seconds / self.duration * 100)) if self.duration else None
            if percent is not None:
                self.last = percent
            self.callback(percent, f"已处理 {seconds:.1f} 秒")
        elif key == "progress" and value == "end":
            self.callback(99.0 if self.duration else None, "编码完成，正在验证输出")


def describe_media(data: dict) -> str:
    """Compact UI-safe description, without metadata or personal file contents."""
    parts = []
    duration = media_duration(data)
    if duration:
        parts.append(f"{int(duration // 60):02d}:{duration % 60:04.1f}")
    for stream in data.get("streams", []):
        kind = stream.get("codec_type")
        if kind == "video" and not stream.get("disposition", {}).get("attached_pic"):
            parts.append(f"{stream.get('width', '?')}×{stream.get('height', '?')} {stream.get('codec_name', '')}")
            break
    audio = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
    if audio:
        parts.append(f"{len(audio)} 音轨 · {audio[0].get('codec_name', '')}")
    return " · ".join(parts) or "未发现可用音视频流"
