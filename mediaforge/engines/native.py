"""Native PDF/image libraries run in separate processes for reliable cancellation."""
from __future__ import annotations

import json
import sys
import threading
from dataclasses import asdict
from pathlib import Path

from mediaforge.core.errors import ConversionError
from mediaforge.engines.process import run_process

PREFIX = "MEDIAFORGE_EVENT "


def worker_command(spec: Path) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--worker", str(spec)]
    return [sys.executable, "-m", "mediaforge.worker", str(spec)]


def convert_isolated(job, output, context, settings):
    spec = output.parent / ".worker-spec.json"
    events = output.parent / ".worker-events.jsonl"
    events.write_text("", encoding="utf-8")
    spec.write_text(json.dumps({"action": "convert", "job": job.to_dict(), "output": str(output),
                                "settings": asdict(settings), "log_path": str(context.log_path), "events": str(events)}, ensure_ascii=False), encoding="utf-8")
    result = {}
    stop = threading.Event()

    def on_line(line):
        try:
            event = json.loads(line)
            if event["type"] == "progress":
                context.progress(event.get("value"), event.get("message", ""))
            elif event["type"] == "result":
                result["paths"] = event["paths"]
            elif event["type"] == "error":
                result["error"] = event["message"]
        except (KeyError, ValueError):
            result["error"] = "本地工作进程返回了无效数据。"

    def watch_events():
        # Read only actual flushed worker events; this never estimates progress.
        with events.open(encoding="utf-8") as stream:
            pending = ""
            while True:
                line = stream.readline()
                if line:
                    pending += line
                    if pending.endswith("\n"):
                        on_line(pending)
                        pending = ""
                elif stop.is_set():
                    break
                else:
                    stop.wait(0.08)

    watcher = threading.Thread(target=watch_events, daemon=True)
    watcher.start()
    error = None

    try:
        context.run(worker_command(spec))
    except Exception as exc:
        error = exc
    finally:
        stop.set()
        watcher.join(timeout=5)
    context.check_cancelled()
    if result.get("error"):
        raise ConversionError(result["error"])
    if error:
        raise error
    if "paths" not in result:
        raise ConversionError("本地工作进程没有返回转换结果。")
    return [Path(p) for p in result["paths"]]


def inspect_pdf(path: Path, temp_dir: Path | None = None) -> dict:
    # A dedicated process also protects GUI inspection workers from MuPDF's
    # unsupported shared-library multi-threaded access.
    import tempfile
    if temp_dir:
        temp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mediaforge-inspect-", dir=temp_dir) as directory:
        spec = Path(directory) / "request.json"
        events = Path(directory) / "events.jsonl"
        spec.write_text(json.dumps({"action": "inspect_pdf", "path": str(path), "events": str(events)}), encoding="utf-8")
        run_process(worker_command(spec), timeout=30)
        for line in reversed(events.read_text(encoding="utf-8").splitlines()):
            event = json.loads(line)
            if event.get("type") == "result":
                return event["info"]
    raise ConversionError("无法读取 PDF 信息。")
