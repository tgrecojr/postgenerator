"""All HTTP routes, one module per area of the UI."""

from __future__ import annotations

from fastapi import APIRouter

from postgen.web.routes import corpus, drafts, home, jobs, profile, settings, topics, voice

router = APIRouter()
for module in (home, drafts, jobs, corpus, voice, topics, profile, settings):
    router.include_router(module.router)
