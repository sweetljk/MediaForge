from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


TERMINAL = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.SKIPPED}


@dataclass
class Job:
    category: str
    inputs: list[Path]
    target_format: str
    output_dir: Path
    params: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid4().hex)
    status: JobStatus = JobStatus.PENDING
    progress: float | None = 0.0
    message: str = "等待开始"
    error: str = ""
    output_paths: list[Path] = field(default_factory=list)
    log_path: Path | None = None
    created_at: str = field(default_factory=now)
    started_at: str | None = None
    finished_at: str | None = None

    def __post_init__(self):
        self.inputs = [Path(p).resolve() for p in self.inputs]
        self.output_dir = Path(self.output_dir).resolve()
        self.target_format = self.target_format.lower().lstrip(".")

    @property
    def elapsed(self) -> float:
        if not self.started_at:
            return 0.0
        end = datetime.fromisoformat(self.finished_at) if self.finished_at else datetime.now(timezone.utc)
        return max(0.0, (end - datetime.fromisoformat(self.started_at)).total_seconds())

    def to_dict(self) -> dict:
        data = asdict(self)
        data["inputs"] = [str(p) for p in self.inputs]
        data["output_dir"] = str(self.output_dir)
        data["output_paths"] = [str(p) for p in self.output_paths]
        data["log_path"] = str(self.log_path) if self.log_path else None
        data["status"] = self.status.value
        data["elapsed"] = self.elapsed
        return data

    def transition(self, status: JobStatus) -> None:
        allowed = {
            JobStatus.PENDING: {JobStatus.RUNNING, JobStatus.CANCELLED},
            JobStatus.RUNNING: TERMINAL,
        }
        if status not in allowed.get(self.status, set()):
            raise ValueError(f"Invalid transition: {self.status} -> {status}")
        self.status = status
        if status == JobStatus.RUNNING:
            self.started_at = now()
        if status in TERMINAL:
            self.finished_at = now()
