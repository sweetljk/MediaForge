from __future__ import annotations

import os
import re
import shutil
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from mediaforge.core.errors import ConversionError
from mediaforge.engines.process import run_process
from mediaforge.services.settings import Settings

TOOL_META = {
    "ffmpeg": ("ffmpeg", "https://ffmpeg.org/download.html"),
    "ffprobe": ("ffprobe", "https://ffmpeg.org/download.html"),
    "libreoffice": ("soffice", "https://www.libreoffice.org/download/download-libreoffice/"),
    "imagemagick": ("magick", "https://imagemagick.org/script/download.php"),
}


@dataclass(frozen=True)
class ToolInfo:
    name: str
    path: str = ""
    available: bool = False
    version: str = "未检测"
    error: str = ""
    url: str = ""


class ToolRegistry:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._cache: dict[str, ToolInfo] = {}
        self._encoders: set[str] | None = None
        self._lock = threading.RLock()

    def _candidates(self, name: str) -> list[str]:
        configured = getattr(self.settings, name, "")
        if configured:
            # soffice.exe is a GUI launcher on Windows and does not expose the
            # console output needed for version/error reporting; its sibling is
            # the supported console entry point to the same installation.
            if name == "libreoffice" and os.name == "nt" and Path(configured).suffix.lower() == ".exe":
                console = Path(configured).with_suffix(".com")
                if console.is_file():
                    return [str(console)]
            return [str(Path(configured).expanduser())]
        executable = TOOL_META[name][0]
        candidates = []
        env = os.environ.get(f"MEDIAFORGE_{name.upper()}")
        if env:
            candidates.append(env)
        # Resolve portable tools relative to the executable, never the working
        # directory. Keep paths dynamic so moving an extracted folder works.
        frozen = getattr(sys, "frozen", False)
        project = Path(sys.executable).resolve().parent if frozen else Path(__file__).resolve().parents[2]
        roots = [project / ".tools"]
        # Also support the original workspace-shaped archive: dist/MediaForge
        # beside a top-level .tools directory, without the VBS launcher.
        if frozen and project.parent.name.lower() == "dist":
            roots.append(project.parent.parent / ".tools")
        filenames = [executable + (".exe" if os.name == "nt" else "")]
        if name == "libreoffice" and os.name == "nt":
            filenames.insert(0, "soffice.com")
        for bundled in roots:
            if bundled.is_dir():
                for filename in filenames:
                    candidates.extend(str(p) for p in sorted(bundled.glob(f"**/{filename}")))
        located = shutil.which(executable)
        if located:
            candidates.append(located)
        if name == "libreoffice":
            candidates.extend([
                str(Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "LibreOffice/program/soffice.com"),
                str(Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "LibreOffice/program/soffice.exe"),
                "/usr/bin/libreoffice", "/Applications/LibreOffice.app/Contents/MacOS/soffice",
            ])
        if name == "ffprobe" and self.settings.ffmpeg:
            candidates.append(str(Path(self.settings.ffmpeg).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")))
        return candidates

    def detect(self, name: str) -> ToolInfo:
        if name not in TOOL_META:
            raise ValueError(name)
        _, url = TOOL_META[name]
        error = "未安装或未找到。请安装工具，或在设置中指定可执行文件。"
        info = ToolInfo(name=name, error=error, version="未安装", url=url)
        for candidate in self._candidates(name):
            if not Path(candidate).is_file():
                continue
            try:
                output = run_process([candidate, "--version" if name == "libreoffice" else "-version"], timeout=12)
                version = output.splitlines()[0][:180] if output else "版本未知"
                signature = {"ffmpeg": "ffmpeg", "ffprobe": "ffprobe", "libreoffice": "libreoffice", "imagemagick": "imagemagick"}[name]
                if signature not in output.lower():
                    raise ConversionError("指定的程序不是预期的工具，请检查路径。")
                info = ToolInfo(name, str(Path(candidate).resolve()), True, version, "", url)
                break
            except (OSError, ConversionError) as exc:
                info = ToolInfo(name, candidate, False, "不可用", str(exc), url)
        with self._lock:
            self._cache[name] = info
            if name == "ffmpeg":
                self._encoders = None
        return info

    def detect_all(self) -> dict[str, ToolInfo]:
        for name in TOOL_META:
            self.detect(name)
        return dict(self._cache)

    def get(self, name: str) -> ToolInfo:
        with self._lock:
            cached = self._cache.get(name)
        return cached if cached is not None else self.detect(name)

    def require(self, name: str) -> str:
        info = self.get(name)
        if not info.available:
            raise ConversionError(f"需要 {TOOL_META.get(name, (name,))[0]}：{info.error}\n安装指引：{info.url}")
        return info.path

    def encoders(self) -> set[str]:
        with self._lock:
            if self._encoders is not None:
                return set(self._encoders)
        output = run_process([self.require("ffmpeg"), "-hide_banner", "-encoders"], timeout=15)
        encoders = set()
        for line in output.splitlines():
            match = re.match(r"^\s*[VAS][A-Z.]{5}\s+(\S+)", line)
            if match and match.group(1) != "=":
                encoders.add(match.group(1))
        with self._lock:
            self._encoders = encoders
        return set(encoders)
