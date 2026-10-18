from __future__ import annotations

from pathlib import Path

from mediaforge.core.formats import classify_file


def inspect_file(path: str | Path, tools) -> dict:
    path = Path(path)
    category = classify_file(path)
    result = {"name": path.name, "size": path.stat().st_size, "type": category, "summary": ""}
    try:
        if category == "image":
            from PIL import Image
            with Image.open(path) as img:
                frames = getattr(img, "n_frames", 1)
                result.update(width=img.width, height=img.height, frames=frames,
                              transparency="A" in img.mode or "transparency" in img.info)
                result["summary"] = f"{img.width} × {img.height} · {img.format} · {frames} 帧" if frames > 1 else f"{img.width} × {img.height} · {img.format}"
        elif category == "pdf":
            from mediaforge.engines.native import inspect_pdf
            result.update(inspect_pdf(path, Path(tools.settings.temp_dir)))
        elif category in {"video", "audio"}:
            from mediaforge.engines.ffmpeg import probe
            info = probe(path, tools)
            duration = float(info.get("format", {}).get("duration", 0) or 0)
            videos = [s for s in info.get("streams", []) if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")]
            audios = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
            result.update(duration=duration, streams=info.get("streams", []))
            parts = [f"{int(duration // 60):02d}:{int(duration % 60):02d}"]
            if videos:
                stream = videos[0]
                parts += [f"{stream.get('width', '?')} × {stream.get('height', '?')}", stream.get("codec_name", "")]
            if audios:
                parts += [f"{len(audios)} 音轨", audios[0].get("codec_name", "")]
            result["summary"] = " · ".join(parts)
        elif category == "document":
            from mediaforge.converters.document import document_targets
            formats = document_targets(path.suffix)
            result["summary"] = "可转 " + " / ".join(f.upper() for f in formats)
    except Exception as exc:
        result["summary"] = "信息读取失败：" + str(exc).splitlines()[0][:180]
    return result
