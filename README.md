# postgen

Self-hosted LinkedIn post generator. Each run researches a topic drawn from your own
LinkedIn headline and About section, drafts a post in your voice, and has an independent
evaluator score it for originality, voice match, engagement, factual grounding, and
LinkedIn fit. You review the result in a small single-user web UI. Every approval, edit,
and rejection feeds back into the voice profile, so the writer gets closer to you over time.

Pipeline: **topic → research → write → evaluate (→ revise)**.

The whole lifecycle runs in the browser: profile, corpus, topic map, generation, review,
voice profile, job history, settings, and backup. There is no CLI to run; the container
image is distroless and ships nothing but the app.

## Run it with Docker

```bash
cp .env.example .env            # add your ANTHROPIC_API_KEY
docker compose up -d --build    # UI at http://127.0.0.1:8790
```

First visit takes you to **Setup**, a checklist that links to each thing a run needs:

1. **Profile**: paste your LinkedIn headline and About section.
2. **Corpus**: add past posts, one at a time or in bulk (paste with `***` separators,
   or upload `.md` / `.txt` files). Five or more is a sensible minimum.
3. **Settings → Test API connection** confirms the key and model work.

Then press **Generate** (optionally with a topic request). The job page shows progress and
you can close it; the draft appears under **Pending** when the run finishes. Open it, edit
if you like, then **Approve** or **Reject** with a reason. Approved and edited posts join the
corpus; edits and rejection reasons are distilled into the voice profile on the next run.

Data lives in the named volume `postgen-data`. **Dashboard → download data as zip** is
your backup. To move an existing local `data/` directory into the volume once:

```bash
scripts/import-data.sh ./data
```

### Exposing it beyond localhost

The UI has no authentication. Compose publishes the port on `127.0.0.1` only. To reach it
from elsewhere, put it behind Tailscale, Cloudflare Zero Trust, or a reverse proxy with
auth, and add that hostname to `POSTGEN_ALLOWED_HOSTS` (a comma-separated Host-header
allowlist that also blocks DNS-rebinding attacks).

## Configuration

Everything is an environment variable, read from `.env` by compose. See `.env.example`.
Required: `ANTHROPIC_API_KEY`. Everything else is optional and prefixed `POSTGEN_` (model
per step, effort, research provider, thresholds, allowed hosts, host/port). The **Settings**
page shows the effective values with secrets masked; the app never stores secrets itself.

## Development

```bash
uv sync                            # creates .venv with dev tools
cp .env.example .env
.venv/bin/postgen --reload        # local UI at http://127.0.0.1:8790, data in ./data
```

Quality gate (also run in CI):

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/python -m pytest -q     # fake LLM; no API key needed
```

CI follows the same shape as the other repos: `test.yml` (lint, mypy, pytest, Docker
build) on pull requests; `docker-publish.yml` on every push to `main` runs the
`supply-chain.yml` scan (Socket, OSV, pip-audit), then builds a multi-arch image, signs it
with cosign, and attests an SBOM and build provenance to `ghcr.io/tgrecojr/postgen`;
`ghcr-retention.yml` prunes old versions weekly; Renovate keeps dependencies, actions,
and the Chainguard base images current. To run the published image instead of building
locally, replace `build: .` in `compose.yaml` with `image: ghcr.io/tgrecojr/postgen:latest`.

## How it learns your voice

- `voice_profile.md` is generated from the corpus plus your review feedback. It is
  cached and rebuilt automatically whenever the corpus or feedback count changes.
- The writer sees the voice profile, the most topically similar past posts as exemplars,
  and one-line notes from your recent edits and rejections.
- The evaluator scores voice match independently, so drift is caught before you see it.

## Security notes

- Single user, no auth: keep it on localhost or behind an authenticating proxy. Cross-site
  form posts are rejected via `Sec-Fetch-Site`; unknown `Host` headers are rejected.
- The container runs as a non-root user on a Chainguard python base with no shell.
- Web research content is treated as untrusted data in every prompt; it is never given
  instruction authority.
- Secrets come only from the environment. `data/` and `.env` are git-ignored.
