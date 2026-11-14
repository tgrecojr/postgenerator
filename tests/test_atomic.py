"""Data files are replaced atomically: a concurrent reader never sees a partial write."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from postgen.pipeline.models import VoiceProfile
from postgen.store import atomic
from postgen.store.atomic import write_text_atomic
from postgen.store.profile import VoiceState, load_voice, save_voice


def test_writes_and_replaces(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "file.txt"
    write_text_atomic(target, "first")
    write_text_atomic(target, "second ✓")
    assert target.read_text(encoding="utf-8") == "second ✓"
    assert [p.name for p in target.parent.iterdir()] == ["file.txt"]  # no temp files left


def test_failed_write_keeps_previous_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "file.txt"
    write_text_atomic(target, "original")

    def boom(*_args: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(atomic.os, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        write_text_atomic(target, "replacement")
    assert target.read_text(encoding="utf-8") == "original"
    assert [p.name for p in tmp_path.iterdir()] == ["file.txt"]


def test_voice_state_is_never_read_half_written(tmp_path: Path) -> None:
    """Regression: a page render during a voice rebuild read an empty voice.json and 500'd."""
    path = tmp_path / "voice.md"
    profile = VoiceProfile(
        summary="Direct.",
        tone=["plain"],
        structure_patterns=[],
        sentence_style=[],
        vocabulary=[],
        formatting=[],
        do=[],
        dont=[],
        corrections=[],
    )
    state = VoiceState(corpus_hash="x" * 64, feedback_count=0, profile=profile)
    save_voice(path, state)
    stop = threading.Event()

    def writer() -> None:
        while not stop.is_set():
            save_voice(path, state)

    thread = threading.Thread(target=writer)
    thread.start()
    try:
        for _ in range(2000):
            assert load_voice(path) == state
    finally:
        stop.set()
        thread.join()
