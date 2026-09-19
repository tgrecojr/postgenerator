"""The voice corpus: past posts stored as markdown files with YAML front matter."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
TOKEN = re.compile(r"[a-z0-9][a-z0-9+\-#]{2,}")
SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")
BATCH_SEPARATOR = re.compile(r"^\s*\*{3,}\s*$", re.MULTILINE)
STOPWORDS = frozenset(
    [
        "the",
        "and",
        "for",
        "that",
        "this",
        "with",
        "you",
        "your",
        "are",
        "was",
        "were",
        "have",
        "has",
        "not",
        "but",
        "from",
        "they",
        "them",
        "their",
        "what",
        "when",
        "where",
        "which",
        "who",
        "will",
        "would",
        "can",
        "could",
        "should",
        "about",
        "into",
        "over",
        "than",
        "then",
        "there",
        "these",
        "those",
        "been",
        "being",
        "also",
        "just",
        "more",
        "most",
        "some",
        "such",
        "only",
        "very",
    ]
)


@dataclass
class Post:
    path: Path
    text: str
    date: str | None = None
    source: str = "seed"  # seed | approved | edited
    topic: str | None = None
    meta: dict[str, object] = field(default_factory=dict)

    @property
    def slug(self) -> str:
        return self.path.stem


def _parse(path: Path) -> Post:
    raw = path.read_text(encoding="utf-8")
    meta: dict[str, object] = {}
    body = raw
    if m := FRONT_MATTER.match(raw):
        loaded = yaml.safe_load(m.group(1)) or {}
        meta = dict(loaded) if isinstance(loaded, dict) else {}
        body = raw[m.end() :]
    return Post(
        path=path,
        text=body.strip(),
        date=str(meta.get("date")) if meta.get("date") else None,
        source=str(meta.get("source", "seed")),
        topic=str(meta["topic"]) if meta.get("topic") else None,
        meta=meta,
    )


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOPWORDS]


class Corpus:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def posts(self) -> list[Post]:
        files = sorted(self.directory.glob("*.md"))
        return [_parse(p) for p in files]

    def content_hash(self) -> str:
        h = hashlib.sha256()
        for p in sorted(self.directory.glob("*.md")):
            h.update(p.name.encode())
            h.update(p.read_bytes())
        return h.hexdigest()

    def _unique_path(self, stem: str) -> Path:
        """Timestamped file name that never overwrites an existing post."""
        stamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")
        path = self.directory / f"{stamp}-{stem}.md"
        n = 1
        while path.exists():
            n += 1
            path = self.directory / f"{stamp}-{stem}-{n}.md"
        return path

    def add(self, text: str, source: str, topic: str | None = None) -> Path:
        path = self._unique_path(source)
        meta = {"date": path.name[:10], "source": source}
        if topic:
            meta["topic"] = topic
        front = yaml.safe_dump(meta, sort_keys=True).strip()
        path.write_text(f"---\n{front}\n---\n\n{text.strip()}\n", encoding="utf-8")
        return path

    def remove(self, path: Path | str) -> None:
        """Delete a corpus file previously returned by `add`; ignores files outside the corpus."""
        target = Path(path)
        if target.parent.resolve() == self.directory.resolve():
            target.unlink(missing_ok=True)

    def _path_for(self, slug: str) -> Path | None:
        if not SLUG.match(slug):
            return None
        path = self.directory / f"{slug}.md"
        return path if path.is_file() else None

    def get(self, slug: str) -> Post | None:
        path = self._path_for(slug)
        return _parse(path) if path else None

    def update(self, slug: str, text: str, topic: str | None) -> Post:
        """Replace a post's body and topic, keeping its other front matter (date, source)."""
        path = self._path_for(slug)
        if path is None:
            raise KeyError(slug)
        meta = dict(_parse(path).meta)
        meta.pop("topic", None)
        if topic:
            meta["topic"] = topic
        front = yaml.safe_dump(meta, sort_keys=True).strip() if meta else ""
        head = f"---\n{front}\n---\n\n" if front else ""
        path.write_text(f"{head}{text.strip()}\n", encoding="utf-8")
        return _parse(path)

    def delete(self, slug: str) -> bool:
        path = self._path_for(slug)
        if path is None:
            return False
        path.unlink()
        return True

    def import_text(self, text: str) -> int:
        """Add several pasted posts separated by a line of three or more asterisks."""
        parts = [p.strip() for p in BATCH_SEPARATOR.split(text) if p.strip()]
        for part in parts:
            self.add(part, source="seed")
        return len(parts)

    def import_file(self, filename: str, content: str) -> Path:
        """Import one uploaded file. Files with front matter are kept verbatim."""
        if FRONT_MATTER.match(content):
            stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(filename).stem).strip("-.") or "post"
            path = self._unique_path(stem[:60])
            path.write_text(content.strip() + "\n", encoding="utf-8")
            return path
        return self.add(content, source="seed")

    def most_similar(self, query: str, k: int) -> list[Post]:
        """BM25-lite ranking of posts against a query; falls back to newest when no overlap."""
        posts = self.posts()
        if not posts:
            return []
        docs = [tokenize(p.topic or "") + tokenize(p.text) for p in posts]
        df: Counter[str] = Counter()
        for d in docs:
            df.update(set(d))
        n = len(docs)
        avg_len = sum(len(d) for d in docs) / n
        q_terms = set(tokenize(query))
        scored: list[tuple[float, Post]] = []
        for post, doc in zip(posts, docs, strict=True):
            tf = Counter(doc)
            score = 0.0
            for term in q_terms:
                if term not in tf:
                    continue
                idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
                num = tf[term] * 2.2
                den = tf[term] + 1.2 * (0.25 + 0.75 * len(doc) / avg_len)
                score += idf * num / den
            scored.append((score, post))
        scored.sort(key=lambda s: (s[0], s[1].date or ""), reverse=True)
        chosen = [p for s, p in scored if s > 0][:k]
        if len(chosen) < k:
            newest = sorted(posts, key=lambda p: p.date or "", reverse=True)
            chosen += [p for p in newest if p not in chosen][: k - len(chosen)]
        return chosen
