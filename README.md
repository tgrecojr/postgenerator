# postgen

Self-hosted LinkedIn post generator. Each run researches a topic drawn from your own
LinkedIn headline and About section, drafts a post in your voice, and has an independent
evaluator score it for originality, voice match, engagement, factual grounding, and
LinkedIn fit. You review the result in a small local web UI. Every approval, edit, and
rejection feeds back into the voice profile, so the writer gets closer to you over time.

Pipeline: **topic → research → write → evaluate (→ revise)**.

## Requirements

- Python 3.14 and [`uv`](https://docs.astral.sh/uv/)
- An Anthropic API key (or `ant auth login`)
- Optional: a Tavily key if you prefer Tavily over Claude's built-in web search

## Setup

```bash
uv venv --python 3.14
uv pip install -e ".[dev]"

cp examples/env.example .env.example   # committed template
cp examples/env.example .env           # local secrets; edit and add your key

.venv/bin/postgen init                 # creates data/profile.yaml + example corpus post
```

Then:

1. Edit `data/profile.yaml`: paste your LinkedIn headline and About section verbatim.
2. Drop past posts into `data/corpus/` as markdown files (one post per file), or paste
   them in via the web UI's Corpus page. Five or more is a sensible minimum.
3. Optional: `postgen topics` to see the subject areas derived from your profile.
   Edit `data/topics.yaml` if you want to steer it.

## Usage

```bash
.venv/bin/postgen run                     # generate one draft (auto-picks a topic)
.venv/bin/postgen run --topic "MCP tool poisoning in CI pipelines"
.venv/bin/postgen serve                   # review UI at http://127.0.0.1:8790
.venv/bin/postgen voice --rebuild         # force a voice-profile rebuild
.venv/bin/postgen topics --rebuild        # regenerate topic map from profile
```

In the UI, open a pending draft, edit the text if you like, then **Approve** or **Reject**
with a reason. Approved and edited posts are appended to `data/corpus/`; edits and
rejection reasons are distilled into the "Corrections" section of the voice profile on the
next run.

### Scheduling

`scripts/run-daily.sh` wraps `postgen run` for cron. A launchd example for macOS is in
`scripts/com.tgrecojr.postgen.plist` (install notes inside the file). With Docker:

```bash
docker compose up -d                       # review UI on 127.0.0.1:8790
docker compose run --rm generate           # one-shot generation (cron-friendly)
```

## How it learns your voice

- `data/voice_profile.md` is generated from the corpus plus your review feedback. It is
  cached and rebuilt automatically whenever the corpus or feedback count changes.
- The writer sees the voice profile, the most topically similar past posts as exemplars,
  and one-line notes from your recent edits and rejections.
- The evaluator scores voice match independently, so drift is caught before you see it.

## Environment variables

See `examples/env.example`. Required: `ANTHROPIC_API_KEY`. Everything else is optional
and prefixed `POSTGEN_` (model per step, effort, research provider, thresholds, host/port).

## Development

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/python -m pytest -q
```

Tests use a fake LLM; no API key is needed.

## Security notes

- The UI binds to localhost and has no auth. If you expose it, put it behind Cloudflare
  Zero Trust, Tailscale, or similar.
- Web research content is treated as untrusted data in every prompt; it is never given
  instruction authority.
- `data/` (your profile, posts, drafts) and `.env` are git-ignored.
