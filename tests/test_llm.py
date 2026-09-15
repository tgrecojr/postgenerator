from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from postgen.config import Settings
from postgen.llm import FALLBACK_BETA, LLM, LLMRefusalError


class Out(BaseModel):
    value: str


def _response(
    stop: str, parsed: Any = None, text: str = "", content: list[Any] | None = None
) -> Any:
    blocks = content if content is not None else [SimpleNamespace(type="text", text=text)]
    return SimpleNamespace(
        stop_reason=stop,
        stop_details=SimpleNamespace(category="cyber") if stop == "refusal" else None,
        parsed_output=parsed,
        content=blocks,
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=5,
            cache_read_input_tokens=3,
            cache_creation_input_tokens=0,
        ),
    )


class FakeClient:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._call, create=self._call))

    def _call(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_structured_uses_step_model_effort_and_fallbacks(settings: Settings) -> None:
    settings.model_writer = "claude-sonnet-5"
    client = FakeClient([_response("end_turn", parsed=Out(value="ok"))])
    llm = LLM(settings, client=client)
    out = llm.structured("writer", "sys", "user", Out, effort="low")
    assert out.value == "ok"
    call = client.calls[0]
    assert call["model"] == "claude-sonnet-5"
    assert call["output_config"] == {"effort": "low"}
    assert call["betas"] == [FALLBACK_BETA] and call["fallbacks"] == "default"
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert call["thinking"] == {"type": "adaptive"}
    assert llm.usage.input_tokens == 10 and llm.usage.cache_read == 3


def test_fallbacks_can_be_disabled(settings: Settings) -> None:
    settings.enable_fallbacks = False
    client = FakeClient([_response("end_turn", parsed=Out(value="ok"))])
    LLM(settings, client=client).structured("writer", "s", "u", Out)
    assert "fallbacks" not in client.calls[0] and "betas" not in client.calls[0]


def test_refusal_and_truncation_raise(settings: Settings) -> None:
    llm = LLM(settings, client=FakeClient([_response("refusal")]))
    with pytest.raises(LLMRefusalError, match="cyber"):
        llm.structured("writer", "s", "u", Out)
    llm = LLM(settings, client=FakeClient([_response("max_tokens", parsed=Out(value="x"))]))
    with pytest.raises(RuntimeError, match="max_tokens"):
        llm.structured("writer", "s", "u", Out)


def test_research_with_search_resumes_after_pause_turn(settings: Settings) -> None:
    paused = _response(
        "pause_turn",
        content=[SimpleNamespace(type="server_tool_use", name="web_search", input={"query": "q"})],
    )
    final = _response(
        "end_turn",
        content=[
            SimpleNamespace(type="text", text="Let me search."),
            SimpleNamespace(type="web_search_tool_result", content=[]),
            SimpleNamespace(type="text", text="# Report"),
        ],
    )
    client = FakeClient([paused, final])
    report = LLM(settings, client=client).research_with_search("research", "s", "u", max_searches=3)
    assert report == "# Report"
    assert len(client.calls) == 2
    assert client.calls[0]["tools"][0]["type"] == "web_search_20260209"
    assert client.calls[0]["tools"][0]["max_uses"] == 3
    # second call replays the paused assistant turn
    assert client.calls[1]["messages"][1]["role"] == "assistant"
