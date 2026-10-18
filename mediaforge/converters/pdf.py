"""Real PDF page operations using pypdf and PyMuPDF, with bounded rendering."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
from typing import TYPE_CHECKING

import pymupdf
from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter
from pypdf.errors import DependencyError, PdfReadError

from mediaforge.core.errors import ConversionError

if TYPE_CHECKING:
    from mediaforge.core.models import Job
    from mediaforge.engines.base import ConversionContext

MAX_PAGES = 10_000
MAX_RENDER_PIXELS = 40_000_000


def parse_pages(spec: str, total: int) -> list[int]:
    """Parse one-based inclusive ranges into ordered unique zero-based pages."""
    if not 1 <= total <= MAX_PAGES:
        raise ConversionError(f"PDF 页数须为 1–{MAX_PAGES}。")
    if not str(spec or "").strip():
        return list(range(total))
    pages = []
    seen = set()
    for token in str(spec).replace("，", ",").split(","):
        match = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+)\s*)?", token)
        if not match:
            raise ConversionError("页码格式不正确，请使用例如 1-3,5,8-10。")
        start, end = int(match[1]), int(match[2] or match[1])
        if not 1 <= start <= end <= total:
            raise ConversionError(f"页码超出范围或顺序不正确：{token.strip()}（共 {total} 页）。")
        for index in range(start - 1, end):
            if index not in seen:
                pages.append(index)
                seen.add(index)
    return pages


def pdf_info(path: Path) -> dict:
    try:
        with pymupdf.open(path) as pdf:
            if pdf.needs_pass:
                raise ConversionError("PDF 已加密，请先使用原软件解密后再处理。")
            return {"pages": pdf.page_count, "page_sizes": [(round(p.rect.width, 2), round(p.rect.height, 2)) for p in pdf]}
    except (RuntimeError, ValueError) as exc:
        raise ConversionError(f"无法读取 PDF：{exc}") from exc


def _reader(path: Path) -> PdfReader:
    try:
        # Detect password protection before pypdf attempts an optional AES backend.
        with pymupdf.open(path) as probe:
            if probe.needs_pass:
                raise ConversionError("PDF 已加密，请先使用原软件解密后再处理。")
        reader = PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ConversionError("PDF 已加密，请先使用原软件解密后再处理。")
        if not 1 <= len(reader.pages) <= MAX_PAGES:
            raise ConversionError(f"PDF 必须包含 1–{MAX_PAGES} 页。")
        return reader
    except DependencyError as exc:
        raise ConversionError("此 PDF 使用加密算法，请先使用原软件解密后再处理。") from exc
    except (PdfReadError, ValueError, OSError, RuntimeError) as exc:
        raise ConversionError(f"无法读取 PDF，文件可能已损坏：{exc}") from exc


def _validate(path: Path, expected_pages: int) -> None:
    if not path.exists() or path.stat().st_size == 0:
        raise ConversionError("未生成有效 PDF 输出。")
    with pymupdf.open(path) as check:
        if check.page_count != expected_pages:
            raise ConversionError("PDF 输出页数与请求不符。")


def _write_pages(reader: PdfReader, indices: list[int], output: Path, context: "ConversionContext") -> None:
    writer = PdfWriter()
    try:
        for index in indices:
            context.check_cancelled()
            writer.add_page(reader.pages[index])
        if reader.metadata:
            writer.add_metadata({key: str(value) for key, value in reader.metadata.items() if value is not None})
        with output.open("wb") as stream:
            writer.write(stream)
    finally:
        writer.close()
    _validate(output, len(indices))


def _render(job: "Job", output: Path, context: "ConversionContext") -> list[Path]:
    target = job.target_format
    if target not in {"png", "jpg", "jpeg"}:
        raise ConversionError("PDF 页面图片格式仅支持 PNG 或 JPEG。")
    dpi = int(job.params.get("dpi", 150))
    if not 36 <= dpi <= 600:
        raise ConversionError("PDF 渲染分辨率范围为 36–600 DPI。")
    paths = []
    with pymupdf.open(job.inputs[0]) as pdf:
        if pdf.needs_pass:
            raise ConversionError("PDF 已加密，请先解密。")
        indices = parse_pages(job.params.get("pages", ""), pdf.page_count)
        for number, index in enumerate(indices, 1):
            context.check_cancelled()
            page = pdf[index]
            if page.rect.width * page.rect.height * (dpi / 72) ** 2 > MAX_RENDER_PIXELS:
                raise ConversionError("页面渲染将超过 4000 万像素，请降低 DPI。")
            destination = output.with_name(f"{output.stem}_p{index + 1:04d}.{target}")
            pixmap = page.get_pixmap(dpi=dpi, alpha=False, colorspace=pymupdf.csRGB)
            pixmap.save(destination)
            with Image.open(destination) as check:
                check.verify()
            paths.append(destination)
            context.progress(number / len(indices) * 100, f"已渲染 {number}/{len(indices)} 页")
    return paths


def _images_to_pdf(job: "Job", output: Path, context: "ConversionContext") -> list[Path]:
    if len(job.inputs) > MAX_PAGES:
        raise ConversionError("一次最多处理 10000 张图片。")
    dpi = int(job.params.get("dpi", 150))
    if not 36 <= dpi <= 600:
        raise ConversionError("图片页面分辨率范围为 36–600 DPI。")
    with pymupdf.open() as document:
        for number, source in enumerate(job.inputs, 1):
            context.check_cancelled()
            with Image.open(source) as image:
                if image.width * image.height > MAX_RENDER_PIXELS:
                    raise ConversionError("图片超过 4000 万像素的 PDF 处理限制。")
                frame = ImageOps.exif_transpose(image).convert("RGB")
                # PDF pages have an opaque white background.
                if "A" in image.getbands() or "transparency" in image.info:
                    rgba = ImageOps.exif_transpose(image).convert("RGBA")
                    frame = Image.new("RGB", rgba.size, "white")
                    frame.paste(rgba, mask=rgba.getchannel("A"))
                data = BytesIO()
                frame.save(data, format="PNG")
                page = document.new_page(width=frame.width / dpi * 72, height=frame.height / dpi * 72)
                page.insert_image(page.rect, stream=data.getvalue())
                frame.close()
            context.progress(number / (len(job.inputs) + 1) * 100, f"已添加图片 {number}/{len(job.inputs)}（多帧图片仅取第一帧）")
        context.check_cancelled()
        document.save(output, garbage=3, deflate=True)
    _validate(output, len(job.inputs))
    return [output]


def convert(job: "Job", output: Path, context: "ConversionContext") -> list[Path]:
    operation = job.params.get("operation", "extract")
    if operation not in {"merge", "split", "extract", "render", "images_to_pdf"}:
        raise ConversionError(f"未知 PDF 操作：{operation}")
    if not job.inputs:
        raise ConversionError("请先添加输入文件。")
    if operation not in {"merge", "images_to_pdf"} and len(job.inputs) != 1:
        raise ConversionError("此 PDF 操作每个任务只支持一个 PDF。")
    if operation != "render" and job.target_format != "pdf":
        raise ConversionError("此 PDF 操作的目标格式必须为 PDF。")
    context.check_cancelled()
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        if operation == "render":
            outputs = _render(job, output, context)
        elif operation == "images_to_pdf":
            outputs = _images_to_pdf(job, output, context)
        elif operation == "merge":
            writer = PdfWriter()
            total = 0
            try:
                for number, source in enumerate(job.inputs, 1):
                    context.check_cancelled()
                    reader = _reader(source)
                    total += len(reader.pages)
                    if total > MAX_PAGES:
                        raise ConversionError("合并后的 PDF 超过 10000 页限制。")
                    for page in reader.pages:
                        context.check_cancelled()
                        writer.add_page(page)
                    context.progress(number / (len(job.inputs) + 1) * 100, f"已合并文件 {number}/{len(job.inputs)}")
                with output.open("wb") as stream:
                    writer.write(stream)
            finally:
                writer.close()
            _validate(output, total)
            outputs = [output]
        else:
            reader = _reader(job.inputs[0])
            indices = parse_pages(job.params.get("pages", ""), len(reader.pages))
            if operation == "split":
                outputs = []
                for number, index in enumerate(indices, 1):
                    path = output.with_name(f"{output.stem}_p{index + 1:04d}.pdf")
                    _write_pages(reader, [index], path, context)
                    outputs.append(path)
                    context.progress(number / len(indices) * 100, f"已拆分 {number}/{len(indices)} 页")
            else:
                _write_pages(reader, indices, output, context)
                outputs = [output]
        context.check_cancelled()
        context.progress(100, "PDF 处理完成并通过输出验证")
        return outputs
    except (RuntimeError, ValueError, OSError, PdfReadError) as exc:
        raise ConversionError(f"PDF 处理失败：{exc}") from exc
