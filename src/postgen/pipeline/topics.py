"""Step 0: derive the topic map from the profile, and pick the next angle."""

from __future__ import annotations

from postgen.config import Settings
from postgen.llm import LLM
from postgen.pipeline.models import TopicMap, TopicProposal
from postgen.prompts import render
from postgen.store.db import Store
from postgen.store.profile import Profile, load_topics, save_topics


def build_topic_map(llm: LLM, profile: Profile) -> TopicMap:
    return llm.structured(
        "topics",
        render("topics_system"),
        render("topics_user", profile=profile),
        TopicMap,
        effort="medium",
    )


def ensure_topic_map(llm: LLM, settings: Settings, profile: Profile) -> TopicMap:
    existing = load_topics(settings.topics_path)
    if existing and existing.areas:
        return existing
    topics = build_topic_map(llm, profile)
    save_topics(settings.topics_path, topics)
    return topics


def propose_topic(
    llm: LLM,
    settings: Settings,
    profile: Profile,
    topics: TopicMap,
    store: Store,
    requested: str | None = None,
) -> TopicProposal:
    recent = store.recent_topics(settings.topic_cooldown_days)
    return llm.structured(
        "topics",
        render("propose_system"),
        render(
            "propose_user",
            profile=profile,
            topics=topics,
            recent=recent,
            cooldown_days=settings.topic_cooldown_days,
            requested=requested,
        ),
        TopicProposal,
        effort="medium",
    )
