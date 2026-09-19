"""Thin wrapper over the Anthropic SDK used by every pipeline step.

Responsibilities: model/effort selection per step, prompt caching on the system prompt,
refusal handling with server-side fallbacks, structured (Pydantic) outputs, and a
web-search loop that tolerates `pause_turn`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel

from postgen.config import Settings, get_settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOKENS = 16000
MAX_PAUSE_RESTARTS = 5
# A web-search turn on Opus can run well past the SDK's 10-minute default, so the research
# call streams (keeps the connection alive) with a hard ceiling and no automatic retries:
# a timed-out agentic request keeps running and billing server-side, so retrying it
# silently multiplies the cost of a failure.
RESEARCH_TIMEOUT_SECONDS = 20 * 60


class LLMRefusalError(RuntimeError):
    """Raised when the model (and any fallback) declined the request."""


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0

    def add(self, usage: Any) -> None:
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.cache_read += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.cache_write += getattr(usage, "cache_creation_input_tokens", 0) or 0


class LLM:
    def __init__(self, settings: Settings | None = None, client: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = client or anthropic.Anthropic(api_key=self.settings.anthropic_api_key)
        self.usage = Usage()

    # ---- request assembly -------------------------------------------------

    def _common(self, step: str, system: str, effort: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self.settings.model_for(step),
            "max_tokens": MAX_TOKENS,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort or self.settings.effort},
        }
        if self.settings.enable_fallbacks:
            params["betas"] = [FALLBACK_BETA]
            params["fallbacks"] = "default"
        return params

    @staticmethod
    def _check_stop(response: Any) -> None:
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise LLMRefusalError(f"model refused (category={category})")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("response truncated at max_tokens")

    @staticmethod
    def _last_text(response: Any) -> str:
        texts = [b.text for b in response.content if b.type == "text"]
        return texts[-1] if texts else ""

    # ---- public API -------------------------------------------------------

    def ping(self) -> str:
        """Cheap credential check: fetch the default model's metadata. Returns its name."""
        client = self.client.with_options(timeout=15, max_retries=0)
        info = client.models.retrieve(self.settings.model)
        return str(getattr(info, "display_name", None) or info.id)

    def structured(
        self,
        step: str,
        system: str,
        user: str,
        output: type[T],
        effort: str | None = None,
    ) -> T:
        """One-shot call that returns a validated Pydantic instance."""
        params = self._common(step, system, effort)
        response = self.client.beta.messages.parse(
            messages=[{"role": "user", "content": user}],
            output_format=output,
            **params,
        )
        self.usage.add(response.usage)
        self._check_stop(response)
        parsed = response.parsed_output
        if parsed is None:
            raise RuntimeError(f"no structured output returned for step '{step}'")
        return parsed

    def research_with_search(
        self,
        step: str,
        system: str,
        user: str,
        max_searches: int,
        effort: str | None = None,
    ) -> str:
        """Free-form call with the server-side web search tool. Returns final text.

        Streams the response so the long-running server-side tool loop is not cut off by
        the HTTP read timeout (see RESEARCH_TIMEOUT_SECONDS).
        """
        params = self._common(step, system, effort)
        tools: list[Any] = [
            {"type": "web_search_20260209", "name": "web_search", "max_uses": max_searches}
        ]
        messages: list[Any] = [{"role": "user", "content": user}]
        client = self.client.with_options(timeout=RESEARCH_TIMEOUT_SECONDS, max_retries=0)
        for _ in range(MAX_PAUSE_RESTARTS):
            with client.beta.messages.stream(messages=messages, tools=tools, **params) as stream:
                response = stream.get_final_message()
            self.usage.add(response.usage)
            messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason == "pause_turn":
                continue
            self._check_stop(response)
            return self._last_text(response)
        raise RuntimeError("web search turn did not complete after repeated pauses")
