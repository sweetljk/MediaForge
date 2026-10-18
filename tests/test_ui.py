"""GUI integration checks use generated files and a real isolated conversion worker."""
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from mediaforge.core.models import JobStatus
from mediaforge.services.settings import Settings
from mediaforge.services.tools import TOOL_META, ToolInfo, ToolRegistry
from mediaforge.ui.i18n import NAV
from mediaforge.ui.params import ParamsDialog
from mediaforge.ui.theme import apply_theme
from mediaforge.ui.window import MainWindow


@pytest.fixture
def window(qtbot, qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIAFORGE_DATA_DIR", str(tmp_path / "app-data"))
    monkeypatch.setattr(ToolRegistry, "detect_all", lambda self: {name: ToolInfo(name, available=False, version="未安装", error="测试环境未安装", url=meta[1]) for name, meta in TOOL_META.items()})
    settings = Settings(output_dir=str(tmp_path / "outputs"), temp_dir=str(tmp_path / "temporary"), log_dir=str(tmp_path / "logs"))
    apply_theme(qapp, "dark")
    result = MainWindow(settings); qtbot.addWidget(result); result.show()
    qtbot.waitUntil(lambda: bool(result.tool_results), timeout=5000)
    yield result
    result.manager.shutdown(wait=True)
    result.pool.waitForDone(5000)
    result.close()


def wait_complete(qtbot, window, count=1):
    try:
        qtbot.waitUntil(lambda: len(window.manager.jobs()) == count and all(job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.SKIPPED} for job in window.manager.jobs()), timeout=20000)
    except Exception:
        pytest.fail(f"Queue did not settle: {[job.to_dict() for job in window.manager.jobs()]}; image page enabled={window.conversion_pages['image'].isEnabled()}")
    return window.manager.jobs()[-1]


def test_navigation_theme_and_parameter_values(window, qtbot):
    for key, _ in NAV:
        qtbot.mouseClick(window.nav[key], Qt.MouseButton.LeftButton)
        assert window.current_page == key
        assert window.nav[key].isChecked()
    window.toggle_theme()
    assert window.settings.theme == "light"
    assert Settings.load().theme == "light"
    dialog = ParamsDialog("video", {"video_codec": "h264", "width": 1280, "audio_track": "1"}, {"libx264", "aac"}, window)
    assert dialog.values()["video_codec"] == "h264"
    assert dialog.values()["width"] == 1280
    assert dialog.values()["audio_track"] == "1"
    assert dialog.fields["video_codec"].findData("h265") < 0
    dialog.deleteLater()


def test_real_image_conversion_from_ui(window, qtbot, tmp_path):
    source = tmp_path / "中文 图片.png"
    Image.new("RGB", (32, 20), "#53c8a7").save(source)
    page = window.conversion_pages["image"]
    page.add_files([source]); page.target.setCurrentIndex(page.target.findData("tiff"))
    page.params = {"width": 16, "keep_aspect": True}
    page.enqueue(True)
    job = wait_complete(qtbot, window)
    assert job.status == JobStatus.COMPLETED, job.error
    assert window.current_page == "tasks"
    assert job.progress == 100
    with Image.open(job.output_paths[0]) as result:
        assert result.format == "TIFF"
        assert result.size == (16, 10)
    window.pages["tasks"].refresh()
    assert window.pages["tasks"].table.item(0, 2).text() == "已完成"


def test_native_text_html_without_libreoffice(window, qtbot, tmp_path):
    source = tmp_path / "中文 文本.txt"; source.write_text("本地文本 & <安全>", encoding="utf-8")
    page = window.conversion_pages["document"]
    page.add_files([source]); page.target.setCurrentIndex(page.target.findData("html")); page.enqueue(True)
    job = wait_complete(qtbot, window)
    assert job.status == JobStatus.COMPLETED, job.error
    content = job.output_paths[0].read_text(encoding="utf-8")
    assert "本地文本 &amp; &lt;安全&gt;" in content


def test_image_information_loss_confirmed_before_submit(window, qtbot, tmp_path, monkeypatch):
    messages = []
    def confirm(parent, title, message, *args):
        messages.append(message)
        return QMessageBox.StandardButton.Yes
    monkeypatch.setattr(QMessageBox, "question", confirm)
    source = tmp_path / "透明.png"; Image.new("RGBA", (12, 12), (255, 0, 0, 0)).save(source)
    page = window.conversion_pages["image"]; page.add_files([source]); page.target.setCurrentIndex(page.target.findData("jpeg")); page.enqueue(True)
    job = wait_complete(qtbot, window)
    assert job.status == JobStatus.COMPLETED, job.error
    assert any("透明度" in message and "有损压缩" in message for message in messages)
    with Image.open(job.output_paths[0]) as result: assert result.getpixel((0, 0)) == (255, 255, 255)


def test_missing_document_tool_is_actionable(window, tmp_path, monkeypatch):
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text: messages.append(text))
    source = tmp_path / "示例.docx"; source.write_bytes(b"Not read by conversion: tool absent")
    page = window.conversion_pages["document"]; page.add_files([source]); page.enqueue(True)
    assert not window.manager.jobs()
    assert window.current_page == "settings"
    assert "libreoffice" in messages[0]


def test_pdf_mode_notice_and_global_timeout_saved(window):
    page = window.conversion_pages["pdf"]
    page.operation.setCurrentIndex(page.operation.findData("images_to_pdf"))
    assert "第一帧" in page.notice.text()
    assert "白色" in page.notice.text()
    settings = window.pages["settings"]; settings.timeout.setValue(900); settings.save()
    assert Settings.load().timeout == 900
