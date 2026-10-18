import os
import sys
from pathlib import Path

import pytest

from mediaforge.services.settings import Settings
from mediaforge.services.tools import ToolRegistry


@pytest.mark.parametrize("layout", ["flat", "workspace"])
@pytest.mark.parametrize("name,filename", [("ffmpeg", "ffmpeg"), ("ffprobe", "ffprobe"), ("libreoffice", "soffice")])
def test_portable_tools_follow_executable_not_working_directory(tmp_path, monkeypatch, layout, name, filename):
    root = tmp_path / "移动后的 中文目录"
    exe_dir = root if layout == "flat" else root / "dist" / "MediaForge"
    exe_dir.mkdir(parents=True)
    suffix = ".com" if name == "libreoffice" else ".exe"
    tool = root / ".tools" / name / "bin" / (filename + (suffix if os.name == "nt" else ""))
    tool.parent.mkdir(parents=True)
    tool.touch()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "MediaForge.exe"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(f"MEDIAFORGE_{name.upper()}", raising=False)
    monkeypatch.setattr("mediaforge.services.tools.shutil.which", lambda _: "C:/system/tool.exe")
    monkeypatch.setattr("mediaforge.services.tools.run_process", lambda argv, **kwargs: name + " test")
    registry = ToolRegistry(Settings())
    assert registry._candidates(name)[0] == str(tool)
    assert registry.require(name) == str(tool.resolve())


def test_explicit_tool_configuration_still_has_priority(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "MediaForge.exe"))
    path = str(tmp_path / "custom" / "ffmpeg.exe")
    assert ToolRegistry(Settings(ffmpeg=path))._candidates("ffmpeg") == [str(Path(path))]
