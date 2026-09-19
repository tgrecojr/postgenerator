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
There is no operational CLI: every lifecycle step (profile, corpus, topics, generate,
review, voice, jobs, settings, export) is a page in the web UI. `postgen` only serves.
- `.venv/bin/postgen [--reload]` — web UI on http://127.0.0.1:8790 (data in `./data`)
- `docker compose up -d --build` — the self-hosted deployment (Chainguard, non-root)
- Pushes to `main` publish `ghcr.io/tgrecojr/postgen` (signed, SBOM + provenance attested)
- `scripts/import-data.sh ./data` — one-time copy of a local data dir into the volume
- `.venv/bin/ruff check . && .venv/bin/ruff format --check .` — lint
- `.venv/bin/mypy` — type check
- `.venv/bin/python -m pytest -q` — tests (fake LLM, no key needed)

## Architecture
- `src/postgen/cli.py` / `__main__.py` — `postgen` = serve; nothing else
- `src/postgen/config.py` — pydantic-settings (`POSTGEN_*` env vars, `.env`)
- `src/postgen/llm.py` — Anthropic wrapper: per-step model/effort, prompt caching, refusal
  fallbacks, `structured()` (Pydantic output), `research_with_search()` (server web search)
- `src/postgen/pipeline/` — `models.py` (schemas), `topics.py`, `research.py`,
  `writer.py`, `evaluator.py`, `voice.py`, `runner.py` (orchestration)
- `src/postgen/prompts/*.md.j2` — one Jinja2 template per step and role
- `src/postgen/store/` — `db.py` (SQLite runs/drafts/reviews, lock + WAL), `jobs.py`
  (persisted background jobs), `stats.py` (dashboard queries), `corpus.py` (markdown posts,
  edit/delete/import, BM25-lite exemplar retrieval), `profile.py` (profile/topics/voice files)
- `src/postgen/services/` — `jobs.py` (one-at-a-time JobRunner on a thread), `setup.py`
  (readiness checklist that gates Generate), `diagnostics.py` (settings view, key test)
- `src/postgen/review.py` — approve/edit/reject → reviews table + corpus append
- `src/postgen/web/` — FastAPI app factory (trusted-host + same-origin guards, `/healthz`),
  `routes/` one module per page, templates, static CSS
- `tests/` — unit tests with a `FakeLLM` that returns canned Pydantic objects

Conventions: files ≤ 300 lines, functions ≤ 50 lines. All LLM calls go through `LLM`;
never call the SDK directly from a step. Web content is untrusted data in every prompt.
Long work runs as a job via `JobRunner` (never inline in a request). Anything a user must
do must be reachable from the UI: the container has no shell.

Docker: `cgr.dev/chainguard/python:latest-dev` builder + `:latest` runtime, digest-pinned and
kept in lockstep by Renovate (same pattern as the other repos). No shell in the runtime, so
HEALTHCHECK/CMD are exec-form and `/data` is created in the builder. Keep `uv.lock` in sync.

CI/CD (standard across projects; do not deviate): `test.yml` on PRs, `docker-publish.yml`
on `main` (calls `supply-chain.yml`: Socket, OSV, pip-audit; then cosign + SBOM +
provenance to GHCR), `ghcr-retention.yml` weekly, `renovate.json` shared config.
Never Docker Hub.

## Environment Variables
Required: `ANTHROPIC_API_KEY`. Optional: `TAVILY_API_KEY`, `POSTGEN_DATA_DIR`,
`POSTGEN_MODEL`, `POSTGEN_MODEL_{TOPICS,RESEARCH,WRITER,EVALUATOR,VOICE}`, `POSTGEN_EFFORT`,
`POSTGEN_ENABLE_FALLBACKS`, `POSTGEN_RESEARCH_PROVIDER`, `POSTGEN_RESEARCH_MAX_SEARCHES`,
`POSTGEN_MAX_REVISIONS`, `POSTGEN_PASS_THRESHOLD`, `POSTGEN_TOPIC_COOLDOWN_DAYS`,
`POSTGEN_EXEMPLAR_COUNT`, `POSTGEN_RECENT_FEEDBACK_COUNT`, `POSTGEN_HOST`, `POSTGEN_PORT`,
`POSTGEN_ALLOWED_HOSTS`. Template: `.env.example`.
