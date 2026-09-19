"""Web tests for the pages that replaced the CLI: profile, topics, corpus curation, settings."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from postgen.config import Settings
from postgen.store.corpus import Corpus
from postgen.store.db import Store
from postgen.store.profile import load_profile, load_topics
from postgen.web.app import create_app
from tests.conftest import FakeLLM


@pytest.fixture
def client(settings: Settings, store: Store) -> Iterator[TestClient]:
    with TestClient(create_app(settings=settings, store=store)) as c:
        yield c


def _wait(client: TestClient, url: str) -> str:
    import time

    for _ in range(100):
        page = client.get(url).text
        if "running" not in page:
            return page
        time.sleep(0.02)
    raise AssertionError("job did not finish")


# ---- profile ----------------------------------------------------------------


def test_profile_form_roundtrip(client: TestClient, settings: Settings) -> None:
    settings.profile_path.unlink()
    assert "Create profile" in client.get("/profile").text
    r = client.post(
        "/profile",
        data={
            "name": "Me",
            "headline": "Head",
            "about": "About me",
            "off_limits": "employer\n\nvendors",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    profile = load_profile(settings.profile_path)
    assert profile.headline == "Head" and profile.off_limits == ["employer", "vendors"]
    assert "Security engineers" in profile.audience  # default kept when blank
    page = client.get("/profile").text
    assert 'value="Head"' in page and "About me" in page


def test_profile_requires_headline_and_about(client: TestClient) -> None:
    r = client.post("/profile", data={"headline": "  ", "about": "x"})
    assert r.status_code == 400 and "required" in r.text


# ---- topics -----------------------------------------------------------------


def test_topics_empty_then_edit_yaml(client: TestClient, settings: Settings) -> None:
    assert "No topic map yet" in client.get("/topics").text
    bad = client.post("/topics", data={"yaml_text": "areas: [unclosed"})
    assert bad.status_code == 400 and "invalid YAML" in bad.text
    good = "areas:\n- name: A\n  description: d\n  example_angles: [x, y]\n"
    r = client.post("/topics", data={"yaml_text": good}, follow_redirects=False)
    assert r.status_code == 303
    topics = load_topics(settings.topics_path)
    assert topics and topics.areas[0].name == "A"
    assert "example_angles" in client.get("/topics").text


def test_topics_rebuild_job(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    import postgen.llm as llm_mod

    monkeypatch.setattr(llm_mod, "LLM", lambda *_a, **_k: FakeLLM())
    r = client.post("/topics/rebuild", follow_redirects=False)
    assert r.status_code == 303
    page = _wait(client, r.headers["location"])
    assert "done" in page and "saved 1 areas" in page
    topics = load_topics(settings.topics_path)
    assert topics and topics.areas[0].name == "AI Application Security"


def test_voice_rebuild_job(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import postgen.llm as llm_mod

    monkeypatch.setattr(llm_mod, "LLM", lambda *_a, **_k: FakeLLM())
    r = client.post("/voice/rebuild", follow_redirects=False)
    page = _wait(client, r.headers["location"])
    assert "done" in page
    assert "Direct, practitioner voice." in client.get("/voice").text


# ---- corpus -----------------------------------------------------------------


def test_corpus_edit_and_delete(client: TestClient, settings: Settings) -> None:
    corpus = Corpus(settings.corpus_dir)
    r = client.post(
        "/corpus/one/edit", data={"text": "Rewritten", "topic": "new topic"}, follow_redirects=False
    )
    assert r.status_code == 303
    post = corpus.get("one")
    assert post and post.text == "Rewritten" and post.topic == "new topic"
    assert post.source == "seed" and post.date == "2026-01-01"  # other front matter kept
    assert client.post("/corpus/missing/edit", data={"text": "x"}).status_code == 404
    assert client.post("/corpus/../etc/passwd/delete").status_code == 404
    r = client.post("/corpus/one/delete", follow_redirects=False)
    assert r.status_code == 303 and corpus.get("one") is None
    assert client.post("/corpus/one/delete").status_code == 404


def test_corpus_bulk_import(client: TestClient, settings: Settings) -> None:
    before = len(Corpus(settings.corpus_dir).posts())
    r = client.post(
        "/corpus/import",
        data={"text": "First pasted\n***\nSecond pasted\n\n****\n"},
        files=[
            ("files", ("plain.txt", b"From a text file", "text/plain")),
            ("files", ("exported.md", b"---\nsource: approved\n---\n\nExported", "text/markdown")),
        ],
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == "/corpus?imported=4"
    posts = Corpus(settings.corpus_dir).posts()
    assert len(posts) == before + 4
    assert any(p.text == "Exported" and p.source == "approved" for p in posts)
    assert "Imported 4 posts" in client.get("/corpus?imported=4").text
    assert client.post("/corpus/import", data={"text": "  "}).status_code == 400


# ---- settings ---------------------------------------------------------------


def test_settings_page_masks_secrets(client: TestClient, settings: Settings) -> None:
    settings.anthropic_api_key = "sk-ant-secret-value-1234"
    page = client.get("/settings").text
    assert "ANTHROPIC_API_KEY" in page and "…1234" in page and "secret-value" not in page
    assert "POSTGEN_MODEL" in page and settings.model in page


def test_settings_connection_test(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from postgen.services import diagnostics

    class Ping:
        def ping(self) -> str:
            return "Claude"

    monkeypatch.setattr(diagnostics, "LLM", lambda *_a, **_k: Ping())
    assert "OK:" in client.post("/settings/test").text

    class Boom:
        def ping(self) -> str:
            raise RuntimeError("401 bad key")

    monkeypatch.setattr(diagnostics, "LLM", lambda *_a, **_k: Boom())
    assert "RuntimeError: 401 bad key" in client.post("/settings/test").text


def test_export_zip(client: TestClient) -> None:
    import io
    import zipfile

    r = client.get("/export")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "profile.yaml" in names and "corpus/one.md" in names
