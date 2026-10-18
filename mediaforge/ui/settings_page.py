from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QScrollArea, QSpinBox, QVBoxLayout, QWidget

from mediaforge.services.tools import TOOL_META
from mediaforge.ui.params import ParamsDialog
from mediaforge.ui.theme import apply_theme
from mediaforge.ui.widgets import button, card, label


class SettingsPage(QWidget):
    def __init__(self, window):
        super().__init__(); self.window = window; self.paths = {}; self.statuses = {}; self.default_params = dict(window.settings.default_params)
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(16)
        outer.addWidget(label("设置", "title")); outer.addWidget(label("管理本地转换工具、文件目录与界面偏好。", "muted"))
        scroll = QScrollArea(); scroll.setWidgetResizable(True); content = QWidget(); layout = QVBoxLayout(content); layout.setContentsMargins(0, 0, 6, 0); layout.setSpacing(16)
        tool_card, tools = card(); tools.addWidget(label("转换工具", "section")); tools.addWidget(label("留空时自动查找系统安装。选择工具的可执行文件；检测只读取本机版本，不连接服务器。", "muted", True))
        for name, title in [("ffmpeg", "FFmpeg · 视频 / 音频"), ("ffprobe", "FFprobe · 媒体信息"), ("libreoffice", "LibreOffice · Office 文档"), ("imagemagick", "ImageMagick · 可选，扩展图像后端尚未开放")]:
            tools.addWidget(label(title))
            row = QHBoxLayout(); path = QLineEdit(getattr(window.settings, name)); path.setPlaceholderText("自动检测系统路径"); self.paths[name] = path; row.addWidget(path, 1)
            choose = button("浏览…"); choose.clicked.connect(lambda _, n=name: self.choose_tool(n)); row.addWidget(choose)
            guide = button("安装指引"); guide.clicked.connect(lambda _, n=name: QDesktopServices.openUrl(QUrl(TOOL_META[n][1]))); row.addWidget(guide); tools.addLayout(row)
            status = label("等待检测…", "muted", True); status.setTextInteractionFlags(status.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse); tools.addWidget(status); self.statuses[name] = status
        self.detect = button("重新检测已保存的路径", "refresh"); self.detect.clicked.connect(window.detect_tools); tools.addWidget(self.detect); layout.addWidget(tool_card)
        general, general_layout = card(); general_layout.addWidget(label("文件与性能", "section")); form = QFormLayout(); form.setSpacing(12)
        for name, title in [("output_dir", "默认输出目录"), ("temp_dir", "临时文件目录"), ("log_dir", "日志目录")]:
            row = QHBoxLayout(); path = QLineEdit(getattr(window.settings, name)); self.paths[name] = path; row.addWidget(path, 1)
            browse = button("浏览…"); browse.clicked.connect(lambda _, n=name: self.choose_dir(n)); row.addWidget(browse); form.addRow(title, row)
        self.theme = QComboBox(); self.theme.addItem("深色 · 石墨绿", "dark"); self.theme.addItem("浅色 · 雾白", "light"); self.theme.setCurrentIndex(max(0, self.theme.findData(window.settings.theme))); form.addRow("界面主题", self.theme)
        self.concurrency = QSpinBox(); self.concurrency.setRange(1, 3); self.concurrency.setValue(window.settings.concurrency); form.addRow("同时处理任务数", self.concurrency)
        self.timeout = QSpinBox(); self.timeout.setRange(30, 86400); self.timeout.setValue(window.settings.timeout); self.timeout.setSuffix(" 秒"); form.addRow("转换进程超时", self.timeout)
        self.overwrite = QComboBox()
        for title, value in [("自动改名（推荐）", "rename"), ("跳过同名输出", "skip"), ("覆盖（提交前确认）", "overwrite")]: self.overwrite.addItem(title, value)
        self.overwrite.setCurrentIndex(max(0, self.overwrite.findData(window.settings.overwrite))); form.addRow("输出冲突策略", self.overwrite)
        general_layout.addLayout(form); general_layout.addWidget(label("并发建议设为 1。大视频、高清图像和文档转换会占用较多内存。仅清理程序创建的临时工作目录。", "muted", True)); layout.addWidget(general)
        defaults, default_layout = card(); default_layout.addWidget(label("默认转换参数", "section")); row = QHBoxLayout()
        for category, title in [("video", "视频"), ("audio", "音频"), ("image", "图片"), ("document", "文档"), ("pdf", "PDF")]:
            edit = button(title, category); edit.clicked.connect(lambda _, c=category: self.edit_defaults(c)); row.addWidget(edit)
        default_layout.addLayout(row); default_layout.addWidget(label("保存后应用到转换页面。已经加入队列的任务保留原有参数。", "muted", True)); layout.addWidget(defaults)
        layout.addWidget(label("MediaForge 0.1.0  ·  本地处理，无遥测\n核心后端：FFmpeg / Pillow / LibreOffice / PyMuPDF / pypdf", "muted", True)); layout.addStretch()
        scroll.setWidget(content); outer.addWidget(scroll, 1)
        bottom = QHBoxLayout(); self.feedback = label("", "status"); bottom.addWidget(self.feedback, 1)
        save = button("保存并检测", "check", True); save.clicked.connect(self.save); bottom.addWidget(save); outer.addLayout(bottom)

    def choose_tool(self, name):
        path, _ = QFileDialog.getOpenFileName(self, "选择可执行文件", self.paths[name].text(), "程序 (*.exe *.com);;所有文件 (*)")
        if path: self.paths[name].setText(path)

    def choose_dir(self, name):
        path = QFileDialog.getExistingDirectory(self, "选择目录", self.paths[name].text())
        if path: self.paths[name].setText(path)

    def edit_defaults(self, category):
        dialog = ParamsDialog(category, self.default_params.get(category, {}), self.window.encoders, self)
        if dialog.exec() == QDialog.DialogCode.Accepted: self.default_params[category] = dialog.values()

    def save(self):
        if self.window.manager.active_count:
            self.window.show_message("正在处理任务", "请等待当前任务结束或取消后，再更改转换工具和存储设置。"); return
        for name in ("output_dir", "temp_dir", "log_dir"):
            if not self.paths[name].text().strip(): self.window.show_message("目录不能为空", "请填写默认输出、临时文件和日志目录。"); return
        settings = self.window.settings
        previous = dict(settings.__dict__)
        try:
            for name, widget in self.paths.items(): setattr(settings, name, widget.text().strip())
            settings.theme = self.theme.currentData(); settings.overwrite = self.overwrite.currentData(); settings.concurrency = self.concurrency.value(); settings.timeout = self.timeout.value(); settings.default_params = self.default_params
            settings.save()
        except Exception as exc:
            settings.__dict__.update(previous); self.window.show_error(f"设置未保存：{exc}"); return
        from PySide6.QtWidgets import QApplication
        apply_theme(QApplication.instance(), settings.theme)
        for category, page in self.window.conversion_pages.items():
            page.output.setText(settings.output_dir); page.params = dict(settings.default_params.get(category, {})); page.param_label.setText("使用已保存的默认参数")
        self.feedback.setText("设置已保存"); self.window.detect_tools()

    def update_tools(self, results):
        for name, info in results.items():
            self.statuses[name].setText(("已就绪 · " + info.version + "\n" + info.path) if info.available else "未就绪 · " + info.error)
            self.statuses[name].setObjectName("status" if info.available else "muted")
