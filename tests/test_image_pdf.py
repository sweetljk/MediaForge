from pathlib import Path
from threading import Event

import pymupdf
import pytest
from PIL import Image
from pypdf import PdfReader

from mediaforge.converters import image as image_converter
from mediaforge.converters import pdf as pdf_converter
from mediaforge.core.errors import CancelledError, ConversionError
from mediaforge.core.models import Job
from mediaforge.engines.base import ConversionContext


def make_context(tmp_path, progress=None):
    return ConversionContext(None, Event(), tmp_path / "conversion.log", progress or (lambda value, message="": None))


def sample_pdf(path: Path, pages=3):
    with pymupdf.open() as document:
        for number in range(pages):
            page = document.new_page(width=200, height=300)
            page.insert_text((20, 40), f"Page {number + 1}")
        document.save(path)
    return path


@pytest.mark.integration
def test_image_real_transparency_resize_unicode(tmp_path):
    source = tmp_path / "中文 空格.png"
    Image.new("RGBA", (80, 40), (255, 0, 0, 0)).save(source)
    output = tmp_path / "work" / "结果.jpg"
    job = Job("image", [source], "jpg", tmp_path, {"width": 20, "height": 20, "background": "#00ff00"})
    progress = []
    paths = image_converter.convert(job, output, make_context(tmp_path, lambda value, message: progress.append(value)))
    assert paths == [output]
    with Image.open(output) as image:
        assert image.format == "JPEG"
        assert image.size == (20, 10)
        red, green, blue = image.getpixel((0, 0))
        assert green > 245 and red < 10 and blue < 10
    assert source.is_file()
    assert progress[-1] == 100 and progress[0] > 0


@pytest.mark.integration
@pytest.mark.parametrize("target", ["png", "jpeg", "webp", "bmp", "tiff", "gif"])
def test_all_image_formats_real(tmp_path, target):
    source = tmp_path / "source.png"
    Image.new("RGB", (23, 17), "coral").save(source)
    output = tmp_path / f"result.{target}"
    image_converter.convert(Job("image", [source], target, tmp_path), output, make_context(tmp_path))
    with Image.open(output) as result:
        result.load()
        assert result.size == (23, 17)


@pytest.mark.integration
def test_animation_all_or_first_and_incompatible_rejected(tmp_path):
    source = tmp_path / "animated.gif"
    Image.new("RGB", (16, 16), "red").save(source, save_all=True,
        append_images=[Image.new("RGB", (16, 16), "blue")], duration=[80, 120], loop=0)
    job = Job("image", [source], "webp", tmp_path, {"animation": "all"})
    output = tmp_path / "all.webp"
    image_converter.convert(job, output, make_context(tmp_path))
    with Image.open(output) as result:
        assert result.n_frames == 2
    job.target_format = "jpeg"
    with pytest.raises(ConversionError, match="多帧"):
        image_converter.convert(job, tmp_path / "all.jpg", make_context(tmp_path))
    job.params["animation"] = "first"
    image_converter.convert(job, tmp_path / "first.jpg", make_context(tmp_path))
    assert any("第一帧" in message for message in image_converter.image_warnings(source, "jpg"))


def test_exif_orientation_applied_and_metadata_option(tmp_path):
    source = tmp_path / "rotated.jpg"
    original = Image.new("RGB", (30, 10), "red")
    exif = Image.Exif()
    exif[274] = 6
    exif[315] = "MediaForge test"
    original.save(source, exif=exif)
    output = tmp_path / "corrected.png"
    job = Job("image", [source], "png", tmp_path)
    image_converter.convert(job, output, make_context(tmp_path))
    with Image.open(output) as result:
        assert result.size == (10, 30)
        assert result.getexif().get(274) is None
        assert result.getexif()[315] == "MediaForge test"
    job.params["preserve_metadata"] = False
    image_converter.convert(job, output, make_context(tmp_path))
    with Image.open(output) as result:
        assert not result.getexif()


def test_image_cancelled_before_output_and_corrupt_input(tmp_path):
    source = tmp_path / "bad.png"
    source.write_text("this is not an image")
    context = make_context(tmp_path)
    context.cancel.set()
    job = Job("image", [source], "png", tmp_path)
    output = tmp_path / "output.png"
    with pytest.raises(CancelledError):
        image_converter.convert(job, output, context)
    assert not output.exists()
    context.cancel.clear()
    with pytest.raises(ConversionError, match="图片转换失败"):
        image_converter.convert(job, output, context)


@pytest.mark.parametrize("spec,expected", [("", [0, 1, 2, 3, 4]), ("1-3,5", [0, 1, 2, 4]), ("3,1-3", [2, 0, 1]), ("1，5", [0, 4])])
def test_parse_pages(spec, expected):
    assert pdf_converter.parse_pages(spec, 5) == expected


@pytest.mark.parametrize("spec", ["0", "6", "3-1", "1,,2", "abc", "1-10000000000"])
def test_invalid_pdf_pages(spec):
    with pytest.raises(ConversionError):
        pdf_converter.parse_pages(spec, 5)


@pytest.mark.integration
def test_pdf_merge_extract_split_real(tmp_path):
    first = sample_pdf(tmp_path / "中文 文档.pdf", 3)
    second = sample_pdf(tmp_path / "second.pdf", 2)
    merged = tmp_path / "merge.pdf"
    job = Job("pdf", [first, second], "pdf", tmp_path, {"operation": "merge"})
    pdf_converter.convert(job, merged, make_context(tmp_path))
    assert len(PdfReader(merged).pages) == 5
    job = Job("pdf", [merged], "pdf", tmp_path, {"operation": "extract", "pages": "5,1-2"})
    extracted = tmp_path / "extract.pdf"
    pdf_converter.convert(job, extracted, make_context(tmp_path))
    result = PdfReader(extracted)
    assert len(result.pages) == 3
    assert "Page 2" in result.pages[0].extract_text()
    job.params["operation"] = "split"
    paths = pdf_converter.convert(job, tmp_path / "split.pdf", make_context(tmp_path))
    assert len(paths) == 3
    assert all(len(PdfReader(path).pages) == 1 for path in paths)
    assert pdf_converter.pdf_info(first)["pages"] == 3


@pytest.mark.integration
def test_pdf_render_and_images_to_pdf_real(tmp_path):
    source = sample_pdf(tmp_path / "source.pdf", 2)
    job = Job("pdf", [source], "png", tmp_path, {"operation": "render", "dpi": 72})
    paths = pdf_converter.convert(job, tmp_path / "page.png", make_context(tmp_path))
    assert len(paths) == 2
    with Image.open(paths[0]) as rendered:
        assert rendered.size == (200, 300)
    merged = tmp_path / "images.pdf"
    job = Job("pdf", paths, "pdf", tmp_path, {"operation": "images_to_pdf", "dpi": 72})
    pdf_converter.convert(job, merged, make_context(tmp_path))
    assert len(PdfReader(merged).pages) == 2
    assert tuple(PdfReader(merged).pages[0].mediabox)[2:] == (200, 300)


def test_pdf_cancel_between_pages(tmp_path):
    source = sample_pdf(tmp_path / "source.pdf", 3)
    context = make_context(tmp_path)
    context.progress = lambda value, message: context.cancel.set()
    job = Job("pdf", [source], "pdf", tmp_path, {"operation": "split"})
    with pytest.raises(CancelledError):
        pdf_converter.convert(job, tmp_path / "cancel.pdf", context)
    assert (tmp_path / "cancel_p0001.pdf").exists()
    assert not (tmp_path / "cancel_p0002.pdf").exists()
    assert source.exists()


def test_pdf_rejects_password_and_unsafe_render(tmp_path):
    source = tmp_path / "locked.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page()
        pdf.save(source, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")
    job = Job("pdf", [source], "pdf", tmp_path, {"operation": "extract"})
    with pytest.raises(ConversionError, match="加密"):
        pdf_converter.convert(job, tmp_path / "result.pdf", make_context(tmp_path))
    job = Job("pdf", [sample_pdf(tmp_path / "normal.pdf")], "png", tmp_path, {"operation": "render", "dpi": 9999})
    with pytest.raises(ConversionError, match="DPI"):
        pdf_converter.convert(job, tmp_path / "render.png", make_context(tmp_path))
