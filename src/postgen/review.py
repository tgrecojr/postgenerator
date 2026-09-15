"""Reviewer decisions: the feedback loop that teaches the writer over time."""

from __future__ import annotations

from postgen.config import Settings
from postgen.store.corpus import Corpus
from postgen.store.db import DraftRow, Store

DECISIONS = ("approved", "edited", "rejected")


def _normalise(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().replace("\r\n", "\n").split("\n"))


def record_decision(
    settings: Settings,
    store: Store,
    draft: DraftRow,
    decision: str,
    final_text: str | None = None,
    reason: str | None = None,
) -> str:
    """Persist the decision. Approved/edited posts join the corpus so the voice adapts.

    Returns the effective decision ("approved" is downgraded to "edited" if the text changed).
    """
    if decision not in DECISIONS:
        raise ValueError(f"unknown decision: {decision}")
    text = _normalise(final_text or draft.rendered)
    if decision == "approved" and text != _normalise(draft.rendered):
        decision = "edited"
    if decision == "rejected":
        store.add_review(draft.id, decision, None, reason or None)
        return decision
    store.add_review(draft.id, decision, text, reason or None)
    Corpus(settings.corpus_dir).add(text, source=decision, topic=draft.topic_title)
    return decision
