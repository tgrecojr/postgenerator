"""Shared fixtures: temp data dir, settings, a FakeLLM that returns canned objects."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from postgen.config import Settings
from postgen.llm import LLM, Usage
from postgen.pipeline.models import (
    DimensionScore,
    Draft,
    Evaluation,
    ResearchBrief,
    Source,
    TopicArea,
    TopicMap,
    TopicProposal,
    VoiceProfile,
)
from postgen.store.db import Store

PROFILE = {
    "name": "Test Author",
    "headline": "AI Application Security | Product Security",
    "about": "I break and fix AI-enabled applications for a living.",
}


def dim(score: float) -> DimensionScore:
    return DimensionScore(score=score, rationale="because")


def make_eval(overall: float, verdict: str, notes: list[str] | None = None) -> Evaluation:
    return Evaluation(
        originality=dim(overall),
        voice_match=dim(overall),
        engagement=dim(overall),
        factual_grounding=dim(overall),
        linkedin_fit=dim(overall),
        overall=overall,
        verdict=verdict,
        revision_notes=notes or [],
    )


class FakeLLM(LLM):
    """Returns canned Pydantic objects keyed by output type; records every call."""

    def __init__(self, evaluations: list[Evaluation] | None = None) -> None:
        self.usage = Usage()
        self.calls: list[tuple[str, str]] = []
        self.evaluations = list(evaluations or [make_eval(8.5, "publish")])
        self.drafts_written = 0

    def structured(self, step: str, system: str, user: str, output: Any, effort: Any = None) -> Any:
        self.calls.append((step, user))
        if output is TopicMap:
            return TopicMap(
                areas=[
                    TopicArea(
                        name="AI Application Security",
                        description="Securing LLM-backed apps",
                        example_angles=["prompt injection in tool calls"],
                    )
                ]
            )
        if output is TopicProposal:
            return TopicProposal(
                area="AI Application Security",
                title="Why prompt injection scanners miss tool-call attacks",
                why_now="New research this week",
                search_queries=["prompt injection tool calls", "MCP tool poisoning"],
            )
        if output is ResearchBrief:
            return ResearchBrief(
                topic="Why prompt injection scanners miss tool-call attacks",
                summary="Scanners look at user text; attacks arrive via tool results.",
                key_facts=["Paper X (2026) found 70% bypass rate"],
                sources=[Source(title="Paper X", url="https://example.org/x", key_points=["70%"])],
                conventional_takes=["Just add a scanner"],
                contrarian_angles=["Scan tool results, not prompts"],
                practitioner_hooks=["Most teams scan the wrong hop"],
            )
        if output is Draft:
            self.drafts_written += 1
            return Draft(
                hook="Your prompt-injection scanner is watching the wrong door."
                f" (v{self.drafts_written})",
                body="Most attacks arrive in tool results, not the user turn.\n\n"
                "Paper X found a 70% bypass rate.",
                close="Where are you scanning?",
                hashtags=["AppSec", "AISecurity"],
                claims_used=["Paper X (2026) found 70% bypass rate"],
            )
        if output is Evaluation:
            ev = self.evaluations.pop(0) if len(self.evaluations) > 1 else self.evaluations[0]
            return ev
        if output is VoiceProfile:
            return VoiceProfile(
                summary="Direct, practitioner voice.",
                tone=["blunt"],
                structure_patterns=["one-line claim, then why"],
                sentence_style=["short"],
                vocabulary=["concrete tool names"],
                formatting=["short paragraphs"],
                do=["name the failure mode"],
                dont=["hype"],
                corrections=[],
            )
        raise AssertionError(f"unexpected output type {output}")

    def research_with_search(self, *args: Any, **kwargs: Any) -> str:
        self.calls.append(("research_search", ""))
        return "# Report\n\nfindings"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    (d / "corpus").mkdir(parents=True)
    (d / "profile.yaml").write_text(yaml.safe_dump(PROFILE), encoding="utf-8")
    (d / "corpus" / "one.md").write_text(
        "---\ndate: 2026-01-01\nsource: seed\ntopic: prompt injection\n---\n"
        "Prompt injection is not an input validation problem.\n",
        encoding="utf-8",
    )
    (d / "corpus" / "two.md").write_text("SBOMs are not a security control.\n", encoding="utf-8")
    return d


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        data_dir=data_dir,
        allowed_hosts="testserver,localhost",
        anthropic_api_key="sk-ant-test-key-0000",
        tavily_api_key=None,
        _env_file=None,
    )


@pytest.fixture
def store(settings: Settings) -> Iterator[Store]:
    s = Store(settings.db_path)
    yield s
    s.close()


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()
