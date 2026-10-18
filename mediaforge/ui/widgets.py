from PySide6.QtCore import QObject, QRunnable, Signal, Slot, Qt
from PySide6.QtWidgets import QAbstractItemView, QFrame, QHeaderView, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout
from mediaforge.ui.icons import icon


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)


class Worker(QRunnable):
    def __init__(self, function):
        super().__init__(); self.function = function; self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try: self.signals.result.emit(self.function())
        except Exception as exc: self.signals.error.emit(str(exc))


class JobBridge(QObject):
    changed = Signal(object)


def label(text, role=None, wrap=False):
    w = QLabel(text)
    if role: w.setObjectName(role)
    w.setWordWrap(wrap)
    return w


def button(text, icon_name=None, primary=False):
    w = QPushButton(text)
    if icon_name: w.setIcon(icon(icon_name, "#17362b" if primary else "#91a7b3", 19))
    if primary: w.setObjectName("primary")
    w.setCursor(Qt.CursorShape.PointingHandCursor)
    return w


def card():
    frame = QFrame(); frame.setObjectName("card")
    layout = QVBoxLayout(frame); layout.setContentsMargins(20, 18, 20, 18); layout.setSpacing(12)
    return frame, layout


def table(headers):
    w = QTableWidget(0, len(headers)); w.setHorizontalHeaderLabels(headers)
    w.setShowGrid(False); w.verticalHeader().setVisible(False)
    w.verticalHeader().setDefaultSectionSize(52)
    w.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    w.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    w.setAlternatingRowColors(False)
    w.horizontalHeader().setStretchLastSection(True)
    w.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    w.setMinimumHeight(160)
    return w


def cell(value, tooltip=""):
    w = QTableWidgetItem(str(value)); w.setToolTip(tooltip or str(value)); return w


def size_text(size):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024: return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024
    return f"{size:.1f} PB"
