"""Pillow-backed image conversion. No user file is ever modified in place."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
import warnings

from PIL import Image, ImageColor, ImageOps, UnidentifiedImageError, features

from mediaforge.core.errors import ConversionError

if TYPE_CHECKING:
    from mediaforge.core.models import Job
    from mediaforge.engines.base import ConversionContext


FORMATS = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP", "bmp": "BMP", "tif": "TIFF", "tiff": "TIFF", "gif": "GIF"}
MULTIFRAME = {"GIF", "WEBP", "TIFF", "PNG"}
MAX_PIXELS = 80_000_000
MAX_SEQUENCE_PIXELS = 100_000_000


def image_warnings(path: Path, target: str, params: dict | None = None) -> list[str]:
    """Return information-loss notices for the confirmation UI."""
    params = params or {}
    result = []
    fmt = FORMATS.get(target.lower().lstrip("."), "")
    try:
        with Image.open(path) as source:
            alpha = "A" in source.getbands() or "transparency" in source.info
            if alpha and fmt in {"JPEG", "BMP"}:
                result.append("目标格式不保留透明度，透明区域将填充所选背景色。")
            if getattr(source, "n_frames", 1) > 1:
                if params.get("animation", "first") == "first":
                    result.append("这是多帧图片，本次仅保存第一帧。")
                elif fmt not in MULTIFRAME:
                    result.append("目标格式不支持多帧，请改为仅保存第一帧或选择 GIF / WebP / TIFF / PNG。")
                elif fmt == "TIFF":
                    result.append("TIFF 将保存多页，但不保留动画播放时长。")
            if source.getexif() and fmt in {"GIF", "BMP"}:
                result.append("目标格式无法保留原始 EXIF 元数据。")
    except (OSError, ValueError, UnidentifiedImageError):
        return ["无法读取图片，请确认文件完整且格式受支持。"]
    if fmt in {"JPEG", "WEBP"}:
        result.append("当前输出使用有损压缩，重新编码可能损失细节。")
    if fmt == "GIF":
        result.append("GIF 最多使用 256 色，色彩和半透明效果可能发生变化。")
    return result


def _transform(frame: Image.Image, params: dict, fmt: str) -> Image.Image:
    result = ImageOps.exif_transpose(frame)
    width, height = int(params.get("width", 0)), int(params.get("height", 0))
    if width < 0 or height < 0:
        raise ConversionError("图片宽高不能为负数。")
    if width or height:
        if params.get("keep_aspect", True):
            ratio = min(width / result.width if width else float("inf"), height / result.height if height else float("inf"))
            size = (max(1, round(result.width * ratio)), max(1, round(result.height * ratio)))
        else:
            size = (width or result.width, height or result.height)
        if size[0] * size[1] > MAX_PIXELS:
            raise ConversionError("目标图片过大，请将像素总量降低到 8000 万以下。")
        result = result.resize(size, Image.Resampling.LANCZOS)
    rotation = int(params.get("rotation", 0)) % 360
    if rotation:
        result = result.rotate(-rotation, expand=True, resample=Image.Resampling.BICUBIC)
    if fmt in {"JPEG", "BMP"}:
        if "A" in result.getbands() or "transparency" in result.info:
            color = ImageColor.getrgb(str(params.get("background", "#FFFFFF")))
            rgba = result.convert("RGBA")
            canvas = Image.new("RGB", result.size, color[:3])
            canvas.paste(rgba, mask=rgba.getchannel("A"))
            result = canvas
        else:
            result = result.convert("RGB")
    elif fmt == "GIF":
        result = result.convert("RGBA")
    elif fmt == "WEBP" and result.mode not in {"RGB", "RGBA"}:
        result = result.convert("RGBA" if "transparency" in result.info else "RGB")
    return result


def convert(job: "Job", output: Path, context: "ConversionContext") -> list[Path]:
    if len(job.inputs) != 1:
        raise ConversionError("每个图片转换任务需要一个输入文件，请使用批量队列处理多个文件。")
    fmt = FORMATS.get(job.target_format)
    if fmt is None:
        raise ConversionError(f"不支持的图片输出格式：{job.target_format}")
    if fmt == "WEBP" and not features.check("webp"):
        raise ConversionError("当前 Pillow 未包含 WebP 编码支持，请重新安装官方 Pillow wheel。")
    params = job.params
    quality, compression = int(params.get("quality", 90)), int(params.get("compression", 6))
    if not 1 <= quality <= 100 or not 0 <= compression <= 9:
        raise ConversionError("图片质量范围为 1–100，PNG 压缩等级范围为 0–9。")
    if params.get("animation", "first") not in {"first", "all"}:
        raise ConversionError("多帧选项必须为 first 或 all。")
    context.check_cancelled()
    output.parent.mkdir(parents=True, exist_ok=True)
    frames: list[Image.Image] = []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(job.inputs[0]) as source:
                if source.width * source.height > MAX_PIXELS:
                    raise ConversionError("图片超过 8000 万像素的安全处理限制。")
                count = getattr(source, "n_frames", 1) if params.get("animation", "first") == "all" else 1
                if count > 1 and fmt not in MULTIFRAME:
                    raise ConversionError("目标格式不支持多帧，请选择仅保存第一帧。")
                if count * source.width * source.height > MAX_SEQUENCE_PIXELS:
                    raise ConversionError("多帧图片解码总量过大，请仅转换第一帧或缩短原始动画。")
                metadata = source.info.copy()
                durations = []
                for index in range(count):
                    context.check_cancelled()
                    source.seek(index)
                    frame = _transform(source.copy(), params, fmt)
                    if count * frame.width * frame.height > MAX_SEQUENCE_PIXELS:
                        frame.close()
                        raise ConversionError("目标多帧图片总量过大，请降低宽高或仅转换第一帧。")
                    frames.append(frame)
                    durations.append(int(source.info.get("duration", 100)))
                    context.progress((index + 1) / (count + 1) * 100, f"已处理图片帧 {index + 1}/{count}")
                options: dict = {}
                if fmt in {"JPEG", "WEBP"}:
                    options["quality"] = quality
                if fmt == "JPEG":
                    options.update(optimize=True, progressive=True)
                if fmt == "PNG":
                    options["compress_level"] = compression
                if fmt == "TIFF":
                    options["compression"] = "tiff_deflate"
                if params.get("preserve_metadata", True):
                    if fmt in {"JPEG", "WEBP", "PNG", "TIFF"}:
                        exif = frames[0].getexif()
                        if exif:
                            options["exif"] = exif.tobytes()
                        if metadata.get("icc_profile"):
                            options["icc_profile"] = metadata["icc_profile"]
                        if metadata.get("dpi") and fmt != "WEBP":
                            options["dpi"] = metadata["dpi"]
                # Do not let metadata attached to copies bypass the user's choice.
                if not params.get("preserve_metadata", True):
                    for frame in frames:
                        frame.info.clear()
                if count > 1:
                    options.update(save_all=True, append_images=frames[1:])
                    if fmt != "TIFF":
                        options.update(duration=durations, loop=int(metadata.get("loop", 0)))
                    if fmt == "GIF":
                        options["disposal"] = 2
                context.check_cancelled()
                frames[0].save(output, format=fmt, **options)
        context.check_cancelled()
        with Image.open(output) as checked:
            if checked.format != fmt or checked.width <= 0 or checked.height <= 0:
                raise ConversionError("输出图片验证失败。")
            checked.verify()
        context.progress(100, "图片已编码并验证")
        return [output]
    except (OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise ConversionError(f"图片转换失败：{exc}") from exc
    finally:
        for frame in frames:
            frame.close()
