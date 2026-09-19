"""Topic map: view, edit as YAML, rebuild from the profile."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from postgen.services.jobs import JobContext
from postgen.store.profile import load_topics, save_topics, topics_from_yaml, topics_to_yaml
from postgen.web.routes.common import ctx, launch, page, redirect

router = APIRouter()


@router.get("/topics", response_class=HTMLResponse)
def show_topics(request: Request) -> HTMLResponse:
    state = ctx(request)
    topics = load_topics(state.settings.topics_path)
    yaml_text = topics_to_yaml(topics) if topics else ""
    return page(request, "topics.html", topics=topics, yaml_text=yaml_text, error=None)


@router.post("/topics", response_class=HTMLResponse)
def save_topics_yaml(request: Request, yaml_text: Annotated[str, Form()]) -> Response:
    state = ctx(request)
    try:
        topics = topics_from_yaml(yaml_text)
    except ValueError as exc:
        return page(request, "topics.html", 400, topics=None, yaml_text=yaml_text, error=str(exc))
    save_topics(state.settings.topics_path, topics)
    return redirect("/topics")


@router.post("/topics/rebuild")
def rebuild_topics(request: Request) -> RedirectResponse:
    state = ctx(request)

    def target(job: JobContext) -> str:
        from postgen.llm import LLM
        from postgen.pipeline.topics import build_topic_map
        from postgen.store.profile import load_profile

        job.progress("deriving topic map from profile")
        topics = build_topic_map(LLM(state.settings), load_profile(state.settings.profile_path))
        save_topics(state.settings.topics_path, topics)
        job.progress(f"saved {len(topics.areas)} areas")
        return "/topics"

    return launch(state, "topics", target)
