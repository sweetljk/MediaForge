from pathlib import Path

FORMATS = {
    "video": ["mp4", "mkv", "mov", "avi", "webm", "m4v"],
    "audio": ["mp3", "wav", "flac", "aac", "m4a", "ogg", "opus", "aiff"],
    "image": ["png", "jpeg", "webp", "bmp", "tiff", "gif"],
    "document": ["pdf", "doc", "docx", "odt", "rtf", "txt", "html", "ppt", "pptx", "odp", "xls", "xlsx", "ods", "csv"],
    "pdf": ["pdf", "png", "jpeg"],
}
INPUTS = {
    "video": set(FORMATS["video"]) | {"ts", "mts", "m2ts", "wmv", "flv", "mpeg", "mpg", "vob", "3gp"},
    "audio": set(FORMATS["audio"]) | {"aif", "wma", "oga", "alac"},
    "image": set(FORMATS["image"]) | {"jpg", "jpe", "tif", "ico"},
    "document": set(FORMATS["document"]) - {"pdf"} | {"doc", "ppt", "xls", "csv", "htm"},
    "pdf": {"pdf"},
}


def classify_file(path: str | Path) -> str:
    suffix = Path(path).suffix.lower().lstrip(".")
    return next((category for category, formats in INPUTS.items() if suffix in formats), "unknown")


def converter_for(category: str, target: str):
    from mediaforge.core.errors import ConversionError
    if category not in FORMATS or target not in FORMATS[category]:
        raise ConversionError(f"不支持的转换目标：{category} → {target}")
    if category in {"video", "audio"}:
        from mediaforge.converters.media import convert
    elif category == "image":
        from mediaforge.converters.image import convert
    elif category == "document":
        from mediaforge.converters.document import convert
    else:
        from mediaforge.converters.pdf import convert
    return convert
