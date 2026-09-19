"""Draft list, draft detail, review decisions, and the Generate action."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from postgen.review import record_decision
from postgen.services.jobs import JobContext
from postgen.services.setup import is_ready
from postgen.web.routes.common import ctx, launch, page, redirect

router = APIRouter()


@router.get("/drafts", response_class=HTMLResponse)
def list_drafts(request: Request, status: str = "pending") -> HTMLResponse:
    state = ctx(request)
    drafts = state.store.list_final_drafts(None if status == "all" else status)
    return page(request, "drafts.html", drafts=drafts, status=status)


@router.get("/drafts/{draft_id}", response_class=HTMLResponse)
def show_draft(request: Request, draft_id: int) -> HTMLResponse:
    state = ctx(request)
    draft = state.store.get_draft(draft_id)
    if draft is None:
        raise HTTPException(404)
    run = state.store.get_run(draft.run_id) or {}
    research = _json(run.get("research_json"))
    siblings = state.store.drafts_for_run(draft.run_id)
    return page(request, "draft.html", draft=draft, research=research, siblings=siblings, run=run)


@router.post("/drafts/{draft_id}/review")
def review_draft(
    request: Request,
    draft_id: int,
    decision: Annotated[str, Form()],
    final_text: Annotated[str, Form()] = "",
    reason: Annotated[str, Form()] = "",
) -> RedirectResponse:
    state = ctx(request)
    draft = state.store.get_draft(draft_id)
    if draft is None:
        raise HTTPException(404)
    try:
        record_decision(state.settings, state.store, draft, decision, final_text, reason)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return redirect(f"/drafts/{draft_id}")


@router.post("/generate")
def generate(request: Request, topic: Annotated[str, Form()] = "") -> RedirectResponse:
    state = ctx(request)
    if not is_ready(state.settings):
        return redirect("/setup")

    def target(job: JobContext) -> str:
        from postgen.pipeline.runner import run_pipeline

        result = run_pipeline(
            requested=topic.strip() or None,
            settings=state.settings,
            store=state.store,
            progress=job.progress,
        )
        job.attach_run(result.run_id)
        return f"/drafts/{result.draft_id}"

    return launch(state, "generate", target)


def _json(raw: str | None) -> dict[str, Any] | None:
    return json.loads(raw) if raw else None
