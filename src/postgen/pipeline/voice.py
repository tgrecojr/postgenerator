"""Voice profile: built from the corpus + reviewer feedback, cached until either changes."""

from __future__ import annotations

from postgen.config import Settings
from postgen.llm import LLM
from postgen.pipeline.models import VoiceProfile
from postgen.prompts import render
from postgen.store.corpus import Corpus
from postgen.store.db import DraftRow, Store
from postgen.store.profile import Profile, VoiceState, load_voice, save_voice

MAX_POSTS_FOR_VOICE = 60
MAX_FEEDBACK_FOR_VOICE = 30


def build_voice_profile(
    llm: LLM,
    profile: Profile,
    corpus: Corpus,
    feedback: list[DraftRow],
    previous: VoiceProfile | None,
) -> VoiceProfile:
    posts = sorted(corpus.posts(), key=lambda p: p.date or "", reverse=True)
    if not posts and not feedback:
        raise RuntimeError(
            f"No posts in {corpus.directory}. Add at least a few past posts before generating."
        )
    return llm.structured(
        "voice",
        render("voice_system"),
        render(
            "voice_user",
            profile=profile,
            posts=posts[:MAX_POSTS_FOR_VOICE],
            feedback=feedback[:MAX_FEEDBACK_FOR_VOICE],
            previous_corrections=previous.corrections if previous else [],
        ),
        VoiceProfile,
    )


def ensure_voice_profile(
    llm: LLM,
    settings: Settings,
    profile: Profile,
    corpus: Corpus,
    store: Store,
    force: bool = False,
) -> VoiceState:
    """Return the current voice state, rebuilding it if the corpus or feedback changed."""
    corpus_hash = corpus.content_hash()
    feedback = store.recent_feedback(MAX_FEEDBACK_FOR_VOICE)
    existing = load_voice(settings.voice_profile_path)
    fresh = (
        existing is not None
        and existing.corpus_hash == corpus_hash
        and existing.feedback_count == len(feedback)
    )
    if fresh and not force and existing is not None:
        return existing
    built = build_voice_profile(
        llm, profile, corpus, feedback, existing.profile if existing else None
    )
    state = VoiceState(corpus_hash=corpus_hash, feedback_count=len(feedback), profile=built)
    save_voice(settings.voice_profile_path, state)
    return state


def feedback_notes(rows: list[DraftRow]) -> list[str]:
    """Compact one-line lessons for the writer prompt."""
    notes: list[str] = []
    for r in rows:
        if r.decision == "rejected":
            notes.append(f"Rejected ('{r.topic_title}'): {r.reason or 'no reason given'}")
        elif r.decision == "edited":
            why = f" Reason: {r.reason}" if r.reason else ""
            notes.append(f"Edited ('{r.topic_title}') before posting.{why}")
    return notes
