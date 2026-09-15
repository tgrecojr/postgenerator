from pathlib import Path

from postgen.prompts import render
from postgen.store.profile import Profile

TEMPLATE_DIR = Path("src/postgen/prompts")


def test_every_template_has_a_pair() -> None:
    names = {p.name.removesuffix(".md.j2") for p in TEMPLATE_DIR.glob("*.md.j2")}
    systems = {n.removesuffix("_system") for n in names if n.endswith("_system")}
    users = {n.removesuffix("_user") for n in names if n.endswith("_user")}
    assert systems <= users | {"research_tavily"} or systems == users


def test_untrusted_content_warning_present_where_web_content_flows() -> None:
    for name in (
        "research_system",
        "research_structure_system",
        "writer_system",
        "evaluator_system",
    ):
        text = render(
            name, profile=Profile(name="A", headline="h", about="a"), voice="v", threshold=7.5
        )
        assert "instructions" in text.lower()


def test_propose_user_renders_requested_topic() -> None:
    from postgen.pipeline.models import TopicArea, TopicMap

    text = render(
        "propose_user",
        profile=Profile(name="A", headline="h", about="a"),
        topics=TopicMap(areas=[TopicArea(name="X", description="d", example_angles=["e"])]),
        recent=["old title"],
        cooldown_days=60,
        requested="a specific ask",
    )
    assert "a specific ask" in text and "old title" in text
