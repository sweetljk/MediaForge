import threading
import time
from pathlib import Path

import pytest
from PIL import Image

from mediaforge.core.errors import ConversionError
from mediaforge.core.models import Job, JobStatus, TERMINAL
from mediaforge.jobs.manager import JobManager
from mediaforge.services.settings import Settings
from mediaforge.services.tools import ToolRegistry


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIAFORGE_DATA_DIR", str(tmp_path / "data"))
    settings = Settings(output_dir=str(tmp_path / "out"), temp_dir=str(tmp_path / "temp"), log_dir=str(tmp_path / "logs"))
    manager = JobManager(settings, ToolRegistry(settings))
    yield manager
    manager.shutdown(wait=True)


def wait_done(manager, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        jobs = manager.jobs()
        if jobs and all(job.status in TERMINAL for job in jobs):
            return jobs
        time.sleep(0.025)
    pytest.fail("Queue did not finish")


def create_job(manager, tmp_path):
    source = tmp_path / "中文 样例.png"
    Image.new("RGBA", (40, 30), (255, 0, 0, 128)).save(source)
    return Job("image", [source], "jpeg", Path(manager.settings.output_dir))


def test_real_queue_and_history(manager, tmp_path):
    job = create_job(manager, tmp_path)
    states = []
    manager.subscribe(lambda update: states.append(update.status))
    manager.add(job)
    manager.start()
    result = wait_done(manager)[0]
    assert result.status == JobStatus.COMPLETED, result.error
    assert result.progress == 100 and result.output_paths[0].is_file()
    with Image.open(result.output_paths[0]) as image:
        assert image.format == "JPEG" and image.size == (40, 30)
    assert states[0] == JobStatus.PENDING and JobStatus.RUNNING in states
    assert manager.history.load()[0]["status"] == "completed"
    assert not list(Path(manager.settings.temp_dir).glob("mf-*"))


def test_failure_cleanup_and_retry(manager, tmp_path, monkeypatch):
    manager._isolate_native = False
    job = create_job(manager, tmp_path)
    def fail(job, output, context):
        output.write_bytes(b"partial")
        raise ConversionError("expected failure")
    monkeypatch.setattr("mediaforge.jobs.manager.converter_for", lambda *args: fail)
    manager.add(job)
    manager.start()
    result = wait_done(manager)[0]
    assert result.status == JobStatus.FAILED and "expected failure" in result.error
    assert not list(Path(manager.settings.output_dir).iterdir())
    assert not list(Path(manager.settings.temp_dir).iterdir())
    retried = manager.retry(job.id)
    assert retried.id != job.id and retried.status == JobStatus.PENDING


def test_pending_cancel_and_running_cancel(manager, tmp_path, monkeypatch):
    manager._isolate_native = False
    first = create_job(manager, tmp_path)
    manager.add(first)
    manager.cancel(first.id)
    assert manager.jobs()[0].status == JobStatus.CANCELLED
    def slow(job, output, context):
        output.write_bytes(b"half")
        while True:
            context.check_cancelled()
            time.sleep(0.01)
    monkeypatch.setattr("mediaforge.jobs.manager.converter_for", lambda *args: slow)
    second = manager.retry(first.id)
    manager.start()
    time.sleep(0.1)
    manager.cancel(second.id)
    result = wait_done(manager)[1]
    assert result.status == JobStatus.CANCELLED
    assert not list(Path(manager.settings.temp_dir).iterdir())
    assert not list(Path(manager.settings.output_dir).iterdir())


def test_concurrency_and_no_collisions(manager, tmp_path, monkeypatch):
    manager._isolate_native = False
    manager.settings.concurrency = 2
    seen = []
    barrier = threading.Barrier(2)
    def work(job, output, context):
        seen.append(manager.active_count)
        barrier.wait(timeout=5)
        output.write_bytes(b"valid synthetic unit fixture")
        return [output]
    monkeypatch.setattr("mediaforge.jobs.manager.converter_for", lambda *args: work)
    manager.add(create_job(manager, tmp_path))
    manager.add(create_job(manager, tmp_path))
    manager.start()
    jobs = wait_done(manager)
    assert all(j.status == JobStatus.COMPLETED for j in jobs)
    assert len({j.output_paths[0] for j in jobs}) == 2
    assert max(seen) == 2


def test_skip_and_protect_original(manager, tmp_path):
    job = create_job(manager, tmp_path)
    manager.add(job)
    manager.start()
    result = wait_done(manager)[0]
    original = result.output_paths[0].read_bytes()
    manager.settings.overwrite = "skip"
    manager.add(create_job(manager, tmp_path))
    manager.start()
    assert wait_done(manager)[1].status == JobStatus.SKIPPED
    assert result.output_paths[0].read_bytes() == original


def test_overwrite_requires_confirmation(manager, tmp_path):
    manager.settings.overwrite = "overwrite"
    manager.add(create_job(manager, tmp_path))
    manager.start()
    assert "明确确认" in wait_done(manager)[0].error


def test_real_isolated_pdf_cancel_and_cleanup(manager, tmp_path):
    import pymupdf
    source = tmp_path / "取消 渲染.pdf"
    with pymupdf.open() as doc:
        for number in range(25):
            doc.new_page(width=600, height=800).insert_text((40, 50), f"Page {number}")
        doc.save(source)
    job = Job("pdf", [source], "png", Path(manager.settings.output_dir), {"operation": "render", "dpi": 300})
    manager.add(job)
    manager.start()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        result = manager.jobs()[0]
        if result.message.startswith("已渲染"):
            break
        assert result.status not in TERMINAL, result.error
        time.sleep(0.015)
    else:
        pytest.fail("No real rendering progress arrived")
    manager.cancel(job.id)
    assert wait_done(manager)[0].status == JobStatus.CANCELLED
    assert source.exists()
    assert not list(Path(manager.settings.output_dir).iterdir())
    assert not list(Path(manager.settings.temp_dir).iterdir())


def test_publish_rolls_back_overwrite_on_second_failure(manager, tmp_path, monkeypatch):
    output_dir = Path(manager.settings.output_dir)
    output_dir.mkdir()
    target_a, target_b = output_dir / "a.txt", output_dir / "b.txt"
    target_a.write_text("old-a")
    target_b.write_text("old-b")
    stage = tmp_path / "stage"
    stage.mkdir()
    source_a, source_b = stage / "a.txt", stage / "b.txt"
    source_a.write_text("new-a")
    source_b.write_text("new-b")
    job = Job("document", [tmp_path / "input.txt"], "txt", output_dir, {"overwrite": "overwrite", "overwrite_confirmed": True})
    replace = Path.replace
    def fail_second(path, target):
        if path.suffix == ".partial" and Path(target) == target_b:
            raise PermissionError("occupied")
        return replace(path, target)
    monkeypatch.setattr(Path, "replace", fail_second)
    with pytest.raises(PermissionError):
        manager._publish(job, [source_a, source_b], threading.Event())
    assert target_a.read_text() == "old-a" and target_b.read_text() == "old-b"
    assert sorted(p.name for p in output_dir.iterdir()) == ["a.txt", "b.txt"]
