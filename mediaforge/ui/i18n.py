"""Central UI vocabulary; Qt tr() provides the future translation boundary."""
from PySide6.QtCore import QCoreApplication

NAV = [("home", "首页"), ("video", "视频转换"), ("audio", "音频转换"), ("image", "图片转换"), ("document", "文档转换"), ("pdf", "PDF 工具"), ("tasks", "转换任务"), ("history", "转换历史"), ("settings", "设置")]
STATUS = {"pending": "待处理", "running": "处理中", "completed": "已完成", "failed": "失败", "cancelled": "已取消", "skipped": "已跳过"}


def tr(text: str) -> str:
    return QCoreApplication.translate("MediaForge", text)
