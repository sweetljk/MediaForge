"""Private worker protocol. No GUI, networking, or persistent background service."""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from threading import Event

from mediaforge.core.models import Job
from mediaforge.core.formats import converter_for
from mediaforge.engines.base import ConversionContext
from mediaforge.services.settings import Settings
from mediaforge.services.tools import ToolRegistry


EVENT_PATH = None


def emit(event):
    # A windowed executable has no stdout; a private event file works on every
    # platform and carries only actual progress/result events.
    with EVENT_PATH.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=True) + "\n")


def main(argv=None) -> int:
    global EVENT_PATH
    args = sys.argv[1:] if argv is None else argv
    spec = {}
    try:
        spec = json.loads(Path(args[0]).read_text(encoding="utf-8"))
        EVENT_PATH = Path(spec["events"])
        if spec["action"] == "inspect_pdf":
            import pymupdf
            with pymupdf.open(spec["path"]) as pdf:
                if pdf.needs_pass:
                    info = {"summary": "PDF 已加密，需要先解密"}
                else:
                    first = pdf[0].rect if pdf.page_count else None
                    info = {"pages": pdf.page_count, "summary": f"{pdf.page_count} 页" + (f" · {first.width:.0f} × {first.height:.0f} pt" if first else "")}
            emit({"type": "result", "info": info})
            return 0
        data = spec["job"]
        job = Job(data["category"], data["inputs"], data["target_format"], data["output_dir"], data["params"], id=data["id"])
        settings = Settings(**spec["settings"])
        output = Path(spec["output"])
        context = ConversionContext(ToolRegistry(settings), Event(), Path(spec["log_path"]).with_suffix(".engine.log"),
                                    lambda value, message="": emit({"type": "progress", "value": value, "message": message}), settings.timeout)
        paths = converter_for(job.category, job.target_format)(job, output, context)
        emit({"type": "result", "paths": [str(p) for p in paths]})
        return 0
    except Exception as exc:
        if EVENT_PATH:
            emit({"type": "error", "message": str(exc)})
        if spec.get("log_path"):
            try:
                with Path(spec["log_path"]).open("a", encoding="utf-8") as log:
                    log.write("\nNative worker failure:\n" + traceback.format_exc())
            except OSError:
                pass
        if sys.stderr:
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
