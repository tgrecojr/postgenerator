"""Author profile (headline/about), derived topic map, and the generated voice profile."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from postgen.pipeline.models import TopicMap, VoiceProfile


class Profile(BaseModel):
    name: str = "The author"
    headline: str
    about: str
    audience: str = Field(
        default="Security engineers, AppSec leaders, and engineering managers",
        description="Who the posts are written for",
    )
    goals: str = Field(
        default="Share practitioner insight; build credibility; start useful conversations",
        description="What the author wants the posts to achieve",
    )
    off_limits: list[str] = Field(
        default_factory=list, description="Subjects or claims the author never posts about"
    )


def load_profile(path: Path) -> Profile:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Copy examples/profile.yaml to {path} and fill in your details."
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Profile.model_validate(data)


def load_topics(path: Path) -> TopicMap | None:
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return TopicMap.model_validate(data)


def save_topics(path: Path, topics: TopicMap) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Generated from profile.yaml by `postgen topics`. Edit freely; re-run to regenerate.\n"
        + yaml.safe_dump(topics.model_dump(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


class VoiceState(BaseModel):
    corpus_hash: str
    feedback_count: int
    profile: VoiceProfile


def load_voice(path: Path) -> VoiceState | None:
    state_path = path.with_suffix(".json")
    if not state_path.exists():
        return None
    return VoiceState.model_validate_json(state_path.read_text(encoding="utf-8"))


def save_voice(path: Path, state: VoiceState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.profile.render(), encoding="utf-8")
    path.with_suffix(".json").write_text(json.dumps(state.model_dump(), indent=2), encoding="utf-8")
