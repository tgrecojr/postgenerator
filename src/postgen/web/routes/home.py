"""Dashboard, setup checklist, and data export."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from postgen.services.setup import checks, is_ready
from postgen.store.stats import pending_count, recent_runs, usage_totals
from postgen.web.routes.common import ctx, page, redirect

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> Response:
    state = ctx(request)
    if not is_ready(state.settings):
        return redirect("/setup")
    return page(
        request,
        "home.html",
        pending=pending_count(state.store),
        runs=recent_runs(state.store, 8),
        jobs=state.store.jobs.list(5),
        usage=usage_totals(state.store),
    )


@router.get("/setup", response_class=HTMLResponse)
def setup(request: Request) -> HTMLResponse:
    state = ctx(request)
    return page(request, "setup.html", checks=checks(state.settings))


@router.get("/export")
def export_data(request: Request) -> Response:
    """Download everything under the data directory as a zip (profile, corpus, DB, voice)."""
    data_dir = ctx(request).settings.data_dir
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(data_dir.rglob("*")):
            if path.is_file() and not _is_sqlite_sidecar(path):
                zf.write(path, path.relative_to(data_dir).as_posix())
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="postgen-data.zip"'},
    )


def _is_sqlite_sidecar(path: Path) -> bool:
    return path.suffix in {".db-wal", ".db-shm"} or path.name.endswith(("-wal", "-shm"))
