from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable, TYPE_CHECKING

from mediaforge.core.errors import CancelledError
from mediaforge.engines.process import run_process

if TYPE_CHECKING:
    from mediaforge.services.tools import ToolRegistry


@dataclass
class ConversionContext:
    tools: ToolRegistry
    cancel: Event
    log_path: Path
    progress: Callable[[float | None, str], None]
    timeout: float = 7200

    def check_cancelled(self) -> None:
        if self.cancel.is_set():
            raise CancelledError("任务已取消")

    def run(self, args: list[str], timeout: float | None = None, on_line=None) -> str:
        return run_process(args, cancel=self.cancel, timeout=timeout or self.timeout,
                           on_line=on_line, log_path=self.log_path)
