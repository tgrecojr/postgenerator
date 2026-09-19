"""First-run readiness: what must exist before a generation can succeed."""

from __future__ import annotations

import os
from dataclasses import dataclass

from postgen.config import Settings
from postgen.store.corpus import Corpus
from postgen.store.profile import load_profile, load_topics, load_voice

RECOMMENDED_POSTS = 5


@dataclass
class Check:
    key: str
    label: str
    ok: bool
    detail: str
    href: str
    required: bool = True


def api_key_present(settings: Settings) -> bool:
    return bool(
        settings.anthropic_api_key
        or os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    )


def _check_profile(settings: Settings) -> Check:
    try:
        profile = load_profile(settings.profile_path)
    except FileNotFoundError:
        return Check("profile", "Profile", False, "Not filled in yet", "/profile")
    except Exception as exc:
        return Check("profile", "Profile", False, f"Invalid: {exc}", "/profile")
    return Check("profile", "Profile", True, profile.headline, "/profile")


def _check_corpus(settings: Settings) -> Check:
    n = len(Corpus(settings.corpus_dir).posts())
    if n == 0:
        detail = "No posts yet. Add at least one of your past posts (5+ recommended)."
    elif n < RECOMMENDED_POSTS:
        detail = f"{n} post(s). Works, but {RECOMMENDED_POSTS}+ gives a much better voice."
    else:
        detail = f"{n} posts"
    return Check("corpus", "Voice corpus", n > 0, detail, "/corpus")


def checks(settings: Settings) -> list[Check]:
    key_ok = api_key_present(settings)
    items = [
        Check(
            "api_key",
            "Anthropic API key",
            key_ok,
            "Detected" if key_ok else "Set ANTHROPIC_API_KEY in the container environment",
            "/settings",
        ),
        _check_profile(settings),
        _check_corpus(settings),
    ]
    if settings.research_provider == "tavily":
        tavily_ok = bool(settings.tavily_api_key)
        items.append(
            Check(
                "tavily",
                "Tavily API key",
                tavily_ok,
                "Detected" if tavily_ok else "Required because POSTGEN_RESEARCH_PROVIDER=tavily",
                "/settings",
            )
        )
    topics = load_topics(settings.topics_path)
    items.append(
        Check(
            "topics",
            "Topic map",
            bool(topics and topics.areas),
            f"{len(topics.areas)} areas" if topics else "Built on first generation",
            "/topics",
            required=False,
        )
    )
    voice = load_voice(settings.voice_profile_path)
    items.append(
        Check(
            "voice",
            "Voice profile",
            voice is not None,
            "Built" if voice else "Built on first generation",
            "/voice",
            required=False,
        )
    )
    return items


def is_ready(settings: Settings) -> bool:
    return all(c.ok for c in checks(settings) if c.required)
