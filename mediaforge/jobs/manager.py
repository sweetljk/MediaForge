from __future__ import annotations

import copy
import errno
import json
import logging
import os
import shutil
import tempfile
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from mediaforge.core.errors import CancelledError, ConversionError, SkipError
from mediaforge.core.formats import converter_for
from mediaforge.core.models import Job, JobStatus, TERMINAL
from mediaforge.engines.base import ConversionContext
from mediaforge.services.history import HistoryStore
from mediaforge.utils.paths import check_space, check_writable, copy_cancellable, resolve_output


class JobManager:
    """Qt-free queue. Only workers execute engines; callbacks may run on any thread."""

    def __init__(self, settings, tools, *, isolate_native=True):
        self.settings = settings
        self.tools = tools
        self._isolate_native = isolate_native
        self._lock = threading.RLock()
        self._commit_lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._active: set[str] = set()
        self._callbacks = []
        self._executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="MediaForge")
        self._started = False
        self._closed = False
        self.history = HistoryStore(settings)

    def subscribe(self, callback):
        self._callbacks.append(callback)

    def _emit(self, job):
        with self._lock:
            snapshot = copy.deepcopy(job)
        for callback in tuple(self._callbacks):
            try:
                callback(snapshot)
            except Exception:
                logging.getLogger(__name__).exception("Job observer failed")

    def jobs(self) -> list[Job]:
        with self._lock:
            return copy.deepcopy(list(self._jobs.values()))

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    def add(self, job: Job) -> Job:
        with self._lock:
            if self._closed:
                raise ConversionError("任务管理器已关闭。")
            if job.id in self._jobs:
                raise ConversionError("任务 ID 已存在。")
            if job.status != JobStatus.PENDING:
                raise ConversionError("只能添加待处理任务。")
            self._jobs[job.id] = copy.deepcopy(job)
            self._cancel[job.id] = threading.Event()
        self._emit(job)
        return job

    def start(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._started = True
            self._schedule()

    def _schedule(self):
        if self._closed or not self._started:
            return
        limit = max(1, min(3, int(self.settings.concurrency)))
        for job in self._jobs.values():
            if len(self._active) >= limit:
                break
            if job.status == JobStatus.PENDING and job.id not in self._active:
                self._active.add(job.id)
                # Transition before scheduling so removal/cancel cannot race a queued worker.
                job.transition(JobStatus.RUNNING)
                job.progress = None
                job.message = "正在检查文件与转换工具"
                self._emit(job)
                self._executor.submit(self._execute, job)
        if not self._active:
            self._started = False

    def cancel(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status in TERMINAL:
                return
            self._cancel[job_id].set()
            if job.status == JobStatus.PENDING:
                job.transition(JobStatus.CANCELLED)
                job.message = "任务已取消"
                self._record(job)
            else:
                job.message = "正在取消并清理临时文件…"
            self._emit(job)

    def retry(self, job_id: str) -> Job:
        with self._lock:
            previous = self._jobs[job_id]
            if previous.status not in {JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.SKIPPED}:
                raise ConversionError("只有失败、取消或跳过的任务可以重试。")
            job = Job(previous.category, list(previous.inputs), previous.target_format,
                      previous.output_dir, copy.deepcopy(previous.params))
        return self.add(job)

    def remove(self, job_id: str) -> None:
        with self._lock:
            if job_id in self._active:
                raise ConversionError("请先取消任务，等待进程停止后再移除。")
            self._jobs.pop(job_id, None)
            self._cancel.pop(job_id, None)

    def _record(self, job):
        try:
            self.history.record(job)
        except Exception:
            # Successful conversion must not be relabelled a failure due to history IO.
            job.message += "（历史记录保存失败，请检查应用数据目录权限）"

    def _execute(self, job: Job):
        cancel = self._cancel[job.id]
        temporary = None
        status = JobStatus.FAILED
        try:
            log_dir = Path(self.settings.log_dir).expanduser().resolve()
            log_dir.mkdir(parents=True, exist_ok=True)
            job.log_path = log_dir / f"{job.id}.log"
            job.log_path.write_text(f"MediaForge job {job.id}\nCategory: {job.category}\nTarget: {job.target_format}\n", encoding="utf-8")
            if not job.inputs:
                raise ConversionError("请先添加输入文件。")
            for source in job.inputs:
                if not source.is_file():
                    raise ConversionError(f"输入文件不存在或不是普通文件：{source.name}")
                if source.stat().st_size == 0:
                    raise ConversionError(f"输入文件为空：{source.name}")
            converter = converter_for(job.category, job.target_format)
            root = Path(self.settings.temp_dir).expanduser().resolve()
            check_writable(root)
            check_writable(job.output_dir)
            total_size = sum(p.stat().st_size for p in job.inputs)
            minimum = min(total_size, 16 * 1024 * 1024) + 1024 * 1024
            check_space(root, minimum)
            check_space(job.output_dir, minimum)
            temporary = Path(tempfile.mkdtemp(prefix=f"mf-{job.id}-", dir=root))
            (temporary / ".mediaforge-owned").write_text(json.dumps({"id": job.id, "pid": os.getpid()}), encoding="utf-8")
            suffix = "jpg" if job.target_format == "jpeg" else job.target_format
            basename = job.inputs[0].stem
            if job.category == "pdf" and job.params.get("operation") == "merge":
                basename += "_merged"
            output = temporary / f"{basename}.{suffix}"

            last_progress_emit = 0.0

            def progress(value, message=""):
                nonlocal last_progress_emit
                with self._lock:
                    job.progress = None if value is None else max(0.0, min(99.0, float(value)))
                    if message and not cancel.is_set():
                        job.message = message
                # Throttle UI notifications only; never synthesize progress.
                instant = time.monotonic()
                if value is None or instant - last_progress_emit >= 0.1:
                    last_progress_emit = instant
                    self._emit(job)

            context = ConversionContext(self.tools, cancel, job.log_path, progress, self.settings.timeout)
            context.check_cancelled()
            if self._isolate_native and job.category in {"image", "pdf", "document"}:
                from mediaforge.engines.native import convert_isolated
                produced = convert_isolated(job, output, context, self.settings)
            else:
                produced = converter(job, output, context)
            produced = [Path(p).resolve() for p in produced]
            context.check_cancelled()
            if not produced or len(produced) != len(set(produced)):
                raise ConversionError("转换引擎没有生成有效的输出文件。")
            for path in produced:
                if not path.is_relative_to(temporary.resolve()) or path.is_symlink():
                    raise ConversionError("转换引擎返回了非任务目录中的输出，已拒绝保存。")
                if not path.is_file() or path.stat().st_size == 0:
                    raise ConversionError("转换结果不存在或为空，未保存输出。")
            progress(None, "正在校验并保存输出文件")
            self._publish(job, produced, cancel)
            status = JobStatus.COMPLETED
            job.progress = 100.0
            job.message = f"已完成 · {len(job.output_paths)} 个输出文件"
        except CancelledError as exc:
            status = JobStatus.CANCELLED
            job.message = str(exc)
        except SkipError as exc:
            status = JobStatus.SKIPPED
            job.message = str(exc)
        except Exception as exc:
            if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
                job.error = "磁盘空间不足，请更换目录或释放空间后重试。"
            elif isinstance(exc, PermissionError):
                job.error = "文件被占用或目录无写入权限，请关闭占用文件的程序或更换目录。"
            elif isinstance(exc, ConversionError):
                job.error = str(exc)
            else:
                job.error = f"转换失败：{exc}。详细信息已记录到任务日志。"
            job.message = job.error
            if job.log_path:
                try:
                    with job.log_path.open("a", encoding="utf-8") as log:
                        log.write("\n" + traceback.format_exc())
                except OSError:
                    pass
        finally:
            if temporary and temporary.is_dir():
                try:
                    # Exact directory created above; never follow a user-provided cleanup path.
                    shutil.rmtree(temporary)
                except OSError:
                    job.message += "（临时目录被占用，稍后可手动清理）"
            with self._lock:
                job.transition(status)
                self._active.discard(job.id)
                self._record(job)
                self._emit(job)
                self._schedule()

    def _publish(self, job, files, cancel):
        policy = job.params.get("overwrite", self.settings.overwrite)
        if policy not in {"rename", "skip", "overwrite"}:
            raise ConversionError("无效的文件冲突策略。")
        if policy == "overwrite" and not job.params.get("overwrite_confirmed"):
            raise ConversionError("覆盖现有输出需要明确确认。请选择自动改名，或在界面中确认覆盖。")
        with self._commit_lock:
            targets = []
            reserved = set()
            for path in files:
                target = resolve_output(job.output_dir, path.name, policy, protected=job.inputs, reserved=reserved)
                reserved.add(target)
                targets.append(target)
            check_space(job.output_dir, sum(p.stat().st_size for p in files) + 1024 * 1024)
            staged, backups, committed = [], [], []
            try:
                for source, target in zip(files, targets):
                    adjacent = target.parent / f".mediaforge-{uuid4().hex}.partial"
                    copy_cancellable(source, adjacent, cancel, on_created=lambda p=adjacent: staged.append(p))
                if cancel.is_set():
                    raise CancelledError("任务已取消")
                # Commit is deliberately indivisible with respect to cancellation. A cancel
                # after this boundary results in a completed job with complete outputs.
                for stage, target in zip(staged, targets):
                    if target.exists():
                        if policy != "overwrite" or target.resolve() in {p.resolve() for p in job.inputs}:
                            raise ConversionError("保存期间输出路径发生冲突，请重试。")
                        backup = target.parent / f".mediaforge-{uuid4().hex}.backup"
                        target.replace(backup)
                        backups.append((backup, target))
                    if policy == "overwrite":
                        stage.replace(target)
                    else:
                        # Hard linking is exclusive, preventing an external creator from
                        # being overwritten between exists() and publish on NTFS/ext4.
                        try:
                            os.link(stage, target)
                        except FileExistsError as exc:
                            raise ConversionError("保存期间出现同名文件，请重试。") from exc
                        except OSError as exc:
                            if target.exists():
                                raise
                            # FAT/exFAT may not support links. Exclusive creation preserves
                            # conflict safety; failure/cancellation rolls back the output.
                            copy_cancellable(stage, target, threading.Event(), on_created=lambda p=target: committed.append(p))
                            stage.unlink()
                            continue
                        else:
                            committed.append(target)
                            stage.unlink()
                            continue
                    committed.append(target)
                job.output_paths = targets
            except Exception:
                for target in reversed(committed):
                    target.unlink(missing_ok=True)
                for backup, target in reversed(backups):
                    backup.replace(target)
                raise
            finally:
                for path in staged:
                    path.unlink(missing_ok=True)
            for backup, _ in backups:
                try:
                    backup.unlink(missing_ok=True)
                except OSError:
                    pass

    def shutdown(self, wait=False):
        with self._lock:
            self._closed = True
            for job_id in tuple(self._jobs):
                self.cancel(job_id)
        self._executor.shutdown(wait=wait, cancel_futures=False)
