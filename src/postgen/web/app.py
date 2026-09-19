"""FastAPI application factory for the single-user web UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from postgen.config import Settings, get_settings
from postgen.services.jobs import JobRunner
from postgen.store.db import Store

HERE = Path(__file__).parent


@dataclass
class State:
    settings: Settings
    store: Store
    runner: JobRunner

    def running(self) -> bool:
        return self.runner.running()


def create_app(settings: Settings | None = None, store: Store | None = None) -> FastAPI:
    settings = settings or get_settings()
    store = store or Store(settings.db_path)
    store.reconcile_interrupted()
    app = FastAPI(title="postgen", docs_url=None, redoc_url=None)
    app.state.ctx = State(settings=settings, store=store, runner=JobRunner(store))
    app.state.templates = Jinja2Templates(directory=HERE / "templates")
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    @app.middleware("http")
    async def same_origin_posts(request: Request, call_next: Any) -> Response:
        """Cheap CSRF guard for a single-user app: block cross-site form posts."""
        if request.method == "POST":
            site = request.headers.get("sec-fetch-site")
            if site not in (None, "same-origin", "none"):
                return PlainTextResponse("cross-site request rejected", status_code=403)
        return await call_next(request)  # type: ignore[no-any-return]

    # Outermost: a Host allowlist closes DNS-rebinding attacks against a no-auth local UI.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_host_list)

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        store_ok = store.one("SELECT 1 AS ok") is not None
        return JSONResponse({"status": "ok" if store_ok else "degraded", "db": store_ok})

    from postgen.web.routes import router

    app.include_router(router)
    return app
