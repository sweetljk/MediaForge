from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QVBoxLayout, QWidget

from mediaforge.core.formats import FORMATS, classify_file
from mediaforge.core.models import Job
from mediaforge.services.inspection import inspect_file
from mediaforge.ui.params import ParamsDialog
from mediaforge.ui.widgets import Worker, button, card, cell, label, size_text, table


DESCRIPTIONS = {
    "video": ("视频转换", "调整格式、画质和音轨，让视频适合每一次播放。", "FFmpeg · 按构建能力启用编码器"),
    "audio": ("音频转换", "转换音乐与录音，也可以从视频中提取音频。", "MP3 / AAC / OGG / Opus 属于有损格式；重复编码可能降低音质。"),
    "image": ("图片转换", "转换、缩放与旋转图片，批量处理也同样轻松。", "JPEG / BMP 不保留透明度；默认只处理动画第一帧。请在参数中选择多帧策略。"),
    "document": ("文档转换", "在本机转换 Office 文档、演示文稿与电子表格。", "LibreOffice 转换可能改变字体、分页和布局，请复核结果。PDF 转 Word / OCR 尚未开放。"),
    "pdf": ("PDF 工具", "按需要合并、拆分、提取页面，或在图片与 PDF 间转换。", "页码从 1 开始；合并按照列表顺序执行。加密 PDF 需先提供可读取的副本。"),
}


class ConversionPage(QWidget):
    queued = Signal()

    def __init__(self, category, window):
        super().__init__(); self.category = category; self.window = window
        self.paths = []; self.overrides = {}; self.params = dict(window.settings.default_params.get(category, {}))
        self.pending_inspections = set()
        self.inspection_workers = {}
        self.preflight_worker = None
        self.preflight_jobs = None
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(18)
        title, subtitle, notice = DESCRIPTIONS[category]
        outer.addWidget(label(title, "title")); outer.addWidget(label(subtitle, "muted", True))
        toolbar = QHBoxLayout(); toolbar.setSpacing(9)
        add = button("添加文件", "plus", True); add.clicked.connect(self.choose_files); toolbar.addWidget(add)
        folder = button("添加文件夹", "folder"); folder.clicked.connect(self.choose_folder); toolbar.addWidget(folder)
        toolbar.addStretch()
        single = button("单个文件参数", "settings"); single.clicked.connect(self.edit_selected); toolbar.addWidget(single)
        remove = button("移除", "delete"); remove.clicked.connect(self.remove_selected); toolbar.addWidget(remove)
        outer.addLayout(toolbar)
        if category == "pdf":
            row = QHBoxLayout(); row.addWidget(label("处理方式")); self.operation = QComboBox()
            for text, data in [("合并 PDF", "merge"), ("逐页拆分", "split"), ("提取指定页面", "extract"), ("PDF 页面转图片", "render"), ("图片转 PDF", "images_to_pdf")]: self.operation.addItem(text, data)
            row.addWidget(self.operation, 1)
            up = button("上移"); up.clicked.connect(lambda: self.move_selected(-1)); row.addWidget(up)
            down = button("下移"); down.clicked.connect(lambda: self.move_selected(1)); row.addWidget(down)
            outer.addLayout(row); self.operation.currentIndexChanged.connect(self.operation_changed)
        self.file_table = table(["文件名", "类型", "大小", "文件信息 / 参数"])
        self.file_table.setColumnWidth(1, 80); self.file_table.setColumnWidth(2, 90); self.file_table.setColumnWidth(3, 280)
        self.file_table.cellDoubleClicked.connect(lambda *_: self.edit_selected())
        outer.addWidget(self.file_table, 1)
        self.empty = label("将文件拖到这里，或点击「添加文件」开始\n所有文件都在本机处理，不会上传。", "muted", True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter); self.empty.setContentsMargins(16, 12, 16, 12); outer.addWidget(self.empty)
        self.count_label = label("尚未添加文件", "muted"); outer.addWidget(self.count_label)
        options, options_layout = card(); row = QHBoxLayout(); row.setSpacing(12)
        row.addWidget(label("目标格式")); self.target = QComboBox(); self.target.setMinimumWidth(125)
        for fmt in FORMATS[category]: self.target.addItem(fmt.upper(), fmt)
        row.addWidget(self.target)
        defaults = button("批量参数", "settings"); defaults.clicked.connect(self.edit_defaults); row.addWidget(defaults)
        row.addStretch(); self.param_label = label("使用默认参数", "muted"); row.addWidget(self.param_label)
        options_layout.addLayout(row)
        row2 = QHBoxLayout(); row2.addWidget(label("输出目录"))
        self.output = QLineEdit(window.settings.output_dir); self.output.setPlaceholderText("请选择输出目录")
        row2.addWidget(self.output, 1); browse = button("浏览…", "folder"); browse.clicked.connect(self.choose_output); row2.addWidget(browse)
        options_layout.addLayout(row2); outer.addWidget(options)
        self.notice = label(notice, "notice", True); outer.addWidget(self.notice)
        bottom = QHBoxLayout(); self.local_hint = label("本地处理  ·  默认保留源文件", "muted"); bottom.addWidget(self.local_hint); bottom.addStretch()
        queue = button("加入队列"); queue.clicked.connect(lambda: self.enqueue(False)); bottom.addWidget(queue)
        start = button("开始转换", "play", True); start.clicked.connect(lambda: self.enqueue(True)); bottom.addWidget(start)
        outer.addLayout(bottom)
        if category == "pdf": self.operation_changed()

    def choose_files(self):
        filters = "所有支持的文件 (*)"
        if self.category == "pdf" and self.operation.currentData() != "images_to_pdf": filters = "PDF 文件 (*.pdf);;所有文件 (*)"
        paths, _ = QFileDialog.getOpenFileNames(self, "添加待转换文件", "", filters)
        self.add_files(paths)

    def choose_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "添加文件夹（仅当前层级）")
        if directory:
            try: self.add_files([p for p in Path(directory).iterdir() if p.is_file()], silent=True)
            except OSError as exc: self.window.show_error(str(exc))

    def accepts(self, path):
        kind = classify_file(path)
        if self.category == "audio": return kind in {"audio", "video"}
        if self.category == "pdf": return kind == ("image" if self.operation.currentData() == "images_to_pdf" else "pdf")
        return kind == self.category

    def add_files(self, paths, silent=False):
        rejected = []
        for raw in paths:
            path = Path(raw).resolve()
            if not path.is_file() or not self.accepts(path): rejected.append(path.name); continue
            if path not in self.paths: self.paths.append(path)
        self.refresh_files()
        if rejected and not silent:
            self.window.show_message("未添加的文件", "下列文件不符合当前功能或无法读取：\n" + "\n".join(rejected[:12]))

    def refresh_files(self):
        self.file_table.setRowCount(len(self.paths))
        for row, path in enumerate(self.paths):
            self.file_table.setItem(row, 0, cell(path.name, str(path)))
            self.file_table.setItem(row, 1, cell(path.suffix.upper().lstrip(".")))
            try: size = size_text(path.stat().st_size)
            except OSError: size = "不可读取"
            self.file_table.setItem(row, 2, cell(size))
            suffix = " · 单独参数" if str(path) in self.overrides else ""
            info = self.window.file_cache.get(str(path))
            self.file_table.setItem(row, 3, cell((info.get("summary", "") if info else "读取信息…") + suffix))
            if info is None and str(path) not in self.pending_inspections:
                self.pending_inspections.add(str(path))
                def inspect(p=path):
                    try: return str(p), inspect_file(p, self.window.tools)
                    except Exception as exc: return str(p), {"summary": str(exc)}
                worker = Worker(inspect)
                worker.signals.result.connect(self.file_inspected)
                self.inspection_workers[str(path)] = worker
                self.window.pool.start(worker)
        self.empty.setVisible(not self.paths)
        self.count_label.setText(f"{len(self.paths)} 个文件 · 双击文件设置独立参数" if self.paths else "尚未添加文件")
        self.update_document_targets()

    def file_inspected(self, result):
        path, info = result; self.pending_inspections.discard(path); self.inspection_workers.pop(path, None); self.window.file_cache[path] = info
        if Path(path) in self.paths:
            row = self.paths.index(Path(path)); suffix = " · 单独参数" if path in self.overrides else ""
            self.file_table.setItem(row, 3, cell(info.get("summary", "已读取") + suffix))

    def update_document_targets(self):
        if self.category != "document": return
        from mediaforge.converters.document import document_targets
        choices = set(FORMATS["document"])
        for path in self.paths: choices &= set(document_targets(path.suffix))
        current = self.target.currentData(); self.target.clear()
        for fmt in FORMATS["document"]:
            if fmt in choices: self.target.addItem(fmt.upper(), fmt)
        idx = self.target.findData(current)
        if idx >= 0: self.target.setCurrentIndex(idx)

    def selected_rows(self):
        return sorted({item.row() for item in self.file_table.selectedItems()})

    def remove_selected(self):
        for row in reversed(self.selected_rows()): self.overrides.pop(str(self.paths.pop(row)), None)
        self.refresh_files()

    def move_selected(self, direction):
        selected = self.selected_rows()
        if len(selected) != 1: return
        row = selected[0]; destination = row + direction
        if 0 <= destination < len(self.paths):
            self.paths[row], self.paths[destination] = self.paths[destination], self.paths[row]
            self.refresh_files(); self.file_table.selectRow(destination)

    def choose_output(self):
        directory = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output.text())
        if directory: self.output.setText(directory)

    def edit_defaults(self):
        dialog = ParamsDialog(self.category, self.params, self.window.encoders, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.params = dialog.values(); self.param_label.setText("已设置批量参数")

    def edit_selected(self):
        rows = self.selected_rows()
        if len(rows) != 1:
            self.window.show_message("选择文件", "请先选中一个文件，再调整该文件的转换参数。"); return
        path = self.paths[rows[0]]
        if self.category == "pdf" and self.operation.currentData() in {"merge", "images_to_pdf"}:
            self.window.show_message("组合任务参数", "合并 PDF 和图片转 PDF 使用一组批量参数。请点击「批量参数」。"); return
        values = {**self.params, **self.overrides.get(str(path), {})}
        dialog = ParamsDialog(self.category, values, self.window.encoders, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.overrides[str(path)] = dialog.values(); self.refresh_files()

    def operation_changed(self):
        value = self.operation.currentData(); current = self.target.currentData(); self.target.clear()
        for fmt in (["png", "jpeg"] if value == "render" else ["pdf"]): self.target.addItem(fmt.upper(), fmt)
        idx = self.target.findData(current)
        if idx >= 0: self.target.setCurrentIndex(idx)
        self.notice.setText("图片按列表顺序合并为一个 PDF，每张图片占一页。多帧图片仅取第一帧，透明区域将填充白色。" if value == "images_to_pdf" else DESCRIPTIONS["pdf"][2])

    def enqueue(self, start):
        if not self.paths: self.window.show_message("添加文件", "请先添加需要处理的文件。"); return
        if not self.output.text().strip(): self.window.show_message("输出目录", "请选择输出文件夹。"); return
        target = self.target.currentData()
        if not target: self.window.show_message("目标格式", "所选文档没有共同的输出格式，请按文档类型分别添加。"); return
        if any(not self.accepts(path) for path in self.paths):
            self.window.show_message("输入类型不符", "当前处理方式与文件类型不匹配，请移除不适用的文件。"); return
        native_text = self.category == "document" and target in {"html", "txt"} and all(path.suffix.lower() == ".txt" for path in self.paths)
        needed = ["ffmpeg", "ffprobe"] if self.category in {"video", "audio"} else ["libreoffice"] if self.category == "document" and not native_text else []
        unavailable = [name for name in needed if not self.window.tool_results.get(name) or not self.window.tool_results[name].available]
        if unavailable:
            self.window.show_message("转换工具尚未就绪", "需要 " + "、".join(unavailable) + "。请在设置中查看安装指引并检测路径。"); self.window.navigate("settings"); return
        confirmed = False
        if self.window.settings.overwrite == "overwrite":
            result = QMessageBox.question(self, "确认覆盖输出文件", "当前策略会替换输出目录中同名的转换结果。源文件始终受保护。确定继续？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if result != QMessageBox.StandardButton.Yes: return
            confirmed = True
        jobs = []
        operation = self.operation.currentData() if self.category == "pdf" else None
        groups = [list(self.paths)] if operation in {"merge", "images_to_pdf"} else [[p] for p in self.paths]
        for inputs in groups:
            params = {**self.params, **(self.overrides.get(str(inputs[0]), {}) if len(inputs) == 1 else {})}
            if operation: params["operation"] = operation
            if confirmed: params["overwrite_confirmed"] = True
            jobs.append(Job(self.category, inputs, target, Path(self.output.text().strip()), params))
        if self.category == "image":
            from mediaforge.converters.image import image_warnings
            self.setEnabled(False)
            def warnings():
                return sorted({message for job in jobs for message in image_warnings(job.inputs[0], job.target_format, job.params)})
            worker = Worker(warnings)
            self.preflight_jobs = (jobs, start)
            self.preflight_worker = worker
            worker.signals.result.connect(self.image_preflight_complete)
            worker.signals.error.connect(self.preflight_error)
            self.window.pool.start(worker)
            return
        self.submit_jobs(jobs, start)

    def preflight_error(self, error):
        self.preflight_worker = None; self.preflight_jobs = None
        self.setEnabled(True); self.window.show_error("读取图片特性失败：" + error)

    def image_preflight_complete(self, notices):
        jobs, start = self.preflight_jobs
        self.preflight_worker = None; self.preflight_jobs = None
        self.confirm_image_warnings(notices, jobs, start)

    def confirm_image_warnings(self, notices, jobs, start):
        self.setEnabled(True)
        if notices:
            answer = QMessageBox.question(self, "确认图片处理方式", "本批次转换需要注意：\n\n" + "\n".join("• " + notice for notice in notices) + "\n\n是否继续？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes: return
        self.submit_jobs(jobs, start)

    def submit_jobs(self, jobs, start):
        try:
            for job in jobs: self.window.manager.add(job)
            if start: self.window.manager.start()
        except Exception as exc: self.window.show_error(str(exc)); return
        self.paths.clear(); self.overrides.clear(); self.refresh_files(); self.queued.emit()
        self.window.navigate("tasks"); self.window.statusBar().showMessage(f"已添加 {len(jobs)} 个转换任务", 5000)
