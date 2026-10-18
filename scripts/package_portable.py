"""Build a self-contained Windows folder and ZIP without developer caches."""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


def main():
    if sys.platform != "win32":
        raise SystemExit("Build the Windows portable package on Windows.")
    root = Path(__file__).resolve().parents[1]
    release = root / "release"
    destination = release / "MediaForge"
    archive = release / "MediaForge-0.1.0-windows-x64-portable.zip"
    # Never silently replace a distribution that may already be in use.
    if destination.exists() or archive.exists():
        raise SystemExit("release/MediaForge or the ZIP already exists. Move it aside before rebuilding.")
    ffmpeg = root / ".tools" / "ffmpeg"
    builds = [path for path in ffmpeg.iterdir() if path.is_dir() and (path / "bin/ffmpeg.exe").is_file()]
    if len(builds) != 1 or not (builds[0] / "bin/ffprobe.exe").is_file():
        raise SystemExit("Expected exactly one complete FFmpeg build under .tools/ffmpeg.")
    office = root / ".tools" / "libreoffice"
    if not (office / "program/soffice.com").is_file() or not (office / "System64/vcruntime140.dll").is_file():
        raise SystemExit("LibreOffice administrative extraction and x64 runtime files are required.")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", str(release),
                    "--workpath", str(root / "build/portable"), "MediaForge.spec"], cwd=root, check=True)
    shutil.copytree(builds[0], destination / ".tools/ffmpeg" / builds[0].name)
    shutil.copytree(office, destination / ".tools/libreoffice", ignore=shutil.ignore_patterns("*.msi"))
    # Administrative extraction leaves VC runtimes in System64. Put the x64
    # copies next to soffice.bin for app-local DLL loading on a fresh PC.
    for dll in (office / "System64").glob("*.dll"):
        shutil.copy2(dll, destination / ".tools/libreoffice/program" / dll.name)
    for name in ("LICENSE", "README.md", "THIRD_PARTY_NOTICES.md", "TOOLS_PROVENANCE.md", "TEST_REPORT.md"):
        shutil.copy2(root / name, destination / name)
    (destination / "使用说明.txt").write_text(
        "MediaForge 完整便携版\n\n"
        "1. 将整个压缩包解压到一个文件夹，不要直接在压缩包里运行。\n"
        "2. 双击 MediaForge.exe。无需安装 Python，无需运行 VBS 或配置转换引擎。\n"
        "3. 保留 _internal 和 .tools 文件夹，不要单独移动 EXE。\n\n"
        "适用于 Windows 11 x64；本包不适用于 Linux 或 macOS。\n"
        "内含 FFmpeg / FFprobe 与 LibreOffice，文件在本地处理。\n"
        "设置和历史保存在当前用户的 LocalAppData/MediaForge。\n"
        "如曾手动配置旧工具路径，可在设置中清空该项后重新检测。\n"
        "许可证及分发说明见 THIRD_PARTY_NOTICES.md 和各组件附带声明。\n",
        encoding="utf-8-sig")
    print(f"Portable folder: {destination}", flush=True)
    subprocess.run([sys.executable, str(root / "scripts/verify_package.py"), "--portable",
                    "--executable", str(destination / "MediaForge.exe"),
                    "--area", str(root / "artifacts/portable-check")], cwd=root, check=True)
    (destination / "PORTABLE_TEST_REPORT.txt").write_text(
        "Portable EXE verification: 6 real conversion flows and GUI startup passed.\n"
        "Worker settings contained no configured engine paths; MEDIAFORGE engine\n"
        "environment variables were cleared; PATH contained only Windows System32.\n"
        "Working directory differed from the EXE directory. VBS was not used.\n"
        "Image, PDF, text, video, audio and LibreOffice conversions passed.\n"
        "Tested on the development Windows 11 x64 PC, not a fresh second machine.\n",
        encoding="utf-8")
    print("Compressing verified portable folder...", flush=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=4, allowZip64=True) as bundle:
        for path in sorted(destination.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(release))
    with archive.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{checksum}  {archive.name}\n", encoding="ascii")
    print(f"Portable ZIP: {archive} ({archive.stat().st_size:,} bytes)", flush=True)


if __name__ == "__main__":
    main()
