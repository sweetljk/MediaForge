from pathlib import Path
import sys
import threading
import time

import pytest

from mediaforge.core.errors import CancelledError, ConversionError, SkipError
from mediaforge.core.formats import classify_file, converter_for
from mediaforge.core.models import Job, JobStatus
from mediaforge.engines.process import run_process
from mediaforge.services.settings import Settings
from mediaforge.services.tools import ToolRegistry
from mediaforge.utils.paths import resolve_output


@pytest.mark.parametrize("name,category", [("测试.MP4", "video"), ("a.WAV", "audio"), ("图片.JPG", "image"), ("x.docx", "document"), ("x.PDF", "pdf"), ("x.exe", "unknown")])
def test_identification(name, category):
    assert classify_file(name) == category


def test_names_and_original_protection(tmp_path):
    original = tmp_path / "原始 file.png"
    original.write_bytes(b"keep")
    assert resolve_output(tmp_path, original.name).name == "原始 file (1).png"
    assert resolve_output(tmp_path, original.name, "overwrite", protected=[original]) != original
    with pytest.raises(SkipError):
        resolve_output(tmp_path, original.name, "skip")
    assert original.read_bytes() == b"keep"
    with pytest.raises(ConversionError):
        resolve_output(tmp_path, "../escape.jpg")


def test_state_transitions(tmp_path):
    job = Job("image", [], "png", tmp_path)
    with pytest.raises(ValueError):
        job.transition(JobStatus.COMPLETED)
    job.transition(JobStatus.RUNNING)
    assert job.started_at
    job.transition(JobStatus.COMPLETED)
    assert job.finished_at and job.elapsed >= 0
    with pytest.raises(ValueError):
        job.transition(JobStatus.RUNNING)


def test_missing_tool_has_installation_guidance():
    tools = ToolRegistry(Settings(ffmpeg="C:/does-not-exist/ffmpeg.exe"))
    with pytest.raises(ConversionError, match="安装指引"):
        tools.require("ffmpeg")


def test_process_cancel_terminates_child(tmp_path):
    event = threading.Event()
    timer = threading.Timer(0.3, event.set)
    timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(CancelledError):
            run_process([sys.executable, "-c", "import time; time.sleep(30)"], cancel=event, timeout=10)
        assert time.monotonic() - started < 5
    finally:
        timer.cancel()


def test_process_timeout_and_error():
    with pytest.raises(ConversionError, match="超时"):
        run_process([sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.2)
    with pytest.raises(ConversionError, match="7"):
        run_process([sys.executable, "-c", "raise SystemExit(7)"], timeout=5)


def test_process_unicode_path(tmp_path):
    path = tmp_path / "有 空格 & dollar $.py"
    path.write_text("print('OK')", encoding="utf-8")
    assert run_process([sys.executable, str(path)], timeout=5) == "OK"


def test_invalid_target():
    with pytest.raises(ConversionError):
        converter_for("image", "exe")


def test_settings_corrupt_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIAFORGE_DATA_DIR", str(tmp_path))
    (tmp_path / "settings.json").write_text('{"concurrency": "bad"}', encoding="utf-8")
    assert Settings.load().concurrency == 1
    settings = Settings(theme="light", output_dir=str(tmp_path / "中文 输出"))
    settings.save()
    assert Settings.load().output_dir == settings.output_dir


def test_real_long_path_image_conversion(tmp_path):
    from PIL import Image
    from mediaforge.converters.image import convert
    from mediaforge.engines.base import ConversionContext
    directory = tmp_path
    for index in range(5):
        directory = directory / (f"long-{index}-" + "x" * 42)
    directory.mkdir(parents=True)
    source = directory / "中文 image.png"
    output = directory / "结果 output.webp"
    Image.new("RGB", (12, 12), "blue").save(source)
    convert(Job("image", [source], "webp", directory), output,
            ConversionContext(ToolRegistry(Settings()), threading.Event(), tmp_path / "log.txt", lambda *args: None))
    assert output.is_file() and len(str(output)) > 260
