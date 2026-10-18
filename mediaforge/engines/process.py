"""The sole external-process gateway, shared by detection and converters."""
from __future__ import annotations

import os
import locale
import queue
import subprocess
import threading
import time
import signal
from pathlib import Path
from collections import deque
from typing import Callable

import psutil

from mediaforge.core.errors import CancelledError, ConversionError


class _WindowsJob:
    """Keep descendants cancellable even after a launcher process has exited."""
    def __init__(self, process):
        self.handle = None
        if os.name != "nt":
            return
        import ctypes
        from ctypes import wintypes
        class BasicLimit(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]
        class ExtendedLimit(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BasicLimit), ("IoInfo", ctypes.c_ulonglong * 6),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel = kernel
        handle = kernel.CreateJobObjectW(None, None)
        if not handle:
            return
        limits = ExtendedLimit()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)) and kernel.AssignProcessToJobObject(handle, int(process._handle)):
            self.handle = handle
        else:
            kernel.CloseHandle(handle)

    def terminate(self):
        if self.handle:
            self.kernel.TerminateJobObject(self.handle, 1)

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def _terminate(process: subprocess.Popen, job=None) -> None:
    if job:
        job.terminate()
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)
        for child in reversed(children):
            try:
                child.terminate()
            except psutil.Error:
                pass
        try:
            parent.terminate()
        except psutil.Error:
            pass
        _, alive = psutil.wait_procs(children + [parent], timeout=2)
        for child in alive:
            try:
                child.kill()
            except psutil.Error:
                pass
    except psutil.Error:
        if process.poll() is None:
            process.kill()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()


def run_process(args: list[str], *, cancel: threading.Event | None = None,
                timeout: float = 3600, on_line: Callable[[str], None] | None = None,
                log_path: Path | None = None) -> str:
    if not isinstance(args, list) or not args or any(not isinstance(a, str) for a in args):
        raise TypeError("Process arguments must be a nonempty list of strings")
    if cancel and cancel.is_set():
        raise CancelledError("任务已取消")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, shell=False, creationflags=flags,
                                   start_new_session=os.name != "nt")
    except FileNotFoundError as exc:
        raise ConversionError("找不到转换工具，请在设置中检查可执行文件路径。") from exc
    except OSError as exc:
        raise ConversionError(f"无法启动转换工具：{exc.strerror or exc}") from exc
    job = _WindowsJob(process)
    lines: queue.Queue[bytes | None] = queue.Queue(maxsize=512)
    stop = threading.Event()

    def read_output():
        try:
            while not stop.is_set():
                line = process.stdout.readline(65536)
                if not line:
                    break
                while not stop.is_set():
                    try:
                        lines.put(line, timeout=0.1)
                        break
                    except queue.Full:
                        pass
        finally:
            while not stop.is_set():
                try:
                    lines.put(None, timeout=0.1)
                    break
                except queue.Full:
                    pass

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    started = time.monotonic()
    output = deque(maxlen=8192)
    log = None
    try:
        if log_path:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log = log_path.open("a", encoding="utf-8")
            log.write(f"\nEngine: {Path(args[0]).name}\n")
        while True:
            if cancel and cancel.is_set():
                raise CancelledError("任务已取消；转换进程已停止。")
            if time.monotonic() - started > timeout:
                raise ConversionError(f"转换超时（{timeout:g} 秒），进程已停止。可在设置中增大超时。")
            try:
                item = lines.get(timeout=0.1)
            except queue.Empty:
                continue
            if item is None:
                break
            try:
                line = item.decode("utf-8").rstrip()
            except UnicodeDecodeError:
                line = item.decode(locale.getencoding(), errors="replace").rstrip()
            output.append(line)
            if log:
                log.write(line + "\n")
            if on_line:
                on_line(line)
        remaining = max(0.1, timeout - (time.monotonic() - started))
        while process.poll() is None:
            if cancel and cancel.is_set():
                raise CancelledError("任务已取消")
            if time.monotonic() - started > timeout:
                raise ConversionError("转换工具超时，已停止。")
            time.sleep(min(0.05, remaining))
        result = "\n".join(output)
        if process.returncode:
            progress_keys = {"frame", "fps", "stream_0_0_q", "bitrate", "total_size", "out_time_us", "out_time_ms", "out_time", "dup_frames", "drop_frames", "speed", "progress"}
            errors = [line for line in output if line.partition("=")[0] not in progress_keys]
            detail = "\n".join(errors[-10:])[-1800:]
            raise ConversionError(f"转换工具退出（代码 {process.returncode}）。\n{detail}")
        if cancel and cancel.is_set():
            raise CancelledError("任务已取消")
        return result
    finally:
        stop.set()
        # Also terminate the process group if its launcher has already exited.
        _terminate(process, job)
        job.close()
        reader.join(timeout=3)
        process.stdout.close()
        if log:
            log.close()
