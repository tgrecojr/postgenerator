from pathlib import Path

from postgen.store.corpus import Corpus, tokenize


def test_parses_front_matter_and_plain_files(data_dir: Path) -> None:
    posts = Corpus(data_dir / "corpus").posts()
    by_slug = {p.slug: p for p in posts}
    assert by_slug["one"].date == "2026-01-01"
    assert by_slug["one"].topic == "prompt injection"
    assert by_slug["one"].text.startswith("Prompt injection")
    assert by_slug["two"].source == "seed"
    assert by_slug["two"].date is None


def test_add_writes_front_matter_and_changes_hash(data_dir: Path) -> None:
    corpus = Corpus(data_dir / "corpus")
    before = corpus.content_hash()
    path = corpus.add("New post text", source="approved", topic="agents")
    assert path.exists()
    assert corpus.content_hash() != before
    post = next(p for p in corpus.posts() if p.path == path)
    assert post.source == "approved"
    assert post.topic == "agents"
    assert post.text == "New post text"


def test_most_similar_prefers_overlap_then_fills_with_newest(data_dir: Path) -> None:
    corpus = Corpus(data_dir / "corpus")
    hits = corpus.most_similar("prompt injection attacks", k=1)
    assert [h.slug for h in hits] == ["one"]
    hits = corpus.most_similar("zzz nothing matches", k=2)
    assert {h.slug for h in hits} == {"one", "two"}


def test_most_similar_on_empty_corpus(tmp_path: Path) -> None:
    assert Corpus(tmp_path / "empty").most_similar("x", 3) == []


def test_tokenize_drops_stopwords_and_short_tokens() -> None:
    assert tokenize("The AI is not a control") == ["control"]
