from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


def main(argv=None):
    args_list = list(sys.argv[1:] if argv is None else argv)
    # Frozen workers must not import Qt or initialize another GUI.
    if args_list and args_list[0] == "--worker":
        from mediaforge.worker import main as worker_main
        return worker_main(args_list[1:])
    parser = argparse.ArgumentParser(description="MediaForge 本地格式转换")
    parser.add_argument("--smoke-test", action="store_true", help="启动窗口并自动退出")
    parser.add_argument("--screenshot", type=Path, help="启动验证截图路径")
    parser.add_argument("--theme", choices=["dark", "light"])
    args = parser.parse_args(args_list)
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication
    from mediaforge.services.settings import Settings
    from mediaforge.ui.icons import app_icon
    from mediaforge.ui.theme import apply_theme
    from mediaforge.ui.window import MainWindow
    app = QApplication([sys.argv[0]])
    app.setApplicationName("MediaForge"); app.setOrganizationName("MediaForge"); app.setApplicationVersion("0.1.0"); app.setStyle("Fusion"); app.setWindowIcon(app_icon()); app.setFont(QFont("Microsoft YaHei UI" if os.name == "nt" else "Noto Sans CJK SC", 10))
    settings = Settings.load()
    if args.theme: settings.theme = args.theme
    apply_theme(app, settings.theme)
    window = MainWindow(settings); window.show()
    if args.smoke_test:
        def complete():
            if args.screenshot:
                args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                if not window.grab().save(str(args.screenshot)): print("Unable to save screenshot", file=sys.stderr)
            window.close()
        QTimer.singleShot(3500, complete)
    return app.exec()
