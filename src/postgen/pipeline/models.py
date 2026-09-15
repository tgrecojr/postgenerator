"""Structured schemas exchanged between pipeline steps (also used as LLM output formats)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TopicArea(BaseModel):
    name: str = Field(description="Short subject-area name, e.g. 'AI Application Security'")
    description: str = Field(description="One or two sentences on what this area covers")
    example_angles: list[str] = Field(description="3-5 concrete post angles inside this area")


class TopicMap(BaseModel):
    areas: list[TopicArea]


class TopicProposal(BaseModel):
    area: str = Field(description="Which subject area this angle belongs to")
    title: str = Field(description="Working title / one-line angle for the post")
    why_now: str = Field(description="Why this is timely or worth the audience's attention")
    search_queries: list[str] = Field(description="3-6 web search queries to research this angle")


class Source(BaseModel):
    title: str
    url: str
    key_points: list[str] = Field(description="Facts or claims taken from this source")


class ResearchBrief(BaseModel):
    topic: str
    summary: str = Field(description="Neutral 150-250 word synthesis of what was found")
    key_facts: list[str] = Field(description="Concrete, attributable facts with dates/numbers")
    sources: list[Source]
    conventional_takes: list[str] = Field(
        description="What most existing commentary already says (so the post can avoid it)"
    )
    contrarian_angles: list[str] = Field(
        description="Under-discussed, disputed or practitioner-level angles worth taking"
    )
    practitioner_hooks: list[str] = Field(
        description="Specific details an AppSec practitioner would recognise as real"
    )


class Draft(BaseModel):
    hook: str = Field(description="First 1-2 lines; must earn the 'see more' click")
    body: str = Field(description="The main post body, LinkedIn-formatted with line breaks")
    close: str = Field(description="Final line: question, call to action, or punchline")
    hashtags: list[str] = Field(description="0-4 hashtags without the # symbol")
    claims_used: list[str] = Field(description="Facts from the brief this draft relies on")

    def render(self) -> str:
        tags = " ".join(f"#{t.lstrip('#')}" for t in self.hashtags)
        parts = [self.hook.strip(), self.body.strip(), self.close.strip()]
        text = "\n\n".join(p for p in parts if p)
        return f"{text}\n\n{tags}".rstrip() if tags else text


class DimensionScore(BaseModel):
    score: float = Field(description="0-10")
    rationale: str


class Evaluation(BaseModel):
    originality: DimensionScore
    voice_match: DimensionScore
    engagement: DimensionScore
    factual_grounding: DimensionScore
    linkedin_fit: DimensionScore
    overall: float = Field(description="Weighted 0-10 overall score")
    verdict: str = Field(description="One of: publish, revise, reject")
    revision_notes: list[str] = Field(description="Specific, actionable edits if not 'publish'")

    def dimensions(self) -> dict[str, DimensionScore]:
        return {
            "originality": self.originality,
            "voice_match": self.voice_match,
            "engagement": self.engagement,
            "factual_grounding": self.factual_grounding,
            "linkedin_fit": self.linkedin_fit,
        }


class VoiceProfile(BaseModel):
    summary: str = Field(description="2-3 sentence characterisation of the author's voice")
    tone: list[str]
    structure_patterns: list[str] = Field(description="How posts typically open, develop, close")
    sentence_style: list[str] = Field(description="Length, rhythm, punctuation habits")
    vocabulary: list[str] = Field(description="Recurring words, phrases, jargon level")
    formatting: list[str] = Field(description="Line breaks, lists, emoji, hashtags habits")
    do: list[str]
    dont: list[str]
    corrections: list[str] = Field(
        description="Lessons learned from the author's edits and rejections of past drafts"
    )

    def render(self) -> str:
        def section(title: str, items: list[str]) -> str:
            bullets = "\n".join(f"- {i}" for i in items) or "- (none yet)"
            return f"## {title}\n{bullets}\n"

        return "\n".join(
            [
                "# Voice profile\n",
                self.summary.strip() + "\n",
                section("Tone", self.tone),
                section("Structure patterns", self.structure_patterns),
                section("Sentence style", self.sentence_style),
                section("Vocabulary", self.vocabulary),
                section("Formatting", self.formatting),
                section("Do", self.do),
                section("Don't", self.dont),
                section("Corrections learned from feedback", self.corrections),
            ]
        )
