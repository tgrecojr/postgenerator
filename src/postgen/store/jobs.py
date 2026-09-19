"""Persisted background jobs (generate / voice / topics) so history survives restarts."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from postgen.store.db import Store


@dataclass
class JobRow:
    id: int
    kind: str
    status: str  # running | done | failed
    started_at: str
    finished_at: str | None
    log: str
    result: str | None
    error: str | None
    run_id: int | None

    @property
    def log_lines(self) -> list[str]:
        return self.log.splitlines()

    @property
    def elapsed(self) -> str:
        start = datetime.fromisoformat(self.started_at)
        end = datetime.fromisoformat(self.finished_at) if self.finished_at else datetime.now(UTC)
        secs = max(0, int((end - start).total_seconds()))
        return f"{secs // 60}m {secs % 60:02d}s" if secs >= 60 else f"{secs}s"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class JobStore:
    def __init__(self, store: Store) -> None:
        self._db = store

    def create(self, kind: str) -> int:
        return self._db.write(
            "INSERT INTO jobs (kind, status, started_at) VALUES (?, 'running', ?)",
            (kind, _now()),
        )

    def append_log(self, job_id: int, line: str) -> None:
        self._db.write(
            "UPDATE jobs SET log = log || ? WHERE id=?", (f"{_now()[11:19]} {line}\n", job_id)
        )

    def set_run(self, job_id: int, run_id: int) -> None:
        self._db.write("UPDATE jobs SET run_id=? WHERE id=?", (run_id, job_id))

    def finish(self, job_id: int, result: str | None = None, error: str | None = None) -> None:
        self._db.write(
            "UPDATE jobs SET status=?, finished_at=?, result=?, error=? WHERE id=?",
            ("failed" if error else "done", _now(), result, error, job_id),
        )

    def fail_interrupted(self) -> int:
        from postgen.store.db import INTERRUPTED

        return self._db.write(
            "UPDATE jobs SET status='failed', finished_at=?, error=? WHERE status='running'",
            (_now(), INTERRUPTED),
        )

    def get(self, job_id: int) -> JobRow | None:
        row = self._db.one("SELECT * FROM jobs WHERE id=?", (job_id,))
        return self._to_row(row) if row else None

    def list(self, limit: int = 50) -> list[JobRow]:
        rows = self._db.rows("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,))
        return [self._to_row(r) for r in rows]

    def running(self) -> JobRow | None:
        row = self._db.one("SELECT * FROM jobs WHERE status='running' ORDER BY id DESC LIMIT 1")
        return self._to_row(row) if row else None

    @staticmethod
    def _to_row(r: sqlite3.Row) -> JobRow:
        return JobRow(
            id=r["id"],
            kind=r["kind"],
            status=r["status"],
            started_at=r["started_at"],
            finished_at=r["finished_at"],
            log=r["log"],
            result=r["result"],
            error=r["error"],
            run_id=r["run_id"],
        )
