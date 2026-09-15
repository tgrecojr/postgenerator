"""Command-line interface: `postgen <command>`."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Annotated

import typer

from postgen.config import get_settings

app = typer.Typer(
    help="LinkedIn post generator: research -> write -> evaluate.", no_args_is_help=True
)
EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@app.command()
def init() -> None:
    """Create data/ with an example profile and corpus post to edit."""
    settings = get_settings()
    settings.corpus_dir.mkdir(parents=True, exist_ok=True)
    if settings.profile_path.exists():
        typer.echo(f"{settings.profile_path} already exists; leaving it alone.")
    else:
        shutil.copy(EXAMPLES / "profile.yaml", settings.profile_path)
        typer.echo(f"Wrote {settings.profile_path}. Fill in your headline and about section.")
    if not any(settings.corpus_dir.glob("*.md")):
        shutil.copy(
            EXAMPLES / "corpus" / "example-post.md", settings.corpus_dir / "example-post.md"
        )
        typer.echo(f"Wrote an example post to {settings.corpus_dir}. Replace it with your own.")


@app.command()
def topics(
    rebuild: bool = typer.Option(False, help="Regenerate even if topics.yaml exists"),
) -> None:
    """Derive (or regenerate) the topic map from profile.yaml."""
    from postgen.llm import LLM
    from postgen.pipeline.topics import build_topic_map, ensure_topic_map
    from postgen.store.profile import load_profile, save_topics

    settings = get_settings()
    profile = load_profile(settings.profile_path)
    llm = LLM(settings)
    if rebuild:
        topic_map = build_topic_map(llm, profile)
        save_topics(settings.topics_path, topic_map)
    else:
        topic_map = ensure_topic_map(llm, settings, profile)
    for area in topic_map.areas:
        typer.echo(f"\n{area.name}: {area.description}")
        for angle in area.example_angles:
            typer.echo(f"  - {angle}")


@app.command()
def voice(rebuild: bool = typer.Option(False, help="Force a rebuild")) -> None:
    """Build or show the voice profile learned from data/corpus and your feedback."""
    from postgen.llm import LLM
    from postgen.pipeline.voice import ensure_voice_profile
    from postgen.store.corpus import Corpus
    from postgen.store.db import Store
    from postgen.store.profile import load_profile

    settings = get_settings()
    state = ensure_voice_profile(
        LLM(settings),
        settings,
        load_profile(settings.profile_path),
        Corpus(settings.corpus_dir),
        Store(settings.db_path),
        force=rebuild,
    )
    typer.echo(state.profile.render())


@app.command()
def run(
    topic: Annotated[str | None, typer.Option(help="Request a specific subject")] = None,
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Generate one post: topic -> research -> write -> evaluate."""
    from postgen.pipeline.runner import run_pipeline

    _setup_logging(verbose)
    result = run_pipeline(requested=topic, progress=lambda m: typer.echo(f"  * {m}", err=True))
    typer.echo(f"\n=== Draft #{result.draft_id}: {result.proposal.title} ===\n")
    typer.echo(result.draft.render())
    typer.echo(
        f"\nScore {result.evaluation.overall:.1f}/10 ({result.evaluation.verdict}),"
        f" {result.revisions} revision(s). Review it at http://{get_settings().host}:"
        f"{get_settings().port}/drafts/{result.draft_id}"
    )


@app.command()
def serve(
    host: str | None = None,
    port: int | None = None,
    reload: bool = typer.Option(False, help="Auto-reload (development only)"),
) -> None:
    """Start the review web UI."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "postgen.web.app:create_app",
        factory=True,
        host=host or settings.host,
        port=port or settings.port,
        reload=reload,
    )


if __name__ == "__main__":
    app()
