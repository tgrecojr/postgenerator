# Architecture

## Data flow

```
profile.yaml ──► topic map (topics.yaml, cached) ──► TopicProposal
                                                          │
corpus/*.md ──► voice profile (voice_profile.md, cached) │
      ▲                 ▲                                 ▼
      │                 │                     ResearchBrief (web search)
      │                 │                                 │
      │                 │              exemplars (BM25) + feedback notes
      │                 │                                 ▼
      │                 │                     Draft ──► Evaluation ──┐
      │                 │                       ▲   revise ≤ N      │
      │                 │                       └───────────────────┘
      │                 │                                 ▼
      │                 │                    drafts table (final flagged)
      │                 │                                 ▼
      │                 │                       review UI: approve / edit / reject
      │                 │                                 ▼
      └── approved/edited text ──┘◄── reviews table (reason, final_text)
```

## Steps

| Step | Module | Model call | Output |
|---|---|---|---|
| Topic map | `pipeline/topics.py` | `structured()` | `TopicMap` (cached to `topics.yaml`) |
| Propose | `pipeline/topics.py` | `structured()` | `TopicProposal` (dedup vs last N days) |
| Research | `pipeline/research.py` | `research_with_search()` then `structured()` | `ResearchBrief` |
| Write | `pipeline/writer.py` | `structured()` | `Draft` |
| Evaluate | `pipeline/evaluator.py` | `structured()` | `Evaluation` |
| Voice | `pipeline/voice.py` | `structured()` | `VoiceProfile` (cached by corpus hash + feedback count) |

The research step is split in two on purpose: the search call is free-form so interim
text between tool calls cannot break JSON parsing, and the structuring call is small and
runs at low effort.

## Originality controls

1. The brief records "conventional takes" separately, and the writer is told to avoid them.
2. The writer must list `claims_used`; the evaluator caps factual grounding at 3 if any
   claim is not in the brief.
3. The evaluator scores originality against both the sources and the author's exemplars,
   penalising paraphrase.
4. Topic titles are deduplicated against the last `POSTGEN_TOPIC_COOLDOWN_DAYS` days.

## Learning loop

- `reviews.decision ∈ {approved, edited, rejected}`. Approved text that differs from the
  draft is auto-downgraded to `edited`.
- Approved/edited text is appended to `data/corpus/` with `source:` set accordingly, so
  it becomes an exemplar and part of the voice-profile input.
- `ensure_voice_profile()` rebuilds when the corpus hash or the count of edited/rejected
  reviews changes. The rebuild prompt receives draft vs. author-version pairs and reasons,
  and must emit a `corrections` list of inferred rules. Previous corrections are carried
  forward unless contradicted.
- The writer prompt also receives the most recent `POSTGEN_RECENT_FEEDBACK_COUNT`
  feedback notes directly, so a correction takes effect on the very next run.

## Runtime shape

One process: uvicorn serving FastAPI. Long work (generate, voice rebuild, topic rebuild)
runs on a single daemon thread via `services/jobs.py`; only one job at a time. Each job is a
row in the `jobs` table with its log, so history survives restarts, and on startup any job
or run still marked `running` is flagged failed ("interrupted"). The SQLite connection is
shared between the request thread and the job thread behind an `RLock`, in WAL mode.

`services/setup.py` is the readiness gate: API key present, profile valid, corpus non-empty
(plus a Tavily key when that provider is selected). Until it passes, `/` redirects to
`/setup` and `/generate` refuses to start a job.

The container is a shell-less Chainguard python image running as nonroot; there is no CLI inside it. Everything an operator
needs is a page: Profile, Corpus (add / edit / delete / bulk import), Topics (view / edit
YAML / rebuild), Voice, Jobs, Settings (effective config, masked secrets, key test), and a
zip export for backups.

## Trust boundaries

- Search results and page content are third-party input. Every prompt that sees them
  states they are data, not instructions. The evaluator is a separate call with a separate
  system prompt, so a compromised brief cannot also grade itself.
- The web UI is single-user and has no auth. It rejects cross-site `POST`s via
  `Sec-Fetch-Site` and unknown `Host` headers via `POSTGEN_ALLOWED_HOSTS` (DNS rebinding).
  Compose publishes on loopback only; put it behind Zero Trust / Tailscale to expose it.
- Corpus slugs from URLs are validated against a strict pattern and resolved only inside
  the corpus directory; uploads are size-capped.
- Secrets come only from the environment; nothing under `data/` is committed.
