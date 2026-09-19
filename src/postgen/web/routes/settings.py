"""Effective configuration (read-only; values come from the environment) and a key check."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from postgen.services import diagnostics
from postgen.web.routes.common import ctx, page

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
def show_settings(request: Request) -> HTMLResponse:
    rows = diagnostics.effective_settings(ctx(request).settings)
    return page(request, "settings.html", rows=rows, result=None)


@router.post("/settings/test", response_class=HTMLResponse)
def test_connection(request: Request) -> HTMLResponse:
    settings = ctx(request).settings
    ok, message = diagnostics.test_connection(settings)
    rows = diagnostics.effective_settings(settings)
    return page(request, "settings.html", rows=rows, result={"ok": ok, "message": message})
