from postgen.store.db import Store


def test_run_draft_review_roundtrip(store: Store) -> None:
    run_id = store.create_run()
    store.set_run_topic(run_id, "AI AppSec", "A title")
    store.set_run_research(run_id, {"summary": "s"})
    d1 = store.add_draft(run_id, 0, {"hook": "h"}, "text v0", {"overall": 6.0}, 6.0)
    d2 = store.add_draft(run_id, 1, {"hook": "h2"}, "text v1", {"overall": 8.0}, 8.0)
    store.mark_final(d2)
    store.finish_run(run_id, {"input_tokens": 1})

    assert [d.id for d in store.list_final_drafts("pending")] == [d2]
    assert len(store.drafts_for_run(run_id)) == 2
    assert store.get_run(run_id)["status"] == "completed"

    store.add_review(d2, "edited", "final text", "too long")
    assert store.list_final_drafts("pending") == []
    row = store.get_draft(d2)
    assert row is not None and row.decision == "edited" and row.final_text == "final text"
    assert [r.id for r in store.recent_feedback(5)] == [d2]
    assert store.get_draft(d1) is not None


def test_recent_topics_and_failed_run(store: Store) -> None:
    run_id = store.create_run()
    store.set_run_topic(run_id, "area", "used title")
    store.finish_run(run_id, {}, error="boom")
    assert store.recent_topics(30) == ["used title"]
    assert store.get_run(run_id)["status"] == "failed"
    assert store.recent_topics(0) == ["used title"]  # created just now, still within window


def test_review_upsert(store: Store) -> None:
    run_id = store.create_run()
    d = store.add_draft(run_id, 0, {}, "t", None, None)
    store.add_review(d, "approved", "t", None)
    store.add_review(d, "rejected", None, "changed my mind")
    row = store.get_draft(d)
    assert row is not None and row.decision == "rejected" and row.reason == "changed my mind"
