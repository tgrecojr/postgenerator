"""Atomic file writes for data files that are read while a job may be writing them."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_text_atomic(path: Path, text: str) -> None:
    """Write `text` to `path` so readers see the old or the new content, never a partial file.

    `Path.write_text` truncates first, so a concurrent reader (every page render loads the
    voice state) can observe an empty file. Writing a sibling temp file and renaming it over
    the target is atomic on POSIX and Windows.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Dot-prefixed and ".tmp"-suffixed so directory scans (corpus "*.md") never pick it up.
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.chmod(0o644)  # mkstemp creates 0600; keep the mode plain write_text produced
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
