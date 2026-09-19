"""Persisted jobs: runner semantics, failure capture, and restart reconciliation."""

from __future__ import annotations

import threading
import time

import pytest

from postgen.config import Settings
from postgen.services.jobs import JobBusyError, JobContext, JobRunner
from postgen.services.setup import checks, is_ready
from postgen.store.db import INTERRUPTED, Store


def _wait(store: Store, job_id: int) -> None:
    for _ in range(200):
        job = store.jobs.get(job_id)
        if job and job.status != "running":
            return
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def test_runner_persists_progress_and_result(store: Store) -> None:
    runner = JobRunner(store)

    def target(job: JobContext) -> str:
        job.progress("step one")
        job.attach_run(store.create_run())
        return "/done"

    job_id = runner.start("generate", target)
    _wait(store, job_id)
    job = store.jobs.get(job_id)
    assert job and job.status == "done" and job.result == "/done" and job.run_id == 1
    assert job.log_lines[0].endswith("step one") and job.finished_at
    assert not runner.running()


def test_runner_records_failure_and_rejects_overlap(store: Store) -> None:
    runner = JobRunner(store)
    gate = threading.Event()

    def slow(job: JobContext) -> str:
        gate.wait(2)
        raise ValueError("boom")

    job_id = runner.start("voice", slow)
    assert runner.running() and runner.active_job_id() == job_id
    with pytest.raises(JobBusyError) as exc:
        runner.start("voice", slow)
    assert exc.value.job_id == job_id
    gate.set()
    _wait(store, job_id)
    job = store.jobs.get(job_id)
    assert job and job.status == "failed" and job.error == "ValueError: boom"
    assert store.jobs.running() is None and store.jobs.list()[0].id == job_id


def test_reconcile_marks_interrupted(settings: Settings) -> None:
    store = Store(settings.db_path)
    run_id = store.create_run()
    job_id = store.jobs.create("generate")
    store.close()
    reopened = Store(settings.db_path)
    assert reopened.reconcile_interrupted() == 2
    run = reopened.get_run(run_id)
    job = reopened.jobs.get(job_id)
    assert run and run["status"] == "failed" and run["error"] == INTERRUPTED
    assert job and job.status == "failed" and job.error == INTERRUPTED
    reopened.close()


def test_readiness_checks(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    settings.anthropic_api_key = None
    by_key = {c.key: c for c in checks(settings)}
    assert not by_key["api_key"].ok and by_key["profile"].ok and by_key["corpus"].ok
    assert "2 post" in by_key["corpus"].detail and not by_key["topics"].required
    assert not is_ready(settings)
    settings.anthropic_api_key = "sk-ant-x"
    assert is_ready(settings)
    settings.research_provider = "tavily"
    assert not is_ready(settings) and "Tavily API key" in {c.label for c in checks(settings)}
    for f in settings.corpus_dir.glob("*.md"):
        f.unlink()
    settings.research_provider = "anthropic"
    assert not is_ready(settings)
