"""Step 1: research the chosen angle into a structured brief.

Two providers:
- "anthropic": Claude's server-side web_search tool does the searching inside one call,
  then a second small call structures the markdown report.
- "tavily": Tavily returns extracted page content for each query; one call structures it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from postgen.config import Settings
from postgen.llm import LLM
from postgen.pipeline.models import ResearchBrief, TopicProposal
from postgen.prompts import render
from postgen.store.profile import Profile


class SearchClient(Protocol):
    def search(self, query: str, **kwargs: Any) -> dict[str, Any]: ...


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def research_anthropic(
    llm: LLM, settings: Settings, profile: Profile, proposal: TopicProposal
) -> ResearchBrief:
    report = llm.research_with_search(
        "research",
        render("research_system"),
        render("research_user", proposal=proposal, profile=profile, today=_today()),
        max_searches=settings.research_max_searches,
        effort="medium",
    )
    if not report.strip():
        raise RuntimeError("research step returned an empty report")
    return llm.structured(
        "research",
        render("research_structure_system"),
        render("research_structure_user", topic=proposal.title, report=report),
        ResearchBrief,
        effort="low",
    )


def _tavily_client(settings: Settings) -> SearchClient:
    if not settings.tavily_api_key:
        raise RuntimeError("TAVILY_API_KEY is required when POSTGEN_RESEARCH_PROVIDER=tavily")
    from tavily import TavilyClient

    client: SearchClient = TavilyClient(api_key=settings.tavily_api_key)
    return client


def _tavily_results(
    client: SearchClient, queries: list[str], per_query: int
) -> list[dict[str, str]]:
    seen: set[str] = set()
    results: list[dict[str, str]] = []
    for q in queries:
        response = client.search(q, search_depth="advanced", max_results=per_query)
        for r in response.get("results", []):
            url = r.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            results.append(
                {"title": r.get("title", url), "url": url, "content": r.get("content", "")}
            )
    return results


def research_tavily(
    llm: LLM,
    settings: Settings,
    profile: Profile,
    proposal: TopicProposal,
    client: SearchClient | None = None,
) -> ResearchBrief:
    client = client or _tavily_client(settings)
    per_query = max(1, settings.research_max_searches // max(1, len(proposal.search_queries)))
    results = _tavily_results(client, proposal.search_queries, max(3, per_query))
    if not results:
        raise RuntimeError("tavily returned no results for any query")
    return llm.structured(
        "research",
        render("research_system"),
        render(
            "research_tavily_user",
            proposal=proposal,
            profile=profile,
            today=_today(),
            results=results,
        ),
        ResearchBrief,
        effort="medium",
    )


def research(
    llm: LLM, settings: Settings, profile: Profile, proposal: TopicProposal
) -> ResearchBrief:
    if settings.research_provider == "tavily":
        return research_tavily(llm, settings, profile, proposal)
    return research_anthropic(llm, settings, profile, proposal)
