"""Jinja2-rendered prompt templates. One file per (step, role)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_ENV = Environment(
    loader=FileSystemLoader(Path(__file__).parent),
    undefined=StrictUndefined,
    autoescape=False,  # noqa: S701 - prompts are plain text, not HTML
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=False,
)


def render(name: str, **context: Any) -> str:
    return _ENV.get_template(f"{name}.md.j2").render(**context).strip()
