from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from threading import Event

from mediaforge.core.errors import CancelledError, ConversionError, SkipError


def resolve_output(directory: Path, name: str, policy: str = "rename", *,
                   protected: list[Path] = (), reserved: set[Path] | None = None) -> Path:
    directory = Path(directory).resolve()
    if Path(name).name != name or name in {"", ".", ".."}:
        raise ConversionError("输出文件名无效。")
    candidate = directory / name
    protected_paths = {Path(p).resolve() for p in protected}
    reserved = reserved or set()
    exists = candidate.exists() or candidate in reserved
    is_source = candidate.resolve() in protected_paths
    if exists and policy == "skip" and not is_source:
        raise SkipError(f"输出已存在，按设置跳过：{candidate.name}")
    if exists and policy == "overwrite" and not is_source and candidate not in reserved:
        if not candidate.is_file() or candidate.is_symlink():
            raise ConversionError("无法覆盖目录或符号链接。")
        return candidate
    if exists or is_source:
        index = 1
        while True:
            renamed = directory / f"{candidate.stem} ({index}){candidate.suffix}"
            if not renamed.exists() and renamed not in reserved and renamed.resolve() not in protected_paths:
                return renamed
            index += 1
    return candidate


def check_writable(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryFile(dir=directory):
            pass
    except OSError as exc:
        raise ConversionError(f"目录不可写，请选择有写入权限的位置：{directory}") from exc


def copy_cancellable(source: Path, destination: Path, cancel: Event, *, on_created=None) -> None:
    with source.open("rb") as reader, destination.open("xb") as writer:
        if on_created:
            on_created()
        while True:
            if cancel.is_set():
                raise CancelledError("保存结果时取消，临时文件已清理。")
            chunk = reader.read(1024 * 1024)
            if not chunk:
                break
            writer.write(chunk)
        writer.flush()
        os.fsync(writer.fileno())


def check_space(directory: Path, needed: int) -> None:
    if shutil.disk_usage(directory).free < needed:
        raise ConversionError("磁盘可用空间不足，请更换输出或临时目录后重试。")
