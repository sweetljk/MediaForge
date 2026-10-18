from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from mediaforge.ui.icons import icon
from mediaforge.ui.i18n import STATUS
from mediaforge.ui.queue_page import local_time
from mediaforge.ui.widgets import button, card, cell, label, table


class HomePage(QWidget):
    def __init__(self, window):
        super().__init__(); self.window = window
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(19)
        hero, hero_layout = card(); hero.setObjectName("hero")
        hero_layout.addWidget(label("YOUR FILES. YOUR WORKSPACE.", "eyebrow"))
        hero_layout.addWidget(label("让文件，成为你需要的格式。", "title"))
        hero_layout.addWidget(label("视频、音频、图片与文档，一个安静高效的本地工作空间。", "muted", True))
        layout.addWidget(hero)
        grid = QGridLayout(); grid.setSpacing(13)
        for index, (key, title, subtitle, color) in enumerate([
            ("video", "视频转换", "MP4 · MKV · MOV · WebM", "#85b6f4"),
            ("audio", "音频转换", "MP3 · WAV · FLAC · Opus", "#c2a4ee"),
            ("image", "图片转换", "PNG · JPEG · WebP · TIFF", "#79d5b0"),
            ("document", "文档转换", "Office · PDF · 文本", "#e7bb75"),
        ]):
            entry = button(title + "\n" + subtitle); entry.setObjectName("entry"); entry.setIcon(icon(key, color, 35)); entry.setIconSize(QSize(35, 35)); entry.setMinimumHeight(100)
            entry.clicked.connect(lambda _, k=key: window.navigate(k)); grid.addWidget(entry, index // 2, index % 2)
        layout.addLayout(grid)
        row = QHBoxLayout(); row.addWidget(label("最近任务", "section")); row.addStretch(); history = button("全部历史", "arrow"); history.clicked.connect(lambda: window.navigate("history")); row.addWidget(history); layout.addLayout(row)
        self.recent = table(["文件", "格式", "状态", "完成时间"])
        self.recent.setColumnWidth(1, 75); self.recent.setColumnWidth(2, 90); self.recent.setColumnWidth(3, 125)
        self.recent.setMinimumHeight(150); self.recent.setMaximumHeight(210); self.recent.cellDoubleClicked.connect(lambda *_: window.navigate("history")); layout.addWidget(self.recent, 1)
        self.empty = label("尚无转换记录。选择上方入口，或直接将文件拖入窗口。", "muted", True); layout.addWidget(self.empty)
        bottom = QHBoxLayout(); bottom.setSpacing(15)
        tools, tools_layout = card(); tools_layout.addWidget(label("转换引擎", "section")); self.tool_status = label("正在检测本地工具…", "muted", True); tools_layout.addWidget(self.tool_status)
        configure = button("管理工具", "settings"); configure.clicked.connect(lambda: window.navigate("settings")); tools_layout.addWidget(configure); bottom.addWidget(tools, 1)
        shortcuts, shortcuts_layout = card(); shortcuts_layout.addWidget(label("常用工具", "section"))
        pdf = button("合并 / 拆分 PDF", "pdf"); pdf.clicked.connect(lambda: window.navigate("pdf")); shortcuts_layout.addWidget(pdf)
        extract = button("从视频提取音频", "audio"); extract.clicked.connect(lambda: window.navigate("audio")); shortcuts_layout.addWidget(extract); bottom.addWidget(shortcuts, 1)
        layout.addLayout(bottom)

    def refresh(self):
        try: records = self.window.history.load()[:3]
        except Exception: records = []
        self.recent.setRowCount(len(records)); self.empty.setVisible(not records)
        for row, record in enumerate(records):
            names = [Path(p).name for p in record.get("inputs", [])]
            self.recent.setItem(row, 0, cell(names[0] if names else "—"))
            self.recent.setItem(row, 1, cell(record.get("target_format", "").upper()))
            self.recent.setItem(row, 2, cell(STATUS.get(record.get("status"), "—")))
            self.recent.setItem(row, 3, cell(local_time(record.get("finished_at"))))

    def update_tools(self, results):
        self.tool_status.setText("\n".join(f"{'●' if info.available else '○'}  {name}  ·  {'已就绪' if info.available else '未安装 / 不可用'}" for name, info in results.items() if name != "imagemagick") + "\n●  Pillow / PDF 工具  ·  已就绪")
