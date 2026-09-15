"""Orchestrates one generation run: topic -> research -> write -> evaluate (-> revise)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass

from postgen.config import Settings, get_settings
from postgen.llm import LLM
from postgen.pipeline.evaluator import evaluate_draft
from postgen.pipeline.models import Draft, Evaluation, ResearchBrief, TopicProposal
from postgen.pipeline.research import research
from postgen.pipeline.topics import ensure_topic_map, propose_topic
from postgen.pipeline.voice import ensure_voice_profile, feedback_notes
from postgen.pipeline.writer import write_draft
from postgen.store.corpus import Corpus, Post
from postgen.store.db import Store
from postgen.store.profile import Profile, load_profile

log = logging.getLogger(__name__)
Progress = Callable[[str], None]


@dataclass
class RunResult:
    run_id: int
    draft_id: int
    proposal: TopicProposal
    brief: ResearchBrief
    draft: Draft
    evaluation: Evaluation
    revisions: int


@dataclass
class Context:
    settings: Settings
    llm: LLM
    store: Store
    corpus: Corpus
    profile: Profile
    voice: str
    progress: Progress


def _write_and_score(
    ctx: Context, run_id: int, brief: ResearchBrief, exemplars: list[Post]
) -> tuple[int, Draft, Evaluation, int]:
    """Draft/evaluate loop. Returns (best draft id, draft, evaluation, revisions used)."""
    notes = feedback_notes(ctx.store.recent_feedback(ctx.settings.recent_feedback_count))
    best: tuple[int, Draft, Evaluation] | None = None
    previous: str | None = None
    eval_notes: list[str] = []
    for revision in range(ctx.settings.max_revisions + 1):
        ctx.progress(f"writing draft (revision {revision})")
        draft = write_draft(
            ctx.llm, ctx.profile, ctx.voice, exemplars, notes, brief, previous, eval_notes
        )
        ctx.progress("evaluating draft")
        ev = evaluate_draft(
            ctx.llm,
            ctx.profile,
            ctx.voice,
            exemplars,
            brief,
            draft,
            revision,
            ctx.settings.pass_threshold,
        )
        draft_id = ctx.store.add_draft(
            run_id, revision, draft.model_dump(), draft.render(), ev.model_dump(), ev.overall
        )
        ctx.progress(f"score {ev.overall:.1f} ({ev.verdict})")
        if best is None or ev.overall > best[2].overall:
            best = (draft_id, draft, ev)
        if ev.verdict == "publish" or ev.verdict == "reject":
            break
        previous, eval_notes = draft.render(), ev.revision_notes
    assert best is not None
    return best[0], best[1], best[2], revision


def _run(ctx: Context, run_id: int, requested: str | None) -> RunResult:
    ctx.progress("selecting topic")
    topics = ensure_topic_map(ctx.llm, ctx.settings, ctx.profile)
    proposal = propose_topic(ctx.llm, ctx.settings, ctx.profile, topics, ctx.store, requested)
    ctx.store.set_run_topic(run_id, proposal.area, proposal.title)
    ctx.progress(f"topic: {proposal.title}")

    ctx.progress(f"researching via {ctx.settings.research_provider}")
    brief = research(ctx.llm, ctx.settings, ctx.profile, proposal)
    ctx.store.set_run_research(run_id, brief.model_dump())
    ctx.progress(f"brief ready: {len(brief.sources)} sources")

    exemplars = ctx.corpus.most_similar(
        f"{proposal.area} {proposal.title}", ctx.settings.exemplar_count
    )
    draft_id, draft, ev, revisions = _write_and_score(ctx, run_id, brief, exemplars)
    ctx.store.mark_final(draft_id)
    return RunResult(run_id, draft_id, proposal, brief, draft, ev, revisions)


def run_pipeline(
    requested: str | None = None,
    settings: Settings | None = None,
    llm: LLM | None = None,
    store: Store | None = None,
    progress: Progress | None = None,
) -> RunResult:
    settings = settings or get_settings()
    llm = llm or LLM(settings)
    store = store or Store(settings.db_path)
    progress = progress or (lambda msg: log.info(msg))
    profile = load_profile(settings.profile_path)
    corpus = Corpus(settings.corpus_dir)

    progress("checking voice profile")
    voice = ensure_voice_profile(llm, settings, profile, corpus, store)
    ctx = Context(settings, llm, store, corpus, profile, voice.profile.render(), progress)

    run_id = store.create_run()
    try:
        result = _run(ctx, run_id, requested)
    except Exception as exc:
        store.finish_run(run_id, asdict(llm.usage), error=f"{type(exc).__name__}: {exc}")
        raise
    store.finish_run(run_id, asdict(llm.usage))
    return result
