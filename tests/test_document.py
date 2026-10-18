from pathlib import Path
from threading import Event

import pytest

from mediaforge.converters.document import convert, document_targets, validate_document, validate_single_file_html
from mediaforge.core.errors import CancelledError, ConversionError
from mediaforge.core.models import Job
from mediaforge.engines.base import ConversionContext
from mediaforge.engines.libreoffice import build_command
from mediaforge.services.settings import Settings
from mediaforge.services.tools import ToolRegistry


class NoOffice:
    def require(self, name):
        raise ConversionError("需要 LibreOffice，请安装或指定路径。")


def context(tmp_path, tools=None):
    return ConversionContext(tools or NoOffice(), Event(), tmp_path / "doc.log", lambda value, message="": None)


def test_document_family_matrix():
    assert "pdf" in document_targets(".DOCX")
    assert "docx" in document_targets("rtf")
    assert "pptx" not in document_targets("docx")
    assert "xlsx" in document_targets("ods")
    assert "pptx" in document_targets("ppt")
    assert document_targets("pdf") == []


def test_office_command_is_argument_array_and_isolated_profile(tmp_path):
    source = tmp_path / "中文 文件 & test.docx"
    args = build_command("C:/Program Files/LibreOffice/program/soffice.com", source, tmp_path / "export", tmp_path / "独立 profile", "writer", "pdf")
    assert args[-1] == str(source)
    assert "pdf:writer_pdf_Export" in args
    assert "--headless" in args
    assert args[1].startswith("-env:UserInstallation=file:")
    assert "%20" in args[1]
    html_args = build_command("soffice", source, tmp_path / "export", tmp_path / "profile", "writer", "html")
    assert "html:HTML (StarWriter):EmbedImages" in html_args


def test_html_external_resource_rejected(tmp_path):
    output = tmp_path / "converted.html"
    output.write_text('<html><img src="missing.png"></html>')
    with pytest.raises(ConversionError, match="HTML"):
        validate_single_file_html(output)
    output.write_text('<html><img src="data:image/png;base64,TEST"></html>')
    validate_single_file_html(output)


@pytest.mark.integration
def test_local_txt_to_html_real_without_office(tmp_path):
    source = tmp_path / "中文 & 空格.txt"
    source.write_text("你好，MediaForge！\n<script>never execute</script>", encoding="utf-8-sig")
    output = tmp_path / "work" / "result.html"
    convert(Job("document", [source], "html", tmp_path), output, context(tmp_path))
    result = output.read_text(encoding="utf-8")
    assert "你好，MediaForge！" in result
    assert "&lt;script&gt;never execute&lt;/script&gt;" in result
    assert '<meta charset="utf-8">' in result
    assert source.exists()


def test_document_rejects_invalid_matrix_missing_tool_and_bad_encoding(tmp_path):
    source = tmp_path / "source.docx"
    source.write_bytes(b"invalid document")
    with pytest.raises(ConversionError, match="不支持"):
        convert(Job("document", [source], "xlsx", tmp_path), tmp_path / "out.xlsx", context(tmp_path))
    with pytest.raises(ConversionError, match="LibreOffice"):
        convert(Job("document", [source], "pdf", tmp_path), tmp_path / "out.pdf", context(tmp_path))
    source = tmp_path / "gbk.txt"
    source.write_bytes("中文".encode("gbk"))
    with pytest.raises(ConversionError, match="编码"):
        convert(Job("document", [source], "html", tmp_path), tmp_path / "out.html", context(tmp_path))
    convert(Job("document", [source], "html", tmp_path, {"txt_encoding": "gbk"}), tmp_path / "out.html", context(tmp_path))


def test_document_cancel_and_validation(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("text")
    ctx = context(tmp_path)
    ctx.cancel.set()
    with pytest.raises(CancelledError):
        convert(Job("document", [source], "html", tmp_path), tmp_path / "out.html", ctx)
    bad = tmp_path / "bad.docx"
    bad.write_text("renaming is not conversion")
    with pytest.raises(ConversionError, match="Office"):
        validate_document(bad, "docx")


@pytest.mark.integration
def test_installed_libreoffice_real_txt_to_pdf(tmp_path):
    tools = ToolRegistry(Settings())
    if not tools.get("libreoffice").available:
        pytest.skip("LibreOffice is not installed; local TXT→HTML is tested separately")
    source = tmp_path / "中文 sample.txt"
    source.write_text("MediaForge real document conversion\nHello 123", encoding="utf-8")
    output = tmp_path / "work" / "document.pdf"
    convert(Job("document", [source], "pdf", tmp_path), output, context(tmp_path, tools))
    import pymupdf
    with pymupdf.open(output) as pdf:
        assert pdf.page_count >= 1
        assert "MediaForge" in "".join(page.get_text() for page in pdf)


@pytest.mark.integration
@pytest.mark.parametrize("family,intermediate", [("writer", "docx"), ("calc", "xlsx"), ("impress", "pptx")])
def test_office_families_roundtrip_to_pdf(tmp_path, family, intermediate):
    from zipfile import ZipFile, ZIP_DEFLATED
    import pymupdf
    tools = ToolRegistry(Settings())
    if not tools.get("libreoffice").available:
        pytest.skip("LibreOffice is not installed")
    if family == "writer":
        source = tmp_path / "中文 Writer.txt"
        source.write_text("MediaForge Writer document\nRoundtrip test", encoding="utf-8")
    elif family == "calc":
        source = tmp_path / "中文 Calc.csv"
        source.write_text("Name,Amount\nMediaForge,42\n", encoding="utf-8")
    else:
        source = tmp_path / "中文 Impress.odp"
        namespaces = 'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"'
        content = f'<office:document-content {namespaces} office:version="1.2"><office:body><office:presentation><draw:page draw:name="Page1" draw:master-page-name="Default"><draw:frame svg:x="1cm" svg:y="1cm" svg:width="20cm" svg:height="5cm"><draw:text-box><text:p>MediaForge presentation test</text:p></draw:text-box></draw:frame></draw:page></office:presentation></office:body></office:document-content>'
        styles = f'<office:document-styles {namespaces} office:version="1.2"><office:automatic-styles><style:page-layout style:name="PM1"><style:page-layout-properties fo:page-width="28cm" fo:page-height="21cm" style:print-orientation="landscape"/></style:page-layout></office:automatic-styles><office:master-styles><style:master-page style:name="Default" style:page-layout-name="PM1"/></office:master-styles></office:document-styles>'
        manifest = '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2"><manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.presentation"/><manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/><manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/></manifest:manifest>'
        with ZipFile(source, "w", ZIP_DEFLATED) as archive:
            archive.writestr("mimetype", "application/vnd.oasis.opendocument.presentation")
            archive.writestr("content.xml", content)
            archive.writestr("styles.xml", styles)
            archive.writestr("META-INF/manifest.xml", manifest)
    office_file = tmp_path / "office" / f"generated.{intermediate}"
    convert(Job("document", [source], intermediate, tmp_path), office_file, context(tmp_path, tools))
    validate_document(office_file, intermediate)
    output = tmp_path / "pdf" / f"{family}.pdf"
    convert(Job("document", [office_file], "pdf", tmp_path), output, context(tmp_path, tools))
    with pymupdf.open(output) as pdf:
        assert pdf.page_count >= 1
        assert "MediaForge" in "".join(page.get_text() for page in pdf)
