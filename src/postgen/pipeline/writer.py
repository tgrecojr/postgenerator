"""Step 2: draft the post in the author's voice."""

from __future__ import annotations

from postgen.llm import LLM
from postgen.pipeline.models import Draft, ResearchBrief
from postgen.prompts import render
from postgen.store.corpus import Post
from postgen.store.profile import Profile


def write_draft(
    llm: LLM,
    profile: Profile,
    voice: str,
    exemplars: list[Post],
    feedback: list[str],
    brief: ResearchBrief,
    previous: str | None = None,
    notes: list[str] | None = None,
) -> Draft:
    return llm.structured(
        "writer",
        render("writer_system", profile=profile, voice=voice),
        render(
            "writer_user",
            exemplars=exemplars,
            feedback=feedback,
            brief=brief,
            previous=previous,
            notes=notes or [],
        ),
        Draft,
    )
