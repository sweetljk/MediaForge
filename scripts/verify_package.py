"""Generate public test fixtures and exercise the windowed executable's worker."""
from __future__ import annotations

import json
import argparse
import os
from dataclasses import asdict
from pathlib import Path
import sys

from PIL import Image
import pymupdf

from mediaforge.core.models import Job
from mediaforge.engines.process import run_process
from mediaforge.services.settings import Settings
from mediaforge.services.tools import ToolRegistry


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path, default=root / "dist/MediaForge/MediaForge.exe")
    parser.add_argument("--area", type=Path, default=root / "artifacts/package-check")
    parser.add_argument("--portable", action="store_true", help="Do not pass configured tool paths to the EXE")
    args = parser.parse_args()
    executable = args.executable.resolve()
    area = args.area.resolve()
    area.mkdir(parents=True, exist_ok=True)
    if args.portable:
        for name in ("ffmpeg", "ffprobe", "libreoffice", "imagemagick"):
            os.environ.pop(f"MEDIAFORGE_{name.upper()}", None)
        os.environ["PATH"] = str(Path(os.environ["WINDIR"]) / "System32")
        os.chdir(area)
    settings = Settings(output_dir=str(area / "out"), temp_dir=str(area / "temp"), log_dir=str(area / "logs"))
    tools = ToolRegistry(settings)
    for name in ("ffmpeg", "ffprobe", "libreoffice"):
        found = tools.get(name)
        if found.available:
            setattr(settings, name, found.path)
    source_image = area / "中文 样例.png"
    Image.new("RGBA", (100, 70), (30, 180, 120, 180)).save(source_image)
    source_text = area / "文档 样例.txt"
    source_text.write_text("MediaForge packaged conversion <test>\n中文测试", encoding="utf-8")
    source_pdf = area / "页面 样例.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((36, 50), "MediaForge packaged PDF")
        pdf.save(source_pdf)
    cases = [("image", source_image, "jpeg", {}), ("document", source_text, "html", {}),
             ("pdf", source_pdf, "png", {"operation": "render"})]
    if settings.ffmpeg and settings.ffprobe:
        clip = area / "视频 样例.mp4"
        run_process([settings.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=160x120:r=12",
                     "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "0.5", "-c:v", "libx264", "-c:a", "aac", str(clip)], timeout=30)
        cases += [("video", clip, "mkv", {}), ("audio", clip, "mp3", {})]
    if settings.libreoffice:
        cases += [("document", source_text, "pdf", {})]
    if args.portable:
        assert len(cases) == 6, "All engines must be available for portable verification"
        # Workers and GUI must find tools themselves from the relocated EXE.
        for name in ("ffmpeg", "ffprobe", "libreoffice", "imagemagick"):
            setattr(settings, name, "")
    reports = []
    for number, (category, source, target, params) in enumerate(cases):
        folder = area / f"{number}-{category}"
        folder.mkdir(exist_ok=True)
        events = folder / "events.jsonl"
        events.write_text("", encoding="utf-8")
        output = folder / ("result." + target)
        job = Job(category, [source], target, folder, params)
        spec = folder / "spec.json"
        spec.write_text(json.dumps({"action": "convert", "events": str(events), "job": job.to_dict(),
                                    "output": str(output), "log_path": str(folder / "task.log"),
                                    "settings": asdict(settings)}, ensure_ascii=False), encoding="utf-8")
        run_process([str(executable), "--worker", str(spec)], timeout=90)
        messages = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
        result = next(event for event in messages if event["type"] == "result")
        paths = [Path(p) for p in result["paths"]]
        assert paths and all(p.is_file() and p.stat().st_size > 0 for p in paths)
        reports.append({"category": category, "target": target, "passed": True, "outputs": [str(p) for p in paths]})
    os.environ["MEDIAFORGE_DATA_DIR"] = str(area / "app-data")
    settings.save()
    run_process([str(executable), "--smoke-test", "--screenshot", str(area / "packaged-ui.png")], timeout=45)
    assert (area / "packaged-ui.png").is_file()
    (area / "report.json").write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Packaged window and {len(reports)} real conversion flows passed.")


if __name__ == "__main__":
    main()
