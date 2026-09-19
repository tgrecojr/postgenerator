"""Runs one background job at a time on a thread and persists its progress via JobStore."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

from postgen.store.db import Store

log = logging.getLogger(__name__)


class JobBusyError(RuntimeError):
    """Raised when a job is requested while another is still running."""

    def __init__(self, job_id: int) -> None:
        super().__init__(f"job {job_id} is already running")
        self.job_id = job_id


@dataclass
class JobContext:
    id: int
    store: Store

    def progress(self, line: str) -> None:
        self.store.jobs.append_log(self.id, line)

    def attach_run(self, run_id: int) -> None:
        self.store.jobs.set_run(self.id, run_id)


JobTarget = Callable[[JobContext], str]


class JobRunner:
    def __init__(self, store: Store) -> None:
        self.store = store
        self._lock = threading.Lock()
        self._active: int | None = None

    def active_job_id(self) -> int | None:
        with self._lock:
            return self._active

    def running(self) -> bool:
        return self.active_job_id() is not None

    def start(self, kind: str, target: JobTarget) -> int:
        """Start `target` on a daemon thread; returns the persisted job id.

        `target` receives a JobContext for progress lines and returns the URL to open on
        success. Exceptions are recorded on the job row, never swallowed silently.
        """
        with self._lock:
            if self._active is not None:
                raise JobBusyError(self._active)
            job_id = self.store.jobs.create(kind)
            self._active = job_id
        ctx = JobContext(job_id, self.store)

        def runner() -> None:
            try:
                self.store.jobs.finish(job_id, result=target(ctx))
            except Exception as exc:
                log.exception("job %s (%s) failed", job_id, kind)
                self.store.jobs.finish(job_id, error=f"{type(exc).__name__}: {exc}")
            finally:
                with self._lock:
                    self._active = None

        threading.Thread(target=runner, name=f"job-{job_id}", daemon=True).start()
        return job_id
