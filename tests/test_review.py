from postgen.config import Settings
from postgen.review import record_decision
from postgen.store.corpus import Corpus
from postgen.store.db import Store


def _draft(store: Store) -> int:
    run_id = store.create_run()
    store.set_run_topic(run_id, "area", "title")
    d = store.add_draft(run_id, 0, {}, "Original draft text", None, None)
    store.mark_final(d)
    return d


def test_approve_unchanged_appends_to_corpus(settings: Settings, store: Store) -> None:
    d = store.get_draft(_draft(store))
    assert d is not None
    before = len(Corpus(settings.corpus_dir).posts())
    assert record_decision(settings, store, d, "approved", "Original draft text  ") == "approved"
    posts = Corpus(settings.corpus_dir).posts()
    assert len(posts) == before + 1
    added = [p for p in posts if p.source == "approved"]
    assert len(added) == 1 and added[0].topic == "title"


def test_approve_with_changes_becomes_edited(settings: Settings, store: Store) -> None:
    d = store.get_draft(_draft(store))
    assert d is not None
    result = record_decision(settings, store, d, "approved", "Rewritten text", "tighter")
    assert result == "edited"
    row = store.get_draft(d.id)
    assert row is not None and row.decision == "edited" and row.final_text == "Rewritten text"
    assert any(p.source == "edited" for p in Corpus(settings.corpus_dir).posts())


def test_reject_does_not_touch_corpus(settings: Settings, store: Store) -> None:
    d = store.get_draft(_draft(store))
    assert d is not None
    before = len(Corpus(settings.corpus_dir).posts())
    assert record_decision(settings, store, d, "rejected", reason="off brand") == "rejected"
    assert len(Corpus(settings.corpus_dir).posts()) == before
    row = store.get_draft(d.id)
    assert row is not None and row.reason == "off brand"


def test_unknown_decision_raises(settings: Settings, store: Store) -> None:
    d = store.get_draft(_draft(store))
    assert d is not None
    try:
        record_decision(settings, store, d, "maybe")
    except ValueError:
        return
    raise AssertionError("expected ValueError")
