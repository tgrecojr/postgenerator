"""Step 3: independent evaluation of a draft against the rubric."""

from __future__ import annotations

from postgen.llm import LLM
from postgen.pipeline.models import Draft, Evaluation, ResearchBrief
from postgen.prompts import render
from postgen.store.corpus import Post
from postgen.store.profile import Profile


def evaluate_draft(
    llm: LLM,
    profile: Profile,
    voice: str,
    exemplars: list[Post],
    brief: ResearchBrief,
    draft: Draft,
    revision: int,
    threshold: float,
) -> Evaluation:
    return llm.structured(
        "evaluator",
        render("evaluator_system", profile=profile, threshold=threshold),
        render(
            "evaluator_user",
            voice=voice,
            exemplars=exemplars,
            brief=brief,
            draft=draft.render(),
            claims=draft.claims_used,
            revision=revision,
        ),
        Evaluation,
    )
