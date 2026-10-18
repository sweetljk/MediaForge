from pathlib import Path

from PySide6.QtCore import QThreadPool, QTimer, Qt, QUrl, QSize
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QButtonGroup, QFrame, QHBoxLayout, QMainWindow, QMessageBox, QScrollArea, QStackedWidget, QVBoxLayout, QWidget

from mediaforge.core.formats import classify_file
from mediaforge.core.models import TERMINAL
from mediaforge.jobs.manager import JobManager
from mediaforge.services.history import HistoryStore
from mediaforge.services.settings import Settings
from mediaforge.services.tools import ToolRegistry
from mediaforge.ui.conversion_page import ConversionPage
from mediaforge.ui.home_page import HomePage
from mediaforge.ui.icons import app_icon, icon
from mediaforge.ui.i18n import NAV, tr
from mediaforge.ui.queue_page import QueuePage
from mediaforge.ui.settings_page import SettingsPage
from mediaforge.ui.theme import apply_theme
from mediaforge.ui.widgets import JobBridge, Worker, button, label


class MainWindow(QMainWindow):
    def __init__(self, settings=None):
        super().__init__(); self.settings = settings or Settings.load()
        self.setWindowTitle("MediaForge · 本地格式转换"); self.setWindowIcon(app_icon()); self.resize(1320, 920); self.setMinimumSize(1000, 700); self.setAcceptDrops(True)
        self.tools = ToolRegistry(self.settings); self.history = HistoryStore(self.settings); self.manager = JobManager(self.settings, self.tools)
        self.pool = QThreadPool(self); self.pool.setMaxThreadCount(3); self.tool_results = {}; self.encoders = set(); self.file_cache = {}; self.detecting = False
        self.bridge = JobBridge(self); self.bridge.changed.connect(self.job_changed); self.manager.subscribe(self.bridge.changed.emit)
        central = QWidget(); central.setObjectName("main"); self.setCentralWidget(central); frame = QHBoxLayout(central); frame.setContentsMargins(0, 0, 0, 0); frame.setSpacing(0)
        sidebar = QFrame(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(215); side = QVBoxLayout(sidebar); side.setContentsMargins(16, 26, 16, 18); side.setSpacing(8)
        brand_row = QHBoxLayout(); mark = label(""); mark.setPixmap(app_icon().pixmap(32, 32)); brand_row.addWidget(mark); brand_row.addWidget(label("MediaForge", "brand")); brand_row.addStretch(); side.addLayout(brand_row)
        subtitle = label("本地多媒体工作空间", "muted"); subtitle.setContentsMargins(3, 3, 0, 24); side.addWidget(subtitle)
        self.nav = {}; self.nav_group = QButtonGroup(self); self.nav_group.setExclusive(True)
        for index, (key, title) in enumerate(NAV):
            if key == "tasks": side.addSpacing(18); side.addWidget(label("  工作空间", "muted"))
            if key == "settings": side.addStretch(1)
            btn = button(tr(title), key); btn.setObjectName("nav"); btn.setCheckable(True); btn.setMinimumHeight(44); btn.setIconSize(QSize(21, 21)); btn.clicked.connect(lambda _, k=key: self.navigate(k)); self.nav_group.addButton(btn); self.nav[key] = btn; side.addWidget(btn)
        side.addSpacing(15); side.addWidget(label("●  本地处理 · 无文件上传", "status")); side.addWidget(label("VERSION 0.1.0", "muted")); frame.addWidget(sidebar)
        content = QWidget(); content_layout = QVBoxLayout(content); content_layout.setContentsMargins(28, 19, 28, 16); content_layout.setSpacing(17)
        top = QHBoxLayout(); self.breadcrumb = label("工作空间  /  首页", "muted"); top.addWidget(self.breadcrumb); top.addStretch(); self.engine_status = label("正在检测引擎…", "muted"); top.addWidget(self.engine_status)
        toggle = button("切换主题"); toggle.clicked.connect(self.toggle_theme); top.addWidget(toggle); content_layout.addLayout(top)
        self.stack = QStackedWidget(); content_layout.addWidget(self.stack, 1); frame.addWidget(content, 1)
        self.pages = {}; self.conversion_pages = {}
        home = HomePage(self); self.add_page("home", home)
        for category in ("video", "audio", "image", "document", "pdf"):
            page = ConversionPage(category, self); self.conversion_pages[category] = page; page.queued.connect(self.refresh_queue); self.add_page(category, page)
        self.add_page("tasks", QueuePage(self)); self.add_page("history", QueuePage(self, history=True)); self.add_page("settings", SettingsPage(self))
        self.footer = label("就绪  ·  选择文件开始转换", "muted"); self.statusBar().addWidget(self.footer, 1)
        self.statusBar().addPermanentWidget(label("源文件始终保留", "muted")); self.navigate("home"); home.refresh()
        QTimer.singleShot(0, self.detect_tools)

    def add_page(self, key, widget):
        # Scroll only when needed; keeps every control reachable at 100%–200% scaling.
        wrapper = QScrollArea(); wrapper.setWidgetResizable(True); wrapper.setFrameShape(QFrame.Shape.NoFrame); wrapper.setWidget(widget); wrapper.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.pages[key] = widget; self.stack.addWidget(wrapper)

    def navigate(self, key):
        keys = [k for k, _ in NAV]
        self.stack.setCurrentIndex(keys.index(key)); self.nav[key].setChecked(True); self.current_page = key; self.breadcrumb.setText("工作空间  /  " + dict(NAV)[key])
        if key in {"tasks", "history", "home"}: self.pages[key].refresh()

    def refresh_queue(self):
        self.pages["tasks"].refresh(); self.update_footer()

    def job_changed(self, job):
        self.pages["tasks"].refresh(); self.update_footer()
        if job.status in TERMINAL and self.current_page in {"home", "history"}: self.pages[self.current_page].refresh()

    def update_footer(self):
        jobs = self.manager.jobs(); running = sum(j.status == "running" for j in jobs); pending = sum(j.status == "pending" for j in jobs); completed = sum(j.status == "completed" for j in jobs); failed = sum(j.status == "failed" for j in jobs)
        self.footer.setText(f"处理中 {running}  ·  待处理 {pending}  ·  已完成 {completed}  ·  失败 {failed}" if jobs else "就绪  ·  选择文件开始转换")
        self.nav["tasks"].setText(f"转换任务  {running + pending}" if running + pending else "转换任务")

    def detect_tools(self):
        if self.detecting: return
        if self.manager.active_count:
            self.statusBar().showMessage("工具正在用于转换，请在任务结束后重新检测。", 5000); return
        self.detecting = True; self.engine_status.setText("正在检测引擎…"); self.pages["settings"].detect.setEnabled(False)
        def detect():
            results = self.tools.detect_all(); encoders = set()
            if results.get("ffmpeg") and results["ffmpeg"].available:
                try: encoders = self.tools.encoders()
                except Exception: pass
            return results, encoders
        worker = Worker(detect); self.detect_worker = worker; worker.signals.result.connect(self.tools_detected); worker.signals.error.connect(self.tools_failed); self.pool.start(worker)

    def tools_detected(self, value):
        self.detect_worker = None
        self.tool_results, self.encoders = value; self.detecting = False; self.pages["settings"].detect.setEnabled(True)
        count = sum(info.available for name, info in self.tool_results.items() if name != "imagemagick")
        self.engine_status.setText(f"{count}/3 外部工具就绪  ·  图片 / PDF 可用")
        self.pages["settings"].update_tools(self.tool_results); self.pages["home"].update_tools(self.tool_results)

    def tools_failed(self, error):
        self.detect_worker = None
        self.detecting = False; self.pages["settings"].detect.setEnabled(True); self.engine_status.setText("工具检测失败，可在设置中重试"); self.statusBar().showMessage(error, 10000)

    def toggle_theme(self):
        self.settings.theme = "light" if self.settings.theme == "dark" else "dark"
        apply_theme(QApplication.instance(), self.settings.theme); self.pages["settings"].theme.setCurrentIndex(self.pages["settings"].theme.findData(self.settings.theme))
        try: self.settings.save()
        except OSError as exc: self.show_error(f"主题已切换，但无法保存偏好：{exc}")

    def show_error(self, text):
        QMessageBox.warning(self, "无法完成操作", text)

    def show_message(self, title, text):
        QMessageBox.information(self, title, text)

    def open_path(self, path):
        path = Path(path)
        if not path.exists(): self.show_message("路径不存在", "文件可能已被移动或删除：\n" + str(path)); return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))): self.show_error("无法打开路径：" + str(path))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()): event.acceptProposedAction()

    def dropEvent(self, event):
        paths = []
        for url in event.mimeData().urls():
            if not url.isLocalFile(): continue
            path = Path(url.toLocalFile())
            try: paths.extend(p for p in path.iterdir() if p.is_file()) if path.is_dir() else paths.append(path)
            except OSError: pass
        if self.current_page in self.conversion_pages: self.conversion_pages[self.current_page].add_files(paths)
        else:
            groups = {}
            for path in paths:
                category = classify_file(path)
                if category in self.conversion_pages: groups.setdefault(category, []).append(path)
            for category, inputs in groups.items(): self.conversion_pages[category].add_files(inputs)
            if groups: self.navigate(next(iter(groups)))
            else: self.show_message("没有可添加的文件", "请拖入支持的视频、音频、图片、文档或 PDF 文件。")
        event.acceptProposedAction()

    def closeEvent(self, event):
        if self.manager.active_count:
            answer = QMessageBox.question(self, "仍有任务正在处理", "退出会取消正在处理的任务，并清理未完成的输出。确定退出？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes: event.ignore(); return
        self.manager.shutdown(wait=False); event.accept()
