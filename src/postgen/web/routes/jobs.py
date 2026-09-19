"""Background job history and progress pages."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from postgen.web.routes.common import ctx, page

router = APIRouter()


@router.get("/jobs", response_class=HTMLResponse)
def list_jobs(request: Request) -> HTMLResponse:
    return page(request, "jobs.html", jobs=ctx(request).store.jobs.list(100))


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def show_job(request: Request, job_id: int) -> HTMLResponse:
    job = ctx(request).store.jobs.get(job_id)
    if job is None:
        raise HTTPException(404)
    redirect_to = job.result if job.status == "done" else None
    return page(request, "job.html", job=job, redirect=redirect_to)
