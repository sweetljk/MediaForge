"""LibreOffice command construction and isolated, noninteractive execution."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mediaforge.engines.base import ConversionContext


FILTERS = {
    "writer": {"pdf": "writer_pdf_Export", "docx": "Office Open XML Text", "doc": "MS Word 97", "odt": "writer8", "rtf": "Rich Text Format", "txt": "Text (encoded):UTF8", "html": "HTML (StarWriter):EmbedImages"},
    "calc": {"pdf": "calc_pdf_Export", "xlsx": "Calc MS Excel 2007 XML", "xls": "MS Excel 97", "ods": "calc8", "csv": "Text - txt - csv (StarCalc):44,34,76"},
    "impress": {"pdf": "impress_pdf_Export", "pptx": "Impress MS PowerPoint 2007 XML", "ppt": "MS PowerPoint 97", "odp": "impress8"},
}
FAMILIES = {
    **dict.fromkeys(["doc", "docx", "odt", "rtf", "txt", "html", "htm"], "writer"),
    **dict.fromkeys(["xls", "xlsx", "ods", "csv"], "calc"),
    **dict.fromkeys(["ppt", "pptx", "odp"], "impress"),
}


def build_command(executable: str, source: Path, outdir: Path, profile: Path, family: str, target: str) -> list[str]:
    return [
        str(executable), f"-env:UserInstallation={profile.resolve().as_uri()}",
        "--headless", "--nologo", "--nodefault", "--nofirststartwizard", "--norestore",
        "--convert-to", f"{target}:{FILTERS[family][target]}", "--outdir", str(outdir), str(source),
    ]


def prepare_profile(profile: Path) -> None:
    user = profile / "user"
    user.mkdir(parents=True, exist_ok=True)
    (user / "registrymodifications.xcu").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<oor:items xmlns:oor="http://openoffice.org/2001/registry">'
        '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
        '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>'
        '</item>'
        '<item oor:path="/org.openoffice.Office.Common/Load">'
        '<prop oor:name="UpdateMode" oor:op="fuse"><value>0</value></prop>'
        '</item></oor:items>', encoding="utf-8",
    )


def run_conversion(context: "ConversionContext", source: Path, outdir: Path, profile: Path, family: str, target: str, timeout: float) -> Path:
    executable = context.tools.require("libreoffice")
    prepare_profile(profile)
    outdir.mkdir(parents=True, exist_ok=True)
    context.progress(None, "LibreOffice 正在转换（此引擎不提供百分比进度）")
    context.run(build_command(executable, source, outdir, profile, family, target), timeout=timeout)
    context.check_cancelled()
    return outdir / f"{source.stem}.{target}"
