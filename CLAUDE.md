# postgen

## Overview
Self-hosted LinkedIn post generator. One run = topic → research → write → evaluate
(→ revise). Drafts land in a local review UI; approvals/edits/rejections feed a learned
voice profile so later drafts sound more like the author.

## Tech Stack
- Language: Python 3.14 (uv-managed venv in `.venv/`)
- LLM: Anthropic SDK (`anthropic` 1.x), Claude Opus 5 by default, structured outputs via Pydantic
- Web: FastAPI + Jinja2 (server-rendered, no JS framework)
- Storage: SQLite (stdlib) + markdown files under `data/`
- Tooling: Ruff, mypy (strict), pytest; multi-stage Docker; GitHub Actions

## Commands
- `.venv/bin/postgen init` — create `data/profile.yaml` and an example corpus post
- `.venv/bin/postgen run [--topic ...]` — generate one draft
- `.venv/bin/postgen serve` — review UI on http://127.0.0.1:8790
- `.venv/bin/postgen voice [--rebuild]` / `postgen topics [--rebuild]`
- `.venv/bin/ruff check . && .venv/bin/ruff format --check .` — lint
- `.venv/bin/mypy` — type check
- `.venv/bin/python -m pytest -q` — tests (fake LLM, no key needed)

## Architecture
- `src/postgen/config.py` — pydantic-settings (`POSTGEN_*` env vars, `.env`)
- `src/postgen/llm.py` — Anthropic wrapper: per-step model/effort, prompt caching, refusal
  fallbacks, `structured()` (Pydantic output), `research_with_search()` (server web search)
- `src/postgen/pipeline/` — `models.py` (schemas), `topics.py`, `research.py`,
  `writer.py`, `evaluator.py`, `voice.py`, `runner.py` (orchestration)
- `src/postgen/prompts/*.md.j2` — one Jinja2 template per step and role
- `src/postgen/store/` — `db.py` (SQLite runs/drafts/reviews), `corpus.py` (markdown posts
  + BM25-lite exemplar retrieval), `profile.py` (profile/topics/voice files)
- `src/postgen/review.py` — approve/edit/reject → reviews table + corpus append
- `src/postgen/web/` — FastAPI app factory, routes, templates, static CSS
- `tests/` — unit tests with a `FakeLLM` that returns canned Pydantic objects

Conventions: files ≤ 300 lines, functions ≤ 50 lines. All LLM calls go through `LLM`;
never call the SDK directly from a step. Web content is untrusted data in every prompt.

## Environment Variables
Required: `ANTHROPIC_API_KEY`. Optional: `TAVILY_API_KEY`, `POSTGEN_DATA_DIR`,
`POSTGEN_MODEL`, `POSTGEN_MODEL_{TOPICS,RESEARCH,WRITER,EVALUATOR,VOICE}`, `POSTGEN_EFFORT`,
`POSTGEN_ENABLE_FALLBACKS`, `POSTGEN_RESEARCH_PROVIDER`, `POSTGEN_RESEARCH_MAX_SEARCHES`,
`POSTGEN_MAX_REVISIONS`, `POSTGEN_PASS_THRESHOLD`, `POSTGEN_TOPIC_COOLDOWN_DAYS`,
`POSTGEN_EXEMPLAR_COUNT`, `POSTGEN_RECENT_FEEDBACK_COUNT`, `POSTGEN_HOST`, `POSTGEN_PORT`.
Template: `examples/env.example`.
