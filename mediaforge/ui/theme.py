from PySide6.QtGui import QColor, QPalette


def apply_theme(app, mode: str):
    dark = mode == "dark"
    c = dict(bg="#10191f", panel="#17232b", sidebar="#111c23", raised="#1e2d36", border="#2b3c46", text="#edf4f5", muted="#92a8b3", accent="#77e0bd", accent_text="#10271f", selection="#274c43") if dark else dict(bg="#f3f6f8", panel="#ffffff", sidebar="#eaf0f3", raised="#eaf0f3", border="#d5dfe5", text="#182b34", muted="#5f7582", accent="#0d8065", accent_text="#ffffff", selection="#d1eee4")
    palette = QPalette()
    for role, key in [(QPalette.ColorRole.Window, "bg"), (QPalette.ColorRole.WindowText, "text"), (QPalette.ColorRole.Base, "panel"), (QPalette.ColorRole.AlternateBase, "raised"), (QPalette.ColorRole.Text, "text"), (QPalette.ColorRole.Button, "raised"), (QPalette.ColorRole.ButtonText, "text"), (QPalette.ColorRole.Highlight, "selection"), (QPalette.ColorRole.HighlightedText, "text"), (QPalette.ColorRole.ToolTipBase, "panel"), (QPalette.ColorRole.ToolTipText, "text")]: palette.setColor(role, QColor(c[key]))
    app.setPalette(palette)
    app.setStyleSheet("""
    QWidget { color: %(text)s; font-family: 'Segoe UI', 'Microsoft YaHei UI', 'Noto Sans CJK SC'; font-size: 13px; }
    QMainWindow, QDialog, QWidget#main, QStackedWidget { background: %(bg)s; }
    QFrame#sidebar { background: %(sidebar)s; border-right: 1px solid %(border)s; }
    QFrame#card, QFrame#hero { background: %(panel)s; border: 1px solid %(border)s; border-radius: 14px; }
    QFrame#hero { border-left: 3px solid %(accent)s; }
    QLabel { background: transparent; }
    QLabel#brand { font-size: 22px; font-weight: 700; letter-spacing: -0.5px; }
    QLabel#title { font-size: 27px; font-weight: 650; }
    QLabel#section { font-size: 16px; font-weight: 600; }
    QLabel#muted { color: %(muted)s; }
    QLabel#eyebrow { color: %(accent)s; font-size: 11px; font-weight: 700; letter-spacing: 1.5px; }
    QLabel#notice { color: %(muted)s; background: %(raised)s; border: 1px solid %(border)s; border-radius: 9px; padding: 11px; }
    QLabel#status { color: %(accent)s; }
    QPushButton { background: %(raised)s; border: 1px solid %(border)s; border-radius: 8px; padding: 9px 14px; font-weight: 500; }
    QPushButton:hover { border-color: %(muted)s; }
    QPushButton:pressed { background: %(selection)s; }
    QPushButton:disabled { color: %(muted)s; background: %(panel)s; border-color: %(border)s; }
    QPushButton#primary { background: %(accent)s; color: %(accent_text)s; border: 0; font-weight: 650; padding: 10px 18px; }
    QPushButton#primary:hover { border: 2px solid %(text)s; padding: 8px 16px; }
    QPushButton#nav { background: transparent; border: 0; border-radius: 8px; text-align: left; padding: 11px 15px; color: %(muted)s; }
    QPushButton#nav:checked { background: %(selection)s; color: %(text)s; font-weight: 600; }
    QPushButton#nav:hover { background: %(raised)s; }
    QPushButton#entry { background: %(panel)s; border: 1px solid %(border)s; border-radius: 12px; text-align: left; padding: 17px; font-size: 16px; font-weight: 600; }
    QPushButton#entry:hover { border-color: %(accent)s; background: %(raised)s; }
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit { background: %(panel)s; border: 1px solid %(border)s; border-radius: 7px; padding: 7px 9px; min-height: 20px; selection-background-color: %(selection)s; }
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: %(accent)s; }
    QComboBox { padding-right: 24px; }
    QComboBox::drop-down { border: 0; width: 22px; }
    QComboBox QAbstractItemView { background: %(panel)s; selection-background-color: %(selection)s; }
    QTableWidget { background: %(panel)s; alternate-background-color: %(panel)s; border: 1px solid %(border)s; border-radius: 10px; gridline-color: %(border)s; selection-background-color: %(selection)s; outline: none; }
    QTableWidget::item { padding: 8px; border-bottom: 1px solid %(border)s; }
    QHeaderView::section { background: %(raised)s; border: 0; border-bottom: 1px solid %(border)s; color: %(muted)s; padding: 10px 8px; text-align: left; font-weight: 500; }
    QTableCornerButton::section { background: %(raised)s; border: 0; }
    QScrollArea { background: transparent; border: 0; }
    QScrollArea > QWidget > QWidget { background: transparent; }
    QScrollBar:vertical { width: 9px; background: transparent; margin: 0; }
    QScrollBar::handle:vertical { background: %(border)s; border-radius: 4px; min-height: 35px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar:horizontal { height: 9px; background: transparent; }
    QScrollBar::handle:horizontal { background: %(border)s; border-radius: 4px; min-width: 35px; }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
    QProgressBar { border: 0; background: %(raised)s; border-radius: 4px; min-height: 6px; max-height: 7px; text-align: center; }
    QProgressBar::chunk { background: %(accent)s; border-radius: 4px; }
    QCheckBox { spacing: 8px; padding: 5px 0; }
    QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid %(muted)s; border-radius: 4px; background: %(panel)s; }
    QCheckBox::indicator:checked { background: %(accent)s; border-color: %(accent)s; }
    QTabWidget::pane { border: 1px solid %(border)s; border-radius: 8px; }
    QTabBar::tab { background: %(raised)s; padding: 10px 18px; }
    QTabBar::tab:selected { background: %(selection)s; }
    QStatusBar { background: %(sidebar)s; color: %(muted)s; border-top: 1px solid %(border)s; }
    QToolTip { background: %(panel)s; color: %(text)s; border: 1px solid %(border)s; padding: 6px; }
    """ % c)
