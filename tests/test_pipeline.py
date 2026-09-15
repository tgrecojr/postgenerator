from pathlib import Path

import pytest

from postgen.config import Settings
from postgen.pipeline.runner import run_pipeline
from postgen.pipeline.voice import ensure_voice_profile, feedback_notes
from postgen.review import record_decision
from postgen.store.corpus import Corpus
from postgen.store.db import Store
from postgen.store.profile import load_profile, load_topics, load_voice
from tests.conftest import FakeLLM, make_eval


def test_full_run_publishes_first_draft(
    settings: Settings, store: Store, fake_llm: FakeLLM, data_dir: Path
) -> None:
    log: list[str] = []
    result = run_pipeline(settings=settings, llm=fake_llm, store=store, progress=log.append)

    assert result.revisions == 0
    assert result.evaluation.verdict == "publish"
    assert "Your prompt-injection scanner" in result.draft.render()
    assert load_topics(settings.topics_path) is not None
    assert load_voice(settings.voice_profile_path) is not None
    assert (data_dir / "voice_profile.md").exists()
    steps = [c[0] for c in fake_llm.calls]
    assert steps == [
        "voice",
        "topics",
        "topics",
        "research_search",
        "research",
        "writer",
        "evaluator",
    ]
    pending = store.list_final_drafts("pending")
    assert [d.id for d in pending] == [result.draft_id]
    assert store.get_run(result.run_id)["status"] == "completed"
    assert any("topic:" in line for line in log)


def test_revision_loop_keeps_best_and_stops_on_publish(settings: Settings, store: Store) -> None:
    llm = FakeLLM(
        evaluations=[make_eval(6.0, "revise", ["cut paragraph 2"]), make_eval(8.2, "publish")]
    )
    result = run_pipeline(settings=settings, llm=llm, store=store)
    assert result.revisions == 1
    assert result.evaluation.overall == 8.2
    drafts = store.drafts_for_run(result.run_id)
    assert len(drafts) == 2
    assert [d.is_final for d in sorted(drafts, key=lambda d: d.revision)] == [False, True]
    # revision prompt carried the evaluator's notes
    writer_calls = [u for s, u in llm.calls if s == "writer"]
    assert "cut paragraph 2" in writer_calls[1]
    assert "previous_draft" in writer_calls[1]


def test_revision_cap_respected(settings: Settings, store: Store) -> None:
    settings.max_revisions = 1
    llm = FakeLLM(evaluations=[make_eval(5.0, "revise"), make_eval(5.5, "revise")])
    result = run_pipeline(settings=settings, llm=llm, store=store)
    assert llm.drafts_written == 2
    assert result.evaluation.overall == 5.5


def test_requested_topic_and_recent_titles_reach_prompt(settings: Settings, store: Store) -> None:
    llm = FakeLLM()
    run_pipeline(settings=settings, llm=llm, store=store)
    run_pipeline(requested="MCP servers in CI", settings=settings, llm=llm, store=store)
    propose_calls = [u for s, u in llm.calls if s == "topics" and "recently_used_titles" in u]
    assert "MCP servers in CI" in propose_calls[-1]
    assert "Why prompt injection scanners miss tool-call attacks" in propose_calls[-1]


def test_failed_run_is_recorded(settings: Settings, store: Store) -> None:
    class Broken(FakeLLM):
        def research_with_search(self, *a: object, **k: object) -> str:
            raise RuntimeError("search down")

    with pytest.raises(RuntimeError, match="search down"):
        run_pipeline(settings=settings, llm=Broken(), store=store)
    runs = store.conn.execute("SELECT status, error FROM runs").fetchall()
    assert runs[0]["status"] == "failed" and "search down" in runs[0]["error"]


def test_voice_profile_rebuilds_on_corpus_or_feedback_change(
    settings: Settings, store: Store, fake_llm: FakeLLM
) -> None:
    profile = load_profile(settings.profile_path)
    corpus = Corpus(settings.corpus_dir)
    ensure_voice_profile(fake_llm, settings, profile, corpus, store)
    ensure_voice_profile(fake_llm, settings, profile, corpus, store)
    assert sum(1 for s, _ in fake_llm.calls if s == "voice") == 1

    corpus.add("another post", source="seed")
    ensure_voice_profile(fake_llm, settings, profile, corpus, store)
    assert sum(1 for s, _ in fake_llm.calls if s == "voice") == 2

    run_id = store.create_run()
    store.set_run_topic(run_id, "a", "t")
    d = store.add_draft(run_id, 0, {}, "draft", None, None)
    store.mark_final(d)
    row = store.get_draft(d)
    assert row is not None
    record_decision(settings, store, row, "rejected", reason="too generic")
    ensure_voice_profile(fake_llm, settings, profile, corpus, store)
    assert sum(1 for s, _ in fake_llm.calls if s == "voice") == 3
    voice_user = [u for s, u in fake_llm.calls if s == "voice"][-1]
    assert "too generic" in voice_user
    assert feedback_notes(store.recent_feedback(5)) == ["Rejected ('t'): too generic"]


def test_voice_profile_requires_corpus(settings: Settings, store: Store, tmp_path: Path) -> None:
    profile = load_profile(settings.profile_path)
    with pytest.raises(RuntimeError, match="No posts"):
        ensure_voice_profile(FakeLLM(), settings, profile, Corpus(tmp_path / "empty"), store)
