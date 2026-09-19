"""Voice profile: view and rebuild."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from postgen.services.jobs import JobContext
from postgen.store.profile import load_voice
from postgen.web.routes.common import ctx, launch, page

router = APIRouter()


@router.get("/voice", response_class=HTMLResponse)
def show_voice(request: Request) -> HTMLResponse:
    state = ctx(request)
    return page(request, "voice.html", voice=load_voice(state.settings.voice_profile_path))


@router.post("/voice/rebuild")
def rebuild_voice(request: Request) -> RedirectResponse:
    state = ctx(request)

    def target(job: JobContext) -> str:
        from postgen.llm import LLM
        from postgen.pipeline.voice import ensure_voice_profile
        from postgen.store.corpus import Corpus
        from postgen.store.profile import load_profile

        job.progress("rebuilding voice profile from corpus + feedback")
        ensure_voice_profile(
            LLM(state.settings),
            state.settings,
            load_profile(state.settings.profile_path),
            Corpus(state.settings.corpus_dir),
            state.store,
            force=True,
        )
        job.progress("voice profile saved")
        return "/voice"

    return launch(state, "voice", target)
