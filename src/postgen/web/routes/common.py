"""Helpers shared by route modules: request state, page rendering, job launching."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from postgen.services.jobs import JobBusyError, JobTarget
from postgen.services.setup import is_ready
from postgen.web.app import State


def ctx(request: Request) -> State:
    state: State = request.app.state.ctx
    return state


def page(request: Request, name: str, status_code: int = 200, **context: Any) -> HTMLResponse:
    state = ctx(request)
    context.update(
        request=request,
        running=state.running(),
        active_job=state.runner.active_job_id(),
        ready=is_ready(state.settings),
    )
    response: HTMLResponse = request.app.state.templates.TemplateResponse(
        request, name, context, status_code=status_code
    )
    return response


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def launch(state: State, kind: str, target: JobTarget) -> RedirectResponse:
    """Start a job and send the browser to its page; if one is running, go there instead."""
    try:
        job_id = state.runner.start(kind, target)
    except JobBusyError as exc:
        return redirect(f"/jobs/{exc.job_id}")
    return redirect(f"/jobs/{job_id}")
