"""Regression coverage for publishing ownership and process/resource cleanup."""
import errno
import gc
import sys
import threading
import time
from pathlib import Path

import psutil
import pytest

from mediaforge.core.errors import CancelledError
from mediaforge.core.models import Job
from mediaforge.engines.process import run_process
from mediaforge.jobs.manager import JobManager
from mediaforge.services.history import HistoryStore
from mediaforge.services.settings import Settings
from mediaforge.services.tools import ToolRegistry
from mediaforge.utils.paths import copy_cancellable


@pytest.fixture
def publisher(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIAFORGE_DATA_DIR", str(tmp_path / "data"))
    output = tmp_path / "output"
    output.mkdir()
    settings = Settings(output_dir=str(output))
    manager = JobManager(settings, ToolRegistry(settings))
    yield manager, output
    manager.shutdown(wait=True)


def test_unsupported_links_and_external_creation_preserve_external_file(publisher, tmp_path, monkeypatch):
    manager, output = publisher
    source = tmp_path / "converted.txt"
    source.write_text("conversion result", encoding="utf-8")
    target = output / source.name
    job = Job("document", [tmp_path / "input.txt"], "txt", output)

    def unsupported_link(*args):
        raise OSError(errno.ENOTSUP, "Filesystem does not support hard links")

    def racing_copy(source, destination, cancel, **kwargs):
        if destination == target:
            target.write_text("created by another application", encoding="utf-8")
        return copy_cancellable(source, destination, cancel, **kwargs)

    monkeypatch.setattr("mediaforge.jobs.manager.os.link", unsupported_link)
    monkeypatch.setattr("mediaforge.jobs.manager.copy_cancellable", racing_copy)
    with pytest.raises((FileExistsError, OSError)):
        manager._publish(job, [source], threading.Event())
    assert target.read_text(encoding="utf-8") == "created by another application"
    assert list(output.iterdir()) == [target]
    assert not job.output_paths


def test_failed_stage_unlink_rolls_back_already_linked_output(publisher, tmp_path, monkeypatch):
    manager, output = publisher
    source = tmp_path / "converted.txt"
    source.write_text("conversion result", encoding="utf-8")
    job = Job("document", [tmp_path / "input.txt"], "txt", output)
    real_unlink = Path.unlink
    injected = False

    def occupied_once(path, *args, **kwargs):
        nonlocal injected
        if path.suffix == ".partial" and not injected:
            injected = True
            raise PermissionError("Transient antivirus lock")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", occupied_once)
    with pytest.raises(PermissionError):
        manager._publish(job, [source], threading.Event())
    assert injected
    assert list(output.iterdir()) == []
    assert source.read_text(encoding="utf-8") == "conversion result"


def test_history_closes_every_database_connection_before_return(tmp_path):
    # Disable cyclic GC so unclosed sqlite connections cannot disappear by chance.
    was_enabled = gc.isenabled()
    gc.disable()
    path = tmp_path / "history.sqlite3"
    moved = tmp_path / "history-moved.sqlite3"
    try:
        history = HistoryStore(path=path)
        path.rename(moved)
        moved.rename(path)
        job = Job("image", [tmp_path / "image.png"], "jpeg", tmp_path)
        history.record(job)
        path.rename(moved)
        moved.rename(path)
        assert history.load()[0]["id"] == job.id
        path.rename(moved)
        moved.unlink()
        assert not path.exists() and not moved.exists()
    finally:
        if was_enabled:
            gc.enable()


def test_cancel_stops_descendant_after_launcher_has_exited(tmp_path):
    parent = tmp_path / "launcher.py"
    pid_file = tmp_path / "descendant.pid"
    parent.write_text(
        "import subprocess, sys\n"
        "from pathlib import Path\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(5)'])\n"
        "Path(sys.argv[1]).write_text(str(child.pid))\n",
        encoding="utf-8",
    )
    cancel = threading.Event()

    def cancel_after_parent_exit():
        deadline = time.monotonic() + 5
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.2)
        cancel.set()

    trigger = threading.Thread(target=cancel_after_parent_exit, daemon=True)
    trigger.start()
    started = time.monotonic()
    try:
        with pytest.raises(CancelledError):
            run_process([sys.executable, str(parent), str(pid_file)], cancel=cancel, timeout=3)
        elapsed = time.monotonic() - started
        assert elapsed < 2.5, f"Cancellation waited {elapsed:.2f}s for an orphaned descendant"
        assert pid_file.exists(), "The launcher must create a child before cancellation"
        pid = int(pid_file.read_text())
        assert not psutil.pid_exists(pid), "Cancellation left the conversion descendant running"
    finally:
        cancel.set()
        trigger.join(timeout=6)
        if pid_file.exists():
            try:
                descendant = psutil.Process(int(pid_file.read_text()))
                descendant.kill()
                descendant.wait(timeout=3)
            except psutil.Error:
                pass
