from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def icon(name: str, color: str = "#8da7b1", size: int = 24) -> QIcon:
    """Small coherent line icon set, drawn at device-independent coordinates."""
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 24, size / 24)
    p.setPen(QPen(QColor(color), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if name == "video":
        p.drawRoundedRect(QRectF(3, 5, 18, 14), 3, 3)
        path = QPainterPath(); path.moveTo(10, 9); path.lineTo(15, 12); path.lineTo(10, 15); path.closeSubpath(); p.drawPath(path)
    elif name == "audio":
        p.drawLine(9, 16, 9, 5); p.drawLine(9, 5, 19, 3); p.drawLine(19, 3, 19, 14)
        p.drawEllipse(QRectF(3, 15, 6, 5)); p.drawEllipse(QRectF(13, 13, 6, 5))
    elif name == "image":
        p.drawRoundedRect(QRectF(3, 3, 18, 18), 3, 3); p.drawEllipse(QRectF(7, 7, 3, 3))
        path = QPainterPath(); path.moveTo(4, 17); path.lineTo(10, 12); path.lineTo(14, 16); path.lineTo(17, 12); path.lineTo(21, 16); p.drawPath(path)
    elif name in {"document", "pdf", "log"}:
        path = QPainterPath(); path.moveTo(5, 3); path.lineTo(14, 3); path.lineTo(19, 8); path.lineTo(19, 21); path.lineTo(5, 21); path.closeSubpath(); p.drawPath(path)
        p.drawLine(14, 3, 14, 8); p.drawLine(14, 8, 19, 8); p.drawLine(8, 12, 16, 12); p.drawLine(8, 16, 14, 16)
    elif name == "home":
        for x, y in [(3, 3), (14, 3), (3, 14), (14, 14)]: p.drawRoundedRect(QRectF(x, y, 7, 7), 2, 2)
    elif name == "tasks":
        for y in [5, 12, 19]:
            p.drawLine(10, y, 21, y); p.drawEllipse(QRectF(3, y - 1.5, 3, 3))
    elif name == "history":
        p.drawArc(QRectF(4, 3, 17, 17), -45 * 16, 290 * 16); p.drawLine(12, 6, 12, 12); p.drawLine(12, 12, 16, 14); p.drawLine(2, 3, 2, 8); p.drawLine(2, 8, 7, 8)
    elif name == "settings":
        for x, y in [(5, 8), (12, 16), (19, 10)]:
            p.drawLine(x, 3, x, y - 3); p.drawLine(x, y + 3, x, 21); p.drawEllipse(QRectF(x - 2.5, y - 2.5, 5, 5))
    elif name == "folder":
        path = QPainterPath(); path.moveTo(3, 7); path.lineTo(3, 5); path.lineTo(10, 5); path.lineTo(12, 7); path.lineTo(21, 7); path.lineTo(21, 20); path.lineTo(3, 20); path.closeSubpath(); p.drawPath(path)
    elif name == "plus":
        p.drawLine(12, 5, 12, 19); p.drawLine(5, 12, 19, 12)
    elif name == "play":
        path = QPainterPath(); path.moveTo(7, 4); path.lineTo(20, 12); path.lineTo(7, 20); path.closeSubpath(); p.drawPath(path)
    elif name in {"close", "delete"}:
        p.drawLine(6, 6, 18, 18); p.drawLine(6, 18, 18, 6)
    elif name == "check":
        p.drawLine(4, 12, 10, 18); p.drawLine(10, 18, 20, 6)
    elif name == "refresh":
        p.drawArc(QRectF(4, 4, 16, 16), 40 * 16, 300 * 16); p.drawLine(20, 3, 20, 9); p.drawLine(20, 9, 14, 9)
    elif name == "arrow":
        p.drawLine(4, 12, 20, 12); p.drawLine(15, 7, 20, 12); p.drawLine(15, 17, 20, 12)
    else:
        p.drawEllipse(QRectF(4, 4, 16, 16)); p.drawLine(12, 10, 12, 17); p.drawPoint(12, 7)
    p.end()
    return QIcon(pm)


def app_icon() -> QIcon:
    pm = QPixmap(128, 128); pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor("#65dfbc")); p.drawRoundedRect(QRectF(2, 2, 124, 124), 30, 30)
    p.setBrush(QColor("#102824"))
    path = QPainterPath(); path.moveTo(29, 92); path.lineTo(29, 36); path.lineTo(44, 36); path.lineTo(64, 62); path.lineTo(84, 36); path.lineTo(99, 36); path.lineTo(99, 92); path.lineTo(82, 92); path.lineTo(82, 64); path.lineTo(64, 86); path.lineTo(46, 64); path.lineTo(46, 92); path.closeSubpath(); p.drawPath(path); p.end()
    return QIcon(pm)
