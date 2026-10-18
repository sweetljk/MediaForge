"""A conservative document-family matrix, backed by real LibreOffice filters."""
from __future__ import annotations

import html
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING
from zipfile import BadZipFile, ZipFile

from mediaforge.core.errors import ConversionError
from mediaforge.engines.libreoffice import FAMILIES, FILTERS, run_conversion

if TYPE_CHECKING:
    from mediaforge.core.models import Job
    from mediaforge.engines.base import ConversionContext

DOCUMENT_NOTICE = "Office 转换依赖 LibreOffice；仅支持同类文档互转或导出 PDF。字体、公式、图表与复杂排版可能变化，请检查结果。PDF 转可编辑 Word / OCR 暂未开放。"


class _HTMLResources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.external = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        resource = attributes.get("src") or attributes.get("background")
        if tag == "object":
            resource = attributes.get("data")
        if tag == "link" and attributes.get("rel", "").lower() == "stylesheet":
            resource = attributes.get("href")
        if resource and not resource.startswith(("data:", "#")):
            self.external = True


def validate_single_file_html(path: Path) -> None:
    """Reject outputs that would become broken when the job workspace is removed."""
    parser = _HTMLResources()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    if parser.external or any(p.is_file() and p != path for p in path.parent.iterdir()):
        raise ConversionError("此文档包含无法内嵌的 HTML 资源，当前不支持导出为独立 HTML；请选择 PDF 或 DOCX。")


def document_targets(input_suffix: str) -> list[str]:
    family = FAMILIES.get(input_suffix.lower().lstrip("."))
    return list(FILTERS.get(family, {}))


def validate_document(path: Path, target: str) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise ConversionError("转换引擎未生成有效输出。文件可能损坏、被密码保护，或该版本不支持此格式。")
    if target == "pdf":
        import pymupdf
        try:
            with pymupdf.open(path) as pdf:
                if pdf.page_count < 1:
                    raise ConversionError("输出 PDF 没有页面。")
        except (RuntimeError, ValueError) as exc:
            raise ConversionError("输出 PDF 无法读取。") from exc
    elif target in {"docx", "xlsx", "pptx", "odt", "ods", "odp"}:
        required = {"docx": "word/document.xml", "xlsx": "xl/workbook.xml", "pptx": "ppt/presentation.xml"}.get(target, "content.xml")
        try:
            with ZipFile(path) as archive:
                if required not in archive.namelist() or archive.testzip() is not None:
                    raise ConversionError("输出 Office 文档结构不完整。")
        except BadZipFile as exc:
            raise ConversionError("输出 Office 文档不是有效的压缩文档。") from exc
    elif target in {"doc", "xls", "ppt"}:
        with path.open("rb") as stream:
            if stream.read(8) != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
                raise ConversionError("输出文档的二进制格式标识不正确。")
    elif target == "rtf":
        with path.open("rb") as stream:
            if not stream.read(20).lstrip().startswith(b"{\\rtf"):
                raise ConversionError("输出不是有效的 RTF 文档。")


def convert(job: "Job", output: Path, context: "ConversionContext") -> list[Path]:
    if len(job.inputs) != 1:
        raise ConversionError("每个文档转换任务需要一个输入文件。")
    source = job.inputs[0]
    extension = source.suffix.lower().lstrip(".")
    family = FAMILIES.get(extension)
    target = job.target_format
    if family is None or target not in document_targets(extension):
        raise ConversionError(f"不支持 {extension.upper()} → {target.upper()}。仅支持同类文档转换及导出 PDF。")
    context.check_cancelled()
    output.parent.mkdir(parents=True, exist_ok=True)
    # This local path remains useful when LibreOffice is not installed.
    if extension == "txt" and target in {"txt", "html"}:
        try:
            text = source.read_text(encoding=job.params.get("txt_encoding", "utf-8-sig"))
        except (UnicodeError, LookupError) as exc:
            raise ConversionError("文本编码不匹配，请在参数中选择正确的输入字符编码（默认 UTF-8）。") from exc
        if target == "html":
            text = '<!doctype html>\n<html lang="zh-CN"><head><meta charset="utf-8"><title>' + html.escape(source.stem) + '</title></head><body><pre style="white-space:pre-wrap">' + html.escape(text) + '</pre></body></html>\n'
        output.write_text(text, encoding="utf-8")
        context.check_cancelled()
        if target == "html" or text:
            validate_document(output, target)
        context.progress(100, "文本已转换为 UTF-8 并验证")
        return [output]
    timeout = float(job.params.get("timeout", 180))
    if not 10 <= timeout <= 7200:
        raise ConversionError("文档转换超时范围为 10–7200 秒。")
    # An isolated profile prevents interference with an already running office instance.
    converted = run_conversion(context, source, output.parent / "office-export", output.parent / "office-profile", family, target, timeout)
    validate_document(converted, target)
    if target == "html":
        validate_single_file_html(converted)
    context.check_cancelled()
    converted.replace(output)
    context.progress(100, "文档已转换并验证")
    return [output]
