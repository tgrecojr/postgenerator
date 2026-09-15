"""FastAPI application factory for the review UI."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from postgen.config import Settings, get_settings
from postgen.store.db import Store

HERE = Path(__file__).parent


@dataclass
class Job:
    kind: str
    started_at: str
    status: str = "running"  # running | done | failed
    log: list[str] = field(default_factory=list)
    result: str | None = None
    error: str | None = None


@dataclass
class State:
    settings: Settings
    store: Store
    jobs: dict[int, Job] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    _next: int = 1

    def start_job(self, kind: str, target: Callable[[Job], str]) -> int:
        with self.lock:
            job_id = self._next
            self._next += 1
            self.jobs[job_id] = Job(kind, datetime.now(UTC).isoformat(timespec="seconds"))
        job = self.jobs[job_id]

        def runner() -> None:
            try:
                job.result = target(job)
                job.status = "done"
            except Exception as exc:  # surfaced in the UI, never swallowed
                job.error = f"{type(exc).__name__}: {exc}"
                job.status = "failed"

        threading.Thread(target=runner, name=f"job-{job_id}", daemon=True).start()
        return job_id

    def running(self) -> bool:
        return any(j.status == "running" for j in self.jobs.values())


def create_app(settings: Settings | None = None, store: Store | None = None) -> FastAPI:
    settings = settings or get_settings()
    store = store or Store(settings.db_path)
    app = FastAPI(title="postgen", docs_url=None, redoc_url=None)
    app.state.ctx = State(settings=settings, store=store)
    app.state.templates = Jinja2Templates(directory=HERE / "templates")
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    @app.middleware("http")
    async def same_origin_posts(request: Request, call_next: Any) -> Response:
        """Cheap CSRF guard for a single-user local app: block cross-site form posts."""
        if request.method == "POST":
            site = request.headers.get("sec-fetch-site")
            if site not in (None, "same-origin", "none"):
                return PlainTextResponse("cross-site request rejected", status_code=403)
        return await call_next(request)  # type: ignore[no-any-return]

    from postgen.web.routes import router

    app.include_router(router)
    return app
