import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from postgen.config import Settings
from postgen.store.corpus import Corpus
from postgen.store.db import Store
from postgen.web.app import create_app
from tests.conftest import FakeLLM


@pytest.fixture
def client(settings: Settings, store: Store) -> Iterator[TestClient]:
    app = create_app(settings=settings, store=store)
    with TestClient(app) as c:
        yield c


def _seed_draft(store: Store) -> int:
    run_id = store.create_run()
    store.set_run_topic(run_id, "AI AppSec", "A seeded title")
    store.set_run_research(
        run_id,
        {
            "summary": "s",
            "key_facts": [],
            "sources": [],
            "contrarian_angles": [],
            "conventional_takes": [],
        },
    )
    d = store.add_draft(
        run_id,
        0,
        {"hook": "h"},
        "Seeded draft body",
        {
            "originality": {"score": 8, "rationale": "r"},
            "voice_match": {"score": 8, "rationale": "r"},
            "engagement": {"score": 7, "rationale": "r"},
            "factual_grounding": {"score": 9, "rationale": "r"},
            "linkedin_fit": {"score": 8, "rationale": "r"},
            "overall": 8.0,
            "verdict": "publish",
            "revision_notes": [],
        },
        8.0,
    )
    store.mark_final(d)
    store.finish_run(run_id, {})
    return d


def test_home_is_dashboard_when_ready(client: TestClient, store: Store) -> None:
    _seed_draft(store)
    page = client.get("/").text
    assert "Dashboard" in page and "pending draft" in page and "A seeded title" in page


def test_home_redirects_to_setup_until_ready(client: TestClient, settings: Settings) -> None:
    settings.profile_path.unlink()
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/setup"
    page = client.get("/setup").text
    assert "Not filled in yet" in page and "Finish setup" in page
    r = client.post("/generate", data={"topic": ""}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/setup"


def test_untrusted_host_rejected(client: TestClient) -> None:
    assert client.get("/", headers={"host": "evil.example"}).status_code == 400
    assert client.get("/healthz").json()["status"] == "ok"


def test_list_and_detail(client: TestClient, store: Store) -> None:
    d = _seed_draft(store)
    assert "A seeded title" in client.get("/drafts?status=pending").text
    page = client.get(f"/drafts/{d}").text
    assert "Seeded draft body" in page and "originality" in page and "Approve" in page
    assert client.get("/drafts/999").status_code == 404


def test_review_edit_flow(client: TestClient, store: Store, settings: Settings) -> None:
    d = _seed_draft(store)
    r = client.post(
        f"/drafts/{d}/review",
        data={"decision": "approved", "final_text": "Edited body", "reason": "shorter"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    page = client.get(f"/drafts/{d}").text
    assert "Edited body" in page and "edited" in page and "shorter" in page
    assert any(p.source == "edited" for p in Corpus(settings.corpus_dir).posts())
    assert "A seeded title" in client.get("/drafts?status=edited").text
    assert "A seeded title" not in client.get("/drafts?status=pending").text


def test_cross_site_post_rejected(client: TestClient, store: Store) -> None:
    d = _seed_draft(store)
    r = client.post(
        f"/drafts/{d}/review",
        data={"decision": "rejected"},
        headers={"sec-fetch-site": "cross-site"},
    )
    assert r.status_code == 403
    r = client.post(
        f"/drafts/{d}/review",
        data={"decision": "rejected", "reason": "no"},
        headers={"sec-fetch-site": "same-origin"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_corpus_page_and_add(client: TestClient, settings: Settings) -> None:
    assert "SBOMs are not" in client.get("/corpus").text
    r = client.post("/corpus", data={"text": "Pasted post", "topic": "t"}, follow_redirects=False)
    assert r.status_code == 303
    assert "Pasted post" in client.get("/corpus").text
    assert client.post("/corpus", data={"text": "   "}).status_code == 400


def test_generate_job_runs_pipeline(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import postgen.pipeline.runner as runner

    fake = FakeLLM()
    original = runner.run_pipeline

    def patched(**kwargs: object) -> object:
        kwargs["llm"] = fake
        return original(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(runner, "run_pipeline", patched)
    r = client.post("/generate", data={"topic": ""}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/jobs/")
    job_url = r.headers["location"]
    for _ in range(50):
        page = client.get(job_url).text
        if "done" in page or "failed" in page:
            break
        time.sleep(0.05)
    assert "done" in page and "/drafts/" in page
    assert "Why prompt injection scanners" in client.get("/drafts?status=pending").text
    jobs = client.get("/jobs").text
    assert "generate #1" in jobs and "open result" in jobs


def test_voice_page_without_profile(client: TestClient) -> None:
    assert "No voice profile yet" in client.get("/voice").text


def test_reviewed_draft_can_be_edited_again(
    client: TestClient, store: Store, settings: Settings
) -> None:
    d = _seed_draft(store)
    client.post(
        f"/drafts/{d}/review",
        data={"decision": "approved", "final_text": "First body", "reason": "one"},
        follow_redirects=False,
    )
    page = client.get(f"/drafts/{d}").text
    assert "Edit or change decision" in page and 'value="one"' in page
    r = client.post(
        f"/drafts/{d}/review",
        data={"decision": "approved", "final_text": "Second body", "reason": "two"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    page = client.get(f"/drafts/{d}").text
    assert "Second body" in page and "two" in page and "First body" not in page
    texts = [p.text for p in Corpus(settings.corpus_dir).posts() if p.source == "edited"]
    assert texts == ["Second body"]
