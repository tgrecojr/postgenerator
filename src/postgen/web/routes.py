"""HTTP routes for the review UI."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from postgen.review import record_decision
from postgen.store.corpus import Corpus
from postgen.store.profile import load_voice
from postgen.web.app import Job, State

router = APIRouter()


def _ctx(request: Request) -> State:
    state: State = request.app.state.ctx
    return state


def _page(request: Request, name: str, **context: Any) -> HTMLResponse:
    state = _ctx(request)
    context.update(request=request, running=state.running())
    response: HTMLResponse = request.app.state.templates.TemplateResponse(request, name, context)
    return response


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


# ---- drafts ---------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
def home() -> RedirectResponse:
    return _redirect("/drafts?status=pending")


@router.get("/drafts", response_class=HTMLResponse)
def list_drafts(request: Request, status: str = "pending") -> HTMLResponse:
    state = _ctx(request)
    drafts = state.store.list_final_drafts(None if status == "all" else status)
    return _page(request, "drafts.html", drafts=drafts, status=status)


@router.get("/drafts/{draft_id}", response_class=HTMLResponse)
def show_draft(request: Request, draft_id: int) -> HTMLResponse:
    state = _ctx(request)
    draft = state.store.get_draft(draft_id)
    if draft is None:
        raise HTTPException(404)
    run = state.store.get_run(draft.run_id) or {}
    research = _json(run.get("research_json"))
    siblings = state.store.drafts_for_run(draft.run_id)
    return _page(request, "draft.html", draft=draft, research=research, siblings=siblings, run=run)


@router.post("/drafts/{draft_id}/review")
def review_draft(
    request: Request,
    draft_id: int,
    decision: Annotated[str, Form()],
    final_text: Annotated[str, Form()] = "",
    reason: Annotated[str, Form()] = "",
) -> RedirectResponse:
    state = _ctx(request)
    draft = state.store.get_draft(draft_id)
    if draft is None:
        raise HTTPException(404)
    try:
        record_decision(state.settings, state.store, draft, decision, final_text, reason)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _redirect(f"/drafts/{draft_id}")


# ---- generation jobs --------------------------------------------------------


@router.post("/generate")
def generate(request: Request, topic: Annotated[str, Form()] = "") -> RedirectResponse:
    state = _ctx(request)
    if state.running():
        raise HTTPException(409, "a job is already running")

    def target(job: Job) -> str:
        from postgen.pipeline.runner import run_pipeline

        result = run_pipeline(
            requested=topic.strip() or None,
            settings=state.settings,
            store=state.store,
            progress=job.log.append,
        )
        return f"/drafts/{result.draft_id}"

    job_id = state.start_job("generate", target)
    return _redirect(f"/jobs/{job_id}")


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def show_job(request: Request, job_id: int) -> HTMLResponse:
    job = _ctx(request).jobs.get(job_id)
    if job is None:
        raise HTTPException(404)
    if job.status == "done" and job.result:
        return _page(request, "job.html", job=job, job_id=job_id, redirect=job.result)
    return _page(request, "job.html", job=job, job_id=job_id, redirect=None)


# ---- corpus & voice ---------------------------------------------------------


@router.get("/corpus", response_class=HTMLResponse)
def show_corpus(request: Request) -> HTMLResponse:
    posts = Corpus(_ctx(request).settings.corpus_dir).posts()
    posts.sort(key=lambda p: p.date or "", reverse=True)
    return _page(request, "corpus.html", posts=posts)


@router.post("/corpus")
def add_corpus_post(
    request: Request, text: Annotated[str, Form()], topic: Annotated[str, Form()] = ""
) -> RedirectResponse:
    if not text.strip():
        raise HTTPException(400, "post text is required")
    Corpus(_ctx(request).settings.corpus_dir).add(text, source="seed", topic=topic or None)
    return _redirect("/corpus")


@router.get("/voice", response_class=HTMLResponse)
def show_voice(request: Request) -> HTMLResponse:
    state = _ctx(request)
    voice = load_voice(state.settings.voice_profile_path)
    return _page(request, "voice.html", voice=voice)


@router.post("/voice/rebuild")
def rebuild_voice(request: Request) -> RedirectResponse:
    state = _ctx(request)
    if state.running():
        raise HTTPException(409, "a job is already running")

    def target(job: Job) -> str:
        from postgen.llm import LLM
        from postgen.pipeline.voice import ensure_voice_profile
        from postgen.store.profile import load_profile

        job.log.append("rebuilding voice profile")
        ensure_voice_profile(
            LLM(state.settings),
            state.settings,
            load_profile(state.settings.profile_path),
            Corpus(state.settings.corpus_dir),
            state.store,
            force=True,
        )
        return "/voice"

    return _redirect(f"/jobs/{state.start_job('voice', target)}")


def _json(raw: str | None) -> dict[str, Any] | None:
    import json

    return json.loads(raw) if raw else None
