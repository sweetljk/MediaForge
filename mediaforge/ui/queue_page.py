from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QProgressBar, QVBoxLayout, QWidget

from mediaforge.ui.i18n import STATUS
from mediaforge.ui.widgets import button, cell, label, table


def local_time(value):
    try: return datetime.fromisoformat(value).astimezone().strftime("%m-%d %H:%M")
    except (TypeError, ValueError): return "—"


class QueuePage(QWidget):
    def __init__(self, window, history=False):
        super().__init__(); self.window = window; self.history_mode = history; self.records = []
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(18)
        layout.addWidget(label("转换历史" if history else "转换任务", "title"))
        layout.addWidget(label("每次转换的结果与日志，保存在这台电脑。" if history else "查看真实处理进度，管理本次会话中的所有任务。", "muted"))
        actions = QHBoxLayout(); actions.setSpacing(8)
        if not history:
            self.start = button("开始队列", "play", True); self.start.clicked.connect(self.start_queue); actions.addWidget(self.start)
            self.cancel = button("取消任务", "close"); self.cancel.clicked.connect(self.cancel_selected); actions.addWidget(self.cancel)
            self.retry = button("重试", "refresh"); self.retry.clicked.connect(self.retry_selected); actions.addWidget(self.retry)
            self.remove = button("移除", "delete"); self.remove.clicked.connect(self.remove_selected); actions.addWidget(self.remove)
        else:
            refresh = button("刷新历史", "refresh"); refresh.clicked.connect(self.refresh); actions.addWidget(refresh)
        actions.addStretch()
        self.open_output = button("输出目录", "folder"); self.open_output.clicked.connect(self.open_selected_output); actions.addWidget(self.open_output)
        self.open_log = button("查看日志", "log"); self.open_log.clicked.connect(self.open_selected_log); actions.addWidget(self.open_log)
        layout.addLayout(actions)
        self.table = table(["任务 / 输入文件", "目标", "状态", "进度" if not history else "时间", "结果 / 用时"])
        self.table.setColumnWidth(1, 75); self.table.setColumnWidth(2, 85); self.table.setColumnWidth(3, 135); self.table.setColumnWidth(4, 185)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        self.table.cellDoubleClicked.connect(lambda *_: self.open_selected_output())
        layout.addWidget(self.table, 1)
        self.empty = label("暂无转换记录。选择一种格式，完成你的第一次转换。" if history else "队列是空的。添加文件后，转换任务会显示在这里。", "muted", True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter); self.empty.setContentsMargins(20, 30, 20, 30); layout.addWidget(self.empty)
        self.detail = label("选择一个任务，查看状态和输出信息。", "notice", True)
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); self.detail.setMinimumHeight(75); layout.addWidget(self.detail)
        self.summary = label("0 个任务", "muted"); layout.addWidget(self.summary)
        if not history: layout.addWidget(label("暂停未开放：当前转换引擎不提供可靠的跨平台暂停。可取消任务后重新开始。", "muted", True))
        self.selection_changed()

    def selected(self):
        rows = sorted({item.row() for item in self.table.selectedItems()})
        return [self.records[row] for row in rows if row < len(self.records)]

    def refresh(self):
        selected_ids = {r["id"] for r in self.selected()}
        try:
            self.records = self.window.history.load() if self.history_mode else [job.to_dict() for job in self.window.manager.jobs()]
        except Exception as exc:
            self.window.statusBar().showMessage(f"读取记录失败：{exc}", 6000); self.records = []
        self.table.setUpdatesEnabled(False); self.table.blockSignals(True); self.table.setRowCount(len(self.records))
        for row, record in enumerate(self.records):
            names = [Path(p).name for p in record["inputs"]]
            display = names[0] if names else "未命名任务"
            if len(names) > 1: display += f" 等 {len(names)} 个文件"
            self.table.setItem(row, 0, cell(display, "\n".join(record["inputs"])))
            self.table.setItem(row, 1, cell(record["target_format"].upper()))
            self.table.setItem(row, 2, cell(STATUS.get(record["status"], record["status"])))
            if self.history_mode:
                self.table.setItem(row, 3, cell(local_time(record.get("finished_at") or record.get("created_at"))))
            else:
                widget = QWidget(); vertical = QVBoxLayout(widget); vertical.setContentsMargins(10, 7, 10, 7); vertical.setSpacing(3)
                progress = record.get("progress"); status = record["status"]
                if progress is None and status == "running": caption = "处理中 · 百分比未知"
                elif status in {"failed", "cancelled", "skipped"}: caption = STATUS[status]
                else: caption = f"{float(progress or 0):.0f}%"
                small = label(caption, "muted"); small.setStyleSheet("font-size: 11px;"); vertical.addWidget(small)
                bar = QProgressBar(); bar.setTextVisible(False)
                if progress is None and status == "running": bar.setRange(0, 0)
                else: bar.setRange(0, 100); bar.setValue(round(progress or 0))
                vertical.addWidget(bar); self.table.setCellWidget(row, 3, widget)
            result = record.get("error") or record.get("message", "")
            if record.get("status") == "completed": result = f"{len(record.get('output_paths', []))} 个输出 · {record.get('elapsed', 0):.1f} 秒"
            self.table.setItem(row, 4, cell(result))
            if record["id"] in selected_ids: self.table.selectRow(row)
        self.table.blockSignals(False); self.table.setUpdatesEnabled(True)
        self.empty.setVisible(not self.records)
        done = sum(r["status"] == "completed" for r in self.records); failed = sum(r["status"] == "failed" for r in self.records); active = sum(r["status"] == "running" for r in self.records)
        self.summary.setText(f"{len(self.records)} 个任务  ·  处理中 {active}  ·  已完成 {done}  ·  失败 {failed}")
        self.selection_changed()

    def selection_changed(self):
        records = self.selected(); record = records[0] if records else None
        self.open_output.setEnabled(bool(record and record.get("output_paths")))
        self.open_log.setEnabled(bool(record and record.get("log_path") and Path(record["log_path"]).is_file()))
        if not self.history_mode:
            self.start.setEnabled(any(r["status"] == "pending" for r in self.records))
            self.cancel.setEnabled(any(r["status"] in {"pending", "running"} for r in records))
            self.retry.setEnabled(any(r["status"] in {"failed", "cancelled", "skipped"} for r in records))
            self.remove.setEnabled(bool(records) and all(r["status"] != "running" for r in records))
        if record:
            text = record.get("error") or record.get("message") or STATUS.get(record["status"], "")
            text += f"\n输出目录：{record['output_dir']}"
            if record.get("output_paths"): text += "\n输出文件：" + "、".join(Path(p).name for p in record["output_paths"][:6])
            self.detail.setText(text)
        else: self.detail.setText("选择一个任务，查看状态和输出信息。")

    def start_queue(self):
        try: self.window.manager.start()
        except Exception as exc: self.window.show_error(str(exc))

    def cancel_selected(self):
        for record in self.selected():
            if record["status"] in {"pending", "running"}: self.window.manager.cancel(record["id"])
        self.refresh()

    def retry_selected(self):
        try:
            for record in self.selected():
                if record["status"] in {"failed", "cancelled", "skipped"}: self.window.manager.retry(record["id"])
            self.window.manager.start()
        except Exception as exc: self.window.show_error(str(exc))
        self.refresh()

    def remove_selected(self):
        try:
            for record in self.selected(): self.window.manager.remove(record["id"])
        except Exception as exc: self.window.show_error(str(exc))
        self.refresh()

    def open_selected_output(self):
        for record in self.selected()[:1]:
            paths = record.get("output_paths", [])
            if paths: self.window.open_path(Path(paths[0]).parent)

    def open_selected_log(self):
        for record in self.selected()[:1]:
            if record.get("log_path"): self.window.open_path(Path(record["log_path"]))
